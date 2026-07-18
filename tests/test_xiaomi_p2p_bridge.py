from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.xiaomi_miot.core.xiaomi_p2p import (
    MediaContract,
    NormalizedAudioFrame,
    NormalizedVideoFrame,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.bridge import (
    FFMPEG_ARGS,
    BridgeState,
    MediaBridge,
)

from .helpers.fake_ffmpeg import FakeFfmpegProcess, FakeResponse


pytestmark = pytest.mark.enable_socket


@pytest.fixture(autouse=True)
def enable_test_sockets(socket_enabled):
    yield


EXPECTED_FFMPEG_ARGS = (
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


class FakePortLease:
    def __init__(self, events: list[str]) -> None:
        self.pairs = ((5000, 5001), (5002, 5003))
        self.events = events
        self.reservations_released = False
        self.released = False

    def release_reservations(self) -> None:
        self.reservations_released = True
        self.events.append("reservations")

    async def release(self) -> None:
        self.released = True
        self.events.append("ports")


class FakeAllocator:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.leases: list[FakePortLease] = []

    async def acquire(self, track_count: int) -> FakePortLease:
        assert track_count == 2
        lease = FakePortLease(self.events)
        self.leases.append(lease)
        return lease


class FakeSessionLease:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.released = 0
        self.contract = MediaContract(
            video_codec=4,
            audio_codec=1027,
            video_sps=b"\x67\x64",
            video_pps=b"\x68\xee",
            vps=None,
            width=1920,
            height=1080,
            fps=20,
            sample_rate=8000,
            channels=1,
        )
        self.frames: asyncio.Queue[
            NormalizedVideoFrame | NormalizedAudioFrame | None
        ] = asyncio.Queue()
        self.contract_changed = asyncio.Event()

    async def next_frame(
        self,
    ) -> NormalizedVideoFrame | NormalizedAudioFrame | None:
        return await self.frames.get()

    async def release(self) -> None:
        self.released += 1
        self.events.append("session")


class FakeDatagramSocket:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False
        self.block_next = False

    def sendto(self, body: bytes, target: tuple[str, int]) -> int:
        if self.block_next:
            self.block_next = False
            raise BlockingIOError
        self.sent.append((body, target))
        return len(body)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def bridge_parts():
    events: list[str] = []
    process = FakeFfmpegProcess()
    response = FakeResponse()
    calls = []

    async def process_factory(binary, *args, **kwargs):
        calls.append((binary, args, kwargs))
        process.started.set()
        return process

    allocator = FakeAllocator(events)
    session_lease = FakeSessionLease(events)
    bridge = MediaBridge(
        ffmpeg_binary="/configured/ffmpeg",
        sdp="v=0\r\n",
        port_allocator=allocator,
        session_lease=session_lease,
        track_count=2,
        process_factory=process_factory,
        response_factory=lambda: response,
    )
    return SimpleNamespace(
        bridge=bridge,
        process=process,
        response=response,
        calls=calls,
        allocator=allocator,
        session_lease=session_lease,
        events=events,
        request=SimpleNamespace(),
    )


async def test_http_200_waits_for_first_mpegts_chunk(bridge_parts):
    task = asyncio.create_task(bridge_parts.bridge.run(bridge_parts.request))
    await bridge_parts.process.started.wait()
    assert bridge_parts.response.prepared is False

    bridge_parts.process.stdout.feed(b"first-ts-chunk")
    response = await task

    assert response is bridge_parts.response
    assert bridge_parts.response.status == 200
    assert bridge_parts.response.writes == [b"first-ts-chunk"]
    assert bridge_parts.bridge.state is BridgeState.STREAMING
    await bridge_parts.bridge.request_close("test_complete")


async def test_configured_binary_exact_args_and_sdp_stdin(bridge_parts):
    task = asyncio.create_task(bridge_parts.bridge.run(bridge_parts.request))
    await bridge_parts.process.started.wait()
    bridge_parts.process.stdout.feed(b"chunk")
    await task

    binary, args, kwargs = bridge_parts.calls[0]
    assert FFMPEG_ARGS == EXPECTED_FFMPEG_ARGS
    assert binary == "/configured/ffmpeg"
    assert args == EXPECTED_FFMPEG_ARGS
    assert kwargs["stdin"] == asyncio.subprocess.PIPE
    assert kwargs["stdout"] == asyncio.subprocess.PIPE
    assert kwargs["stderr"] == asyncio.subprocess.PIPE
    assert bridge_parts.process.stdin.writes == [b"v=0\r\n"]
    assert bridge_parts.process.stdin.closed is True
    assert bridge_parts.allocator.leases[0].reservations_released is True
    await bridge_parts.bridge.request_close("test_complete")


async def test_setup_timeout_returns_504_without_http_200(bridge_parts, monkeypatch):
    monkeypatch.setattr(MediaBridge, "SETUP_TIMEOUT", 0.01)
    monkeypatch.setattr(MediaBridge, "RESPONSE_TIMEOUT", 0.02)

    response = await bridge_parts.bridge.run(bridge_parts.request)
    result = await asyncio.shield(bridge_parts.bridge.close_future)

    assert response.status == 504
    assert response.writes == []
    assert response.eof_calls == 1
    assert result.reason == "setup_timeout"


async def test_startup_failure_returns_502_after_three_attempts():
    events = []
    allocator = FakeAllocator(events)
    response = FakeResponse()
    calls = 0

    async def fail_start(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise OSError("bind failed")

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=allocator,
        session_lease=FakeSessionLease(events),
        track_count=2,
        process_factory=fail_start,
        response_factory=lambda: response,
    )

    returned = await bridge.run(SimpleNamespace())
    result = await asyncio.shield(bridge.close_future)

    assert returned.status == 502
    assert calls == 3
    assert len(allocator.leases) == 3
    assert all(lease.released for lease in allocator.leases)
    assert result.reason == "startup_failed"


async def test_first_terminal_reason_wins_and_close_is_shared(bridge_parts):
    task = asyncio.create_task(bridge_parts.bridge.run(bridge_parts.request))
    await bridge_parts.process.started.wait()
    bridge_parts.process.stdout.feed(b"chunk")
    await task

    first, second, third = await asyncio.gather(
        bridge_parts.bridge.request_close("disconnect"),
        bridge_parts.bridge.request_close("ffmpeg_exit"),
        bridge_parts.bridge.request_close("unload"),
    )

    assert first is second is third
    assert first.reason == "disconnect"
    assert bridge_parts.bridge.state is BridgeState.CLOSED
    assert bridge_parts.session_lease.released == 1
    assert bridge_parts.events[-2:] == ["ports", "session"]


async def test_cancelled_waiter_does_not_cancel_close(bridge_parts):
    release_gate = asyncio.Event()

    async def blocked_release():
        await release_gate.wait()
        bridge_parts.session_lease.released += 1
        bridge_parts.events.append("session")

    bridge_parts.session_lease.release = blocked_release
    run_task = asyncio.create_task(
        bridge_parts.bridge.run(bridge_parts.request)
    )
    await bridge_parts.process.started.wait()
    bridge_parts.process.stdout.feed(b"chunk")
    await run_task

    owner = asyncio.create_task(
        bridge_parts.bridge.request_close("disconnect")
    )
    await asyncio.sleep(0)
    waiter = asyncio.create_task(
        bridge_parts.bridge.request_close("unload")
    )
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert not bridge_parts.bridge.close_future.cancelled()

    release_gate.set()
    result = await owner
    assert result.reason == "disconnect"
    assert bridge_parts.session_lease.released == 1


async def test_failure_before_process_releases_only_owned_resources():
    events = []
    allocator = FakeAllocator(events)
    session = FakeSessionLease(events)

    async def fail_start(*_args, **_kwargs):
        raise OSError("failed")

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=allocator,
        session_lease=session,
        track_count=2,
        process_factory=fail_start,
        response_factory=FakeResponse,
        max_start_attempts=1,
    )

    await bridge.run(SimpleNamespace())
    await asyncio.shield(bridge.close_future)

    assert events == ["reservations", "ports", "session"]
    assert session.released == 1


async def test_post_200_close_does_not_replace_status(bridge_parts):
    task = asyncio.create_task(bridge_parts.bridge.run(bridge_parts.request))
    await bridge_parts.process.started.wait()
    bridge_parts.process.stdout.feed(b"chunk")
    await task

    await bridge_parts.bridge.request_close("contract_changed", startup_status=502)

    assert bridge_parts.response.status == 200
    assert bridge_parts.response.eof_calls == 1


async def test_close_result_is_immutable(bridge_parts):
    task = asyncio.create_task(bridge_parts.bridge.run(bridge_parts.request))
    await bridge_parts.process.started.wait()
    bridge_parts.process.stdout.feed(b"chunk")
    await task
    result = await bridge_parts.bridge.request_close("complete")

    with pytest.raises((AttributeError, TypeError)):
        result.reason = "changed"


async def test_normalized_frames_are_sent_to_allocated_rtp_ports():
    events: list[str] = []
    process = FakeFfmpegProcess()
    allocator = FakeAllocator(events)
    session = FakeSessionLease(events)
    sockets = [FakeDatagramSocket() for _ in range(4)]

    async def process_factory(*_args, **_kwargs):
        process.started.set()
        return process

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=allocator,
        session_lease=session,
        track_count=2,
        process_factory=process_factory,
        response_factory=FakeResponse,
        socket_factory=lambda: sockets.pop(0),
    )
    run_task = asyncio.create_task(bridge.run(SimpleNamespace()))
    await process.started.wait()
    await bridge.media_started.wait()
    owned_sockets = bridge.rtp_sockets

    await session.frames.put(
        NormalizedVideoFrame(
            data=b"\x00\x00\x00\x01\x65frame",
            pts=0,
            dts=0,
            keyframe=True,
        )
    )
    await session.frames.put(
        NormalizedAudioFrame(
            data=b"audio",
            pts=0,
            sample_rate=8000,
            channels=1,
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert owned_sockets[0].sent[0][1] == ("127.0.0.1", 5000)
    assert owned_sockets[1].sent[0][1] == ("127.0.0.1", 5001)
    assert owned_sockets[2].sent[0][1] == ("127.0.0.1", 5002)
    assert owned_sockets[3].sent[0][1] == ("127.0.0.1", 5003)
    assert all(
        len(body) <= 1200
        for udp_socket in owned_sockets
        for body, _target in udp_socket.sent
    )

    process.stdout.feed(b"chunk")
    await run_task
    await bridge.request_close("test_complete")


async def test_nonblocking_rtp_drop_is_counted():
    events: list[str] = []
    process = FakeFfmpegProcess()
    session = FakeSessionLease(events)
    sockets = [FakeDatagramSocket() for _ in range(4)]
    sockets[0].block_next = True

    async def process_factory(*_args, **_kwargs):
        process.started.set()
        return process

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=FakeAllocator(events),
        session_lease=session,
        track_count=2,
        process_factory=process_factory,
        response_factory=FakeResponse,
        socket_factory=lambda: sockets.pop(0),
    )
    task = asyncio.create_task(bridge.run(SimpleNamespace()))
    await process.started.wait()
    await bridge.media_started.wait()
    await session.frames.put(
        NormalizedVideoFrame(
            data=b"\x00\x00\x00\x01\x65frame",
            pts=0,
            dts=0,
            keyframe=True,
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert bridge.rtp_drop_count == 1

    process.stdout.feed(b"chunk")
    await task
    await bridge.request_close("test_complete")


async def test_contract_change_closes_bridge_before_http_200():
    events: list[str] = []
    process = FakeFfmpegProcess()
    session = FakeSessionLease(events)

    async def process_factory(*_args, **_kwargs):
        process.started.set()
        return process

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=FakeAllocator(events),
        session_lease=session,
        track_count=2,
        process_factory=process_factory,
        response_factory=FakeResponse,
    )
    task = asyncio.create_task(bridge.run(SimpleNamespace()))
    await process.started.wait()
    session.contract_changed.set()

    response = await asyncio.wait_for(task, 0.2)
    result = await asyncio.shield(bridge.close_future)

    assert response.status == 502
    assert result.reason == "contract_changed"


async def test_early_ffmpeg_exit_retries_without_close_deadlock():
    events: list[str] = []
    allocator = FakeAllocator(events)
    processes = [FakeFfmpegProcess(), FakeFfmpegProcess()]
    starts = 0

    async def process_factory(*_args, **_kwargs):
        nonlocal starts
        process = processes[starts]
        starts += 1
        process.started.set()
        if starts == 1:
            asyncio.get_running_loop().call_soon(process.exit, 1)
        return process

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=allocator,
        session_lease=FakeSessionLease(events),
        track_count=2,
        process_factory=process_factory,
        response_factory=FakeResponse,
    )
    task = asyncio.create_task(bridge.run(SimpleNamespace()))
    await processes[1].started.wait()
    processes[1].stdout.feed(b"chunk")

    response = await asyncio.wait_for(task, 0.2)

    assert response.status == 200
    assert starts == 2
    assert allocator.leases[0].released is True
    await bridge.request_close("test_complete")


async def test_process_start_is_bounded_by_setup_deadline(monkeypatch):
    events: list[str] = []
    entered = asyncio.Event()

    async def blocked_start(*_args, **_kwargs):
        entered.set()
        await asyncio.Future()

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=FakeAllocator(events),
        session_lease=FakeSessionLease(events),
        track_count=2,
        process_factory=blocked_start,
        response_factory=FakeResponse,
    )
    monkeypatch.setattr(MediaBridge, "SETUP_TIMEOUT", 0.03)
    monkeypatch.setattr(MediaBridge, "FFMPEG_RESERVE", 0.0)
    monkeypatch.setattr(MediaBridge, "RESPONSE_TIMEOUT", 0.05)

    task = asyncio.create_task(bridge.run(SimpleNamespace()))
    await entered.wait()
    response = await asyncio.wait_for(task, 0.2)

    assert response.status == 504
    assert (await asyncio.shield(bridge.close_future)).reason == "setup_timeout"


