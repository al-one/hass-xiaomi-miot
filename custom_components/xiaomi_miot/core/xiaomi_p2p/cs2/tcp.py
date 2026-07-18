"""Established CS2 TCP transport.

`TcpCs2Transport` is constructed by `DefaultCs2Connector` after a
single successful discovery exchange. Frames on the TCP wire are pure
DRW (no CS2 prefix): the bounded parser consumes the ordered byte
stream directly. While processing writes the transport emits an
opportunistic reference-compatible DRW ping at most once per second;
no independent keepalive is scheduled.
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass
from typing import Optional

from .. import MissError, MissErrorCategory
from .bounds import COMMAND_QUEUE_LIMIT, MEDIA_QUEUE_LIMIT
from .protocol import (
    BoundedDrwParser,
    DRW_MAGIC_COMMAND,
    DRW_MAGIC_MEDIA,
    DRW_MAGIC_PING,
    Cs2Command,
    Cs2MediaPacket,
    decode_inbound_cs2_command,
)


_STRUCT_DRW_HEADER = struct.Struct(">2sHI")
_STRUCT_COMMAND_ID_BE = struct.Struct(">I")


PING_INTERVAL_SECONDS: float = 1.0


class TcpCs2Transport:
    """TCP transport for an already-discovered CS2 peer.

    Inbound frames are read from `reader` and fed directly to a
    `BoundedDrwParser`. Outbound frames are wrapped in a DRW header and
    written to `writer`, coalesced with an opportunistic ping when more
    than `PING_INTERVAL_SECONDS` has elapsed since the last ping.
    """

    negotiated_mode = "tcp"

    def __init__(
        self,
        *,
        reader,
        writer,
        clock,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._clock = clock
        self._parser = BoundedDrwParser()
        self._next_sequence: int = 0
        self._last_ping_at: Optional[float] = None
        self._command_queue: asyncio.Queue = asyncio.Queue(maxsize=COMMAND_QUEUE_LIMIT)
        self._media_queue: asyncio.Queue = asyncio.Queue(maxsize=MEDIA_QUEUE_LIMIT)
        self._closed = False
        self._reader_task: Optional[asyncio.Task] = None
        self._failed_with: Optional[MissError] = None

    # ---- Public surface ------------------------------------------------

    async def read_command(self, timeout: float | None = None) -> Cs2Command:
        return await self._dequeue(self._command_queue, timeout)

    async def write_command(self, command: Cs2Command) -> None:
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        body = _STRUCT_COMMAND_ID_BE.pack(command.command_id) + command.payload
        await self._send_frame(DRW_MAGIC_COMMAND, body)

    async def read_media_packet(self, timeout: float | None = None) -> Cs2MediaPacket:
        return await self._dequeue(self._media_queue, timeout)

    async def write_media_packet(self, packet: Cs2MediaPacket) -> None:
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        body = packet.header + packet.encrypted_body
        await self._send_frame(DRW_MAGIC_MEDIA, body)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
        try:
            if not self._writer.is_closing():
                self._writer.close()
            await self._writer.wait_closed()
        except Exception:  # pragma: no cover - defensive
            pass
        if self._failed_with is None:
            self._failed_with = MissError(
                MissErrorCategory.TRANSPORT, "transport_closed"
            )
        self._fail_queue_sync(self._command_queue)
        self._fail_queue_sync(self._media_queue)

    # ---- Internals -----------------------------------------------------

    def start_reader(self) -> None:
        if self._reader_task is None:
            self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            while not self._closed:
                try:
                    chunk = await self._reader.read(4096)
                except asyncio.IncompleteReadError:
                    self._mark_eof()
                    return
                except asyncio.CancelledError:
                    return
                except ConnectionError:
                    self._mark_eof()
                    return
                if not chunk:
                    self._mark_eof()
                    return
                try:
                    await self._process_chunk(chunk)
                except MissError as exc:
                    self._failed_with = exc
                    self._fail_queue_sync(self._command_queue)
                    self._fail_queue_sync(self._media_queue)
                    return
        except asyncio.CancelledError:
            return

    async def _process_chunk(self, chunk: bytes) -> None:
        self._parser.feed(chunk)
        try:
            frames = list(self._parser.drain())
        except MissError as exc:
            raise exc
        for frame in frames:
            if frame.magic == DRW_MAGIC_COMMAND:
                await self._enqueue_command(decode_inbound_cs2_command(frame.payload))
            elif frame.magic == DRW_MAGIC_MEDIA:
                if len(frame.payload) < 32:
                    continue
                await self._enqueue_media(
                    Cs2MediaPacket(
                        header=frame.payload[:32],
                        encrypted_body=frame.payload[32:],
                    )
                )
            # Other channels (e.g. DRW_MAGIC_PING) are silently ignored
            # — pings are outbound-only in this transport.

    def _mark_eof(self) -> None:
        if self._failed_with is None:
            self._failed_with = MissError(
                MissErrorCategory.TRANSPORT, "connection_lost"
            )
        self._fail_queue_sync(self._command_queue)
        self._fail_queue_sync(self._media_queue)

    async def _send_frame(self, magic: bytes, body: bytes) -> None:
        # Opportunistic ping: at most once per second while processing writes.
        now = self._clock.now
        if self._last_ping_at is None or now - self._last_ping_at >= PING_INTERVAL_SECONDS:
            ping_seq = self._next_sequence
            self._next_sequence = (ping_seq + 1) & 0xFFFF
            ping_frame = _STRUCT_DRW_HEADER.pack(DRW_MAGIC_PING, ping_seq, 0)
            self._writer.write(ping_frame)
            self._last_ping_at = now

        seq = self._next_sequence
        self._next_sequence = (seq + 1) & 0xFFFF
        frame = _STRUCT_DRW_HEADER.pack(magic, seq, len(body)) + body
        self._writer.write(frame)
        await self._writer.drain()

    async def _enqueue_command(self, command: Cs2Command) -> None:
        if self._closed:
            return
        try:
            self._command_queue.put_nowait(command)
        except asyncio.QueueFull:
            raise MissError(MissErrorCategory.TRANSPORT, "command_queue_overflow")

    async def _enqueue_media(self, packet: Cs2MediaPacket) -> None:
        if self._closed:
            return
        try:
            self._media_queue.put_nowait(packet)
        except asyncio.QueueFull:
            raise MissError(MissErrorCategory.TRANSPORT, "media_queue_overflow")

    async def _dequeue(self, queue: asyncio.Queue, timeout: float | None):
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        if self._failed_with is not None:
            raise self._failed_with
        try:
            if timeout is None:
                item = await queue.get()
            else:
                item = await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise MissError(MissErrorCategory.TIMEOUT, "read_timeout") from exc
        if self._failed_with is not None:
            raise self._failed_with
        if isinstance(item, _ClosedSentinel):
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        return item

    @staticmethod
    def _fail_queue_sync(queue: asyncio.Queue) -> None:
        try:
            queue.put_nowait(_CLOSED_SENTINEL)
        except asyncio.QueueFull:  # pragma: no cover - queue already full
            pass


@dataclass(frozen=True)
class _ClosedSentinel:
    pass


_CLOSED_SENTINEL = _ClosedSentinel()


__all__ = ["TcpCs2Transport", "PING_INTERVAL_SECONDS"]
