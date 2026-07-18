"""Per-request FFmpeg MPEG-TS bridge with ordered bounded cleanup."""

from __future__ import annotations

import asyncio
import enum
import secrets
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiohttp import web

from . import NormalizedAudioFrame, NormalizedVideoFrame
from .rtp import RtcpSender, RtpPacketizer


FFMPEG_ARGS = (
    "-hide_banner",
    "-loglevel",
    "warning",
    "-protocol_whitelist",
    "pipe,udp,rtp",
    "-f",
    "sdp",
    "-i",
    "pipe:0",
    "-map",
    "0:v:0",
    "-c:v",
    "copy",
    "-map",
    "0:a:0?",
    "-c:a",
    "aac",
    "-b:a",
    "64k",
    "-f",
    "mpegts",
    "-mpegts_flags",
    "+resend_headers",
    "pipe:1",
)


class BridgeState(str, enum.Enum):
    STARTING = "starting"
    STREAMING = "streaming"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class BridgeCloseResult:
    reason: str
    startup_status: int | None
    cleanup_failed: bool = False


class MediaBridge:
    SETUP_TIMEOUT = 24.0
    RESPONSE_TIMEOUT = 25.0
    FFMPEG_RESERVE = 5.0
    TERMINATE_TIMEOUT = 5.0
    KILL_TIMEOUT = 2.0
    PIPE_DRAIN_TIMEOUT = 2.0
    CLOSE_RESPONSE_TIMEOUT = 2.0
    MPEGTS_CHUNK_SIZE = 64 * 1024

    def __init__(
        self,
        *,
        ffmpeg_binary: str,
        sdp: str | Callable[[tuple[tuple[int, int], ...]], str],
        port_allocator: Any,
        session_lease: Any,
        track_count: int,
        process_factory: Callable[..., Awaitable[Any]] | None = None,
        response_factory: Callable[[], Any] | None = None,
        socket_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_start_attempts: int = 3,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self._sdp = sdp
        self._port_allocator = port_allocator
        self._session_lease = session_lease
        self._track_count = track_count
        self._process_factory = process_factory or asyncio.create_subprocess_exec
        self._response_factory = response_factory or self._default_response
        self._socket_factory = socket_factory or self._new_datagram_socket
        self._clock = clock
        self._max_start_attempts = max_start_attempts

        self.state = BridgeState.STARTING
        self._state_lock = asyncio.Lock()
        self._close_future: asyncio.Future[BridgeCloseResult] | None = None
        self._close_task: asyncio.Task[None] | None = None
        self._terminal_reason: str | None = None
        self._startup_status: int | None = None
        self._setup_deadline = 0.0
        self._response_deadline = 0.0

        self.response: Any | None = None
        self._request: Any | None = None
        self._process: Any | None = None
        self._port_lease: Any | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._process_watch_task: asyncio.Task[None] | None = None
        self._response_write_task: asyncio.Task[None] | None = None
        self._discard_stdout = False
        self._process_exited = asyncio.Event()
        self._first_chunk: asyncio.Future[bytes] | None = None
        self._response_ready = asyncio.Event()
        self._response_lock = asyncio.Lock()
        self._session_released = False
        self._media_task: asyncio.Task[None] | None = None
        self.media_started = asyncio.Event()
        self._contract_task: asyncio.Task[None] | None = None
        self.rtp_sockets: tuple[Any, ...] = ()
        self.rtp_drop_count = 0

    @staticmethod
    def _default_response() -> web.StreamResponse:
        return web.StreamResponse(headers={"Content-Type": "video/mp2t"})

    @staticmethod
    def _new_datagram_socket() -> socket.socket:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setblocking(False)
        return udp_socket

    @property
    def close_future(self) -> asyncio.Future[BridgeCloseResult]:
        if self._close_future is None:
            self._close_future = asyncio.get_running_loop().create_future()
        return self._close_future

    async def run(self, request: web.Request) -> web.StreamResponse:
        started_at = self._clock()
        self._setup_deadline = started_at + self.SETUP_TIMEOUT
        self._response_deadline = started_at + self.RESPONSE_TIMEOUT
        self._request = request
        self.response = self._response_factory()
        if hasattr(self.response, "headers"):
            self.response.headers["Content-Type"] = "video/mp2t"
        try:
            first_chunk = await self._start_until_first_chunk()
            await self._prepare_response(200)
            await self._write_response(first_chunk)
            self.state = BridgeState.STREAMING
            self._response_ready.set()
            if self._process_exited.is_set():
                await self.request_close("ffmpeg_exit")
            return self.response
        except asyncio.TimeoutError:
            await self.request_close("setup_timeout", startup_status=504)
            return self.response
        except asyncio.CancelledError:
            await self.request_close("handler_cancelled")
            raise
        except Exception:
            await self.request_close("startup_failed", startup_status=502)
            return self.response

    async def _start_until_first_chunk(self) -> bytes:
        last_error: BaseException | None = None
        for _ in range(self._max_start_attempts):
            if self._setup_deadline - self._clock() <= self.FFMPEG_RESERVE:
                raise asyncio.TimeoutError
            try:
                await self._start_attempt()
                timeout = self._setup_deadline - self._clock()
                if timeout <= 0:
                    raise asyncio.TimeoutError
                first_chunk = await asyncio.wait_for(
                    asyncio.shield(self._first_chunk),
                    timeout,
                )
                await asyncio.sleep(0)
                if self._process_exited.is_set():
                    raise RuntimeError("FFmpeg exited during startup")
                return first_chunk
            except asyncio.TimeoutError:
                raise
            except asyncio.CancelledError:
                raise
            except Exception as err:
                if self._close_task is not None:
                    raise
                last_error = err
                await self._cleanup_failed_attempt()
        if last_error is not None:
            raise last_error
        raise RuntimeError("FFmpeg start failed")

    async def _start_attempt(self) -> None:
        lease = await self._bounded_setup_call(
            self._port_allocator.acquire(self._track_count)
        )
        self._port_lease = lease
        lease.release_reservations()
        if not self.rtp_sockets:
            self.rtp_sockets = tuple(
                self._socket_factory() for _ in range(self._track_count * 2)
            )
        process = await self._bounded_setup_call(self._process_factory(
            self.ffmpeg_binary,
            *FFMPEG_ARGS,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        ))
        self._process = process
        self._process_exited = asyncio.Event()
        sdp = self._sdp(lease.pairs) if callable(self._sdp) else self._sdp
        process.stdin.write(sdp.encode("utf-8"))
        if hasattr(process.stdin, "drain"):
            await self._bounded_setup_call(process.stdin.drain())
        process.stdin.close()
        if hasattr(process.stdin, "wait_closed"):
            await self._bounded_setup_call(process.stdin.wait_closed())

        loop = asyncio.get_running_loop()
        self._first_chunk = loop.create_future()
        self._response_ready = asyncio.Event()
        self._stdout_task = asyncio.create_task(self._stdout_owner())
        self._stderr_task = asyncio.create_task(self._drain_pipe(process.stderr))
        self._process_watch_task = asyncio.create_task(self._watch_process())
        self._media_task = asyncio.create_task(self._produce_media(lease.pairs))
        self._contract_task = asyncio.create_task(self._watch_contract())

    async def _stdout_owner(self) -> None:
        while True:
            chunk = await self._process.stdout.read(self.MPEGTS_CHUNK_SIZE)
            if not chunk:
                if self._first_chunk is not None and not self._first_chunk.done():
                    self._first_chunk.set_exception(
                        RuntimeError("FFmpeg exited before first chunk")
                    )
                return
            if self._first_chunk is not None and not self._first_chunk.done():
                self._first_chunk.set_result(chunk)
                await self._response_ready.wait()
                continue
            if self.state is not BridgeState.STREAMING or self._discard_stdout:
                continue
            self._response_write_task = asyncio.create_task(
                self._write_response(chunk)
            )
            try:
                await asyncio.shield(self._response_write_task)
            except asyncio.CancelledError:
                if not self._discard_stdout:
                    raise
            except Exception:
                asyncio.create_task(self.request_close("response_failed"))
            finally:
                self._response_write_task = None

    async def _produce_media(
        self,
        pairs: tuple[tuple[int, int], ...],
    ) -> None:
        packetizer = RtpPacketizer(
            video_ssrc=secrets.randbits(32),
            audio_ssrc=secrets.randbits(32),
            video_sequence=secrets.randbits(16),
            audio_sequence=secrets.randbits(16),
            video_timestamp=secrets.randbits(32),
            audio_timestamp=secrets.randbits(32),
            clock=self._clock,
        )
        rtcp = RtcpSender(cname="xiaomi-miss")
        contract = self._session_lease.contract
        self.media_started.set()
        while True:
            frame = await self._session_lease.next_frame()
            if frame is None:
                return
            if isinstance(frame, NormalizedVideoFrame):
                for packet in packetizer.packetize_video(
                    contract.video_codec,
                    frame.data,
                    frame.pts,
                ):
                    self._send_datagram(0, packet.to_bytes(), pairs[0][0])
                self._send_report(
                    rtcp,
                    packetizer.video_track,
                    socket_index=1,
                    port=pairs[0][1],
                )
            elif contract.audio_codec is not None and len(pairs) > 1:
                packet = packetizer.packetize_audio(
                    contract.audio_codec,
                    frame.data,
                    pts=frame.pts,
                    sample_rate=frame.sample_rate,
                )
                self._send_datagram(2, packet.to_bytes(), pairs[1][0])
                self._send_report(
                    rtcp,
                    packetizer.audio_track,
                    socket_index=3,
                    port=pairs[1][1],
                )

    def _send_report(
        self,
        sender: RtcpSender,
        track: Any,
        *,
        socket_index: int,
        port: int,
    ) -> None:
        now = self._clock()
        report = sender.maybe_report(
            track,
            now=now,
            ntp_seconds=time.time() + 2_208_988_800,
        )
        if report is not None:
            self._send_datagram(socket_index, report, port)

    def _send_datagram(self, index: int, body: bytes, port: int) -> None:
        try:
            self.rtp_sockets[index].sendto(body, ("127.0.0.1", port))
        except (BlockingIOError, InterruptedError):
            self.rtp_drop_count += 1

    async def _watch_contract(self) -> None:
        await self._session_lease.contract_changed.wait()
        close_task = asyncio.create_task(
            self.request_close("contract_changed", startup_status=502)
        )
        await asyncio.sleep(0)
        if self._first_chunk is not None and not self._first_chunk.done():
            self._first_chunk.set_exception(RuntimeError("contract changed"))
        await asyncio.shield(close_task)

    @staticmethod
    async def _drain_pipe(pipe: Any) -> None:
        while await pipe.read(MediaBridge.MPEGTS_CHUNK_SIZE):
            pass

    async def _watch_process(self) -> None:
        await self._process.wait()
        self._process_exited.set()
        if self.state is BridgeState.STREAMING:
            asyncio.create_task(self.request_close("ffmpeg_exit"))

    async def _write_response(self, chunk: bytes) -> None:
        async with self._response_lock:
            await self._bounded_response_call(self.response.write(chunk))

    async def _prepare_response(self, status: int) -> None:
        if getattr(self.response, "prepared", False):
            return
        self.response.set_status(status)
        await self._bounded_response_call(self.response.prepare(self._request))

    async def _bounded_setup_call(self, operation: Awaitable[Any]) -> Any:
        remaining = self._setup_deadline - self._clock()
        if remaining <= 0:
            if hasattr(operation, "close"):
                operation.close()
            raise asyncio.TimeoutError
        return await asyncio.wait_for(operation, remaining)

    async def _bounded_response_call(self, operation: Awaitable[Any]) -> Any:
        remaining = self._response_deadline - self._clock()
        if remaining <= 0:
            if hasattr(operation, "close"):
                operation.close()
            raise asyncio.TimeoutError
        return await asyncio.wait_for(operation, remaining)

    async def request_close(
        self,
        reason: str,
        *,
        startup_status: int | None = None,
    ) -> BridgeCloseResult:
        async with self._state_lock:
            if self._close_task is None:
                self.state = BridgeState.CLOSING
                self._terminal_reason = reason
                self._startup_status = startup_status
                self._close_task = asyncio.create_task(self._close())
        return await asyncio.shield(self.close_future)

    async def _close(self) -> None:
        cleanup_failed = False
        try:
            try:
                await self._detach_media()
            except BaseException:
                cleanup_failed = True
            try:
                await self._cancel_stdout_owner()
            except BaseException:
                cleanup_failed = True
            try:
                await self._finish_response()
            except BaseException:
                cleanup_failed = True
                if hasattr(self.response, "force_close"):
                    self.response.force_close()
                transport = getattr(self._request, "transport", None)
                if transport is not None:
                    if hasattr(transport, "abort"):
                        transport.abort()
                    elif hasattr(transport, "close"):
                        transport.close()
            self._response_ready.set()
            try:
                self._close_rtp_sockets()
            except BaseException:
                cleanup_failed = True
            try:
                await self._stop_process()
            except BaseException:
                cleanup_failed = True
            try:
                await self._release_ports()
            except BaseException:
                cleanup_failed = True
        finally:
            try:
                await self._release_session()
            except BaseException:
                cleanup_failed = True
            self.state = BridgeState.CLOSED
            result = BridgeCloseResult(
                reason=self._terminal_reason or "closed",
                startup_status=self._startup_status,
                cleanup_failed=cleanup_failed,
            )
            if not self.close_future.done():
                self.close_future.set_result(result)

    async def _cancel_stdout_owner(self) -> None:
        self._discard_stdout = True
        task = self._response_write_task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _detach_media(self) -> None:
        tasks = (self._media_task, self._contract_task)
        self._media_task = None
        self._contract_task = None
        for task in tasks:
            if task is not None and not task.done():
                task.cancel()
        for task in tasks:
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def _close_rtp_sockets(self) -> None:
        sockets, self.rtp_sockets = self.rtp_sockets, ()
        first_error: BaseException | None = None
        for udp_socket in sockets:
            try:
                udp_socket.close()
            except BaseException as err:
                if first_error is None:
                    first_error = err
        if first_error is not None:
            raise first_error

    async def _finish_response(self) -> None:
        if self.response is None:
            return
        prepared = getattr(self.response, "prepared", False)
        if not prepared and self._startup_status is not None:
            await self._prepare_response(self._startup_status)
            prepared = getattr(self.response, "prepared", False)
        if prepared:
            async with self._response_lock:
                operation = self.response.write_eof()
                if getattr(self.response, "status", None) == 200:
                    await asyncio.wait_for(
                        operation,
                        self.CLOSE_RESPONSE_TIMEOUT,
                    )
                else:
                    await self._bounded_response_call(operation)

    async def _stop_process(self) -> None:
        process = self._process
        if process is None:
            return
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(
                    asyncio.shield(process.wait()),
                    self.TERMINATE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                process.kill()
                await asyncio.wait_for(
                    asyncio.shield(process.wait()),
                    self.KILL_TIMEOUT,
                )
        if self._process_watch_task is not None:
            await self._await_task(self._process_watch_task)
        for task in (self._stdout_task, self._stderr_task):
            if task is not None:
                await self._await_task(task)
        self._process = None

    async def _await_task(self, task: asyncio.Task[Any]) -> None:
        try:
            await asyncio.wait_for(
                asyncio.shield(task),
                self.PIPE_DRAIN_TIMEOUT,
            )
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _cleanup_failed_attempt(self) -> None:
        await self._detach_media()
        self._close_rtp_sockets()
        try:
            await self._stop_process()
        finally:
            await self._release_ports()
        self._stdout_task = None
        self._stderr_task = None
        self._process_watch_task = None
        self._first_chunk = None

    async def _release_ports(self) -> None:
        lease, self._port_lease = self._port_lease, None
        if lease is not None:
            await lease.release()

    async def _release_session(self) -> None:
        if self._session_released:
            return
        self._session_released = True
        await self._session_lease.release()


__all__ = [
    "BridgeCloseResult",
    "BridgeState",
    "FFMPEG_ARGS",
    "MediaBridge",
]