async def test_close_cancels_blocked_stdout_write_before_eof():
    events: list[str] = []
    process = FakeFfmpegProcess()
    first_written = asyncio.Event()
    second_started = asyncio.Event()
    second_cancelled = asyncio.Event()

    class BlockingResponse(FakeResponse):
        async def write(self, chunk: bytes) -> None:
            if not self.writes:
                self.writes.append(chunk)
                first_written.set()
                return
            second_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                second_cancelled.set()
                raise

    async def process_factory(*_args, **_kwargs):
        process.started.set()
        return process

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=FakeAllocator(events),
        session_lease=FakeSessionLease(events),
        track_count=2,
        process_factory=process_factory,
        response_factory=BlockingResponse,
    )
    task = asyncio.create_task(bridge.run(SimpleNamespace()))
    await process.started.wait()
    process.stdout.feed(b"first")
    await task
    await first_written.wait()
    process.stdout.feed(b"blocked")
    await second_started.wait()

    result = await asyncio.wait_for(
        bridge.request_close("disconnect"),
        0.2,
    )

    assert result.reason == "disconnect"
    assert second_cancelled.is_set()
    assert bridge.response.eof_calls == 1


async def test_stream_close_uses_fresh_eof_timeout_after_response_deadline():
    now = 0.0
    events: list[str] = []
    process = FakeFfmpegProcess()

    async def process_factory(*_args, **_kwargs):
        process.started.set()
        return process

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=FakeAllocator(events),
        session_lease=FakeSessionLease(events),
        track_count=2,
        process_factory=process_factory,
        response_factory=FakeResponse,
        clock=lambda: now,
    )
    task = asyncio.create_task(bridge.run(SimpleNamespace()))
    await process.started.wait()
    process.stdout.feed(b"chunk")
    await task
    now = 30.0

    result = await bridge.request_close("disconnect")

    assert result.cleanup_failed is False
    assert bridge.response.eof_calls == 1


async def test_retry_replaces_failed_attempt_datagram_sockets():
    events: list[str] = []
    allocator = FakeAllocator(events)
    processes = [FakeFfmpegProcess(), FakeFfmpegProcess()]
    sockets = [FakeDatagramSocket() for _ in range(8)]
    created: list[FakeDatagramSocket] = []
    starts = 0

    def socket_factory():
        udp_socket = sockets.pop(0)
        created.append(udp_socket)
        return udp_socket

    async def process_factory(*_args, **_kwargs):
        nonlocal starts
        process = processes[starts]
        starts += 1
        process.started.set()
        if starts == 1:
            asyncio.get_running_loop().call_soon(process.exit, 1)
        return process

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=allocator,
        session_lease=FakeSessionLease(events),
        track_count=2,
        process_factory=process_factory,
        response_factory=FakeResponse,
        socket_factory=socket_factory,
    )
    task = asyncio.create_task(bridge.run(SimpleNamespace()))
    await processes[1].started.wait()
    processes[1].stdout.feed(b"chunk")
    await task

    assert len(created) == 8
    assert all(udp_socket.closed for udp_socket in created[:4])
    assert all(not udp_socket.closed for udp_socket in created[4:])
    await bridge.request_close("test_complete")


async def test_exit_after_first_chunk_is_startup_failure():
    events: list[str] = []
    process = FakeFfmpegProcess()

    async def process_factory(*_args, **_kwargs):
        process.started.set()
        return process

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=FakeAllocator(events),
        session_lease=FakeSessionLease(events),
        track_count=2,
        process_factory=process_factory,
        response_factory=FakeResponse,
        max_start_attempts=1,
    )
    task = asyncio.create_task(bridge.run(SimpleNamespace()))
    await process.started.wait()
    process.stdout.feed(b"chunk")
    process.exit(1)

    response = await task

    assert response.status == 502
    assert response.writes == []


async def test_failed_stream_eof_forces_transport_close():
    events: list[str] = []
    process = FakeFfmpegProcess()

    class FailingEofResponse(FakeResponse):
        def __init__(self) -> None:
            super().__init__()
            self.force_close_calls = 0

        async def write_eof(self) -> None:
            raise ConnectionError("disconnected")

        def force_close(self) -> None:
            self.force_close_calls += 1

    async def process_factory(*_args, **_kwargs):
        process.started.set()
        return process

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=FakeAllocator(events),
        session_lease=FakeSessionLease(events),
        track_count=2,
        process_factory=process_factory,
        response_factory=FailingEofResponse,
    )
    class FakeTransport:
        def __init__(self) -> None:
            self.abort_calls = 0

        def abort(self) -> None:
            self.abort_calls += 1

    request = SimpleNamespace(transport=FakeTransport())
    task = asyncio.create_task(bridge.run(request))
    await process.started.wait()
    process.stdout.feed(b"chunk")
    await task

    result = await bridge.request_close("disconnect")

    assert result.cleanup_failed is True
    assert bridge.response.force_close_calls == 1
    assert request.transport.abort_calls == 1


async def test_exit_during_response_prepare_closes_stream():
    events: list[str] = []
    process = FakeFfmpegProcess()
    prepare_started = asyncio.Event()
    finish_prepare = asyncio.Event()

    class BlockingPrepareResponse(FakeResponse):
        async def prepare(self, _request):
            prepare_started.set()
            await finish_prepare.wait()
            self.prepared = True
            return self

    async def process_factory(*_args, **_kwargs):
        process.started.set()
        return process

    bridge = MediaBridge(
        ffmpeg_binary="ffmpeg",
        sdp="v=0\r\n",
        port_allocator=FakeAllocator(events),
        session_lease=FakeSessionLease(events),
        track_count=2,
        process_factory=process_factory,
        response_factory=BlockingPrepareResponse,
    )
    task = asyncio.create_task(bridge.run(SimpleNamespace()))
    await process.started.wait()
    process.stdout.feed(b"chunk")
    await prepare_started.wait()
    process.exit(1)
    await asyncio.sleep(0)
    finish_prepare.set()

    await task
    result = await asyncio.wait_for(bridge.close_future, 0.2)

    assert result.reason == "ffmpeg_exit"
    assert bridge.state is BridgeState.CLOSED
