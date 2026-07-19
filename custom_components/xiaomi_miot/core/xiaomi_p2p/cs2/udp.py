"""Established CS2 UDP transport.

`UdpCs2Transport` is constructed by `DefaultCs2Connector` after a
single successful discovery exchange. The peer endpoint is locked for
the lifetime of the transport; datagrams from any other source are
discarded before parsing.
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass
from typing import Optional

from .. import MissError, MissErrorCategory
from .bounds import (
    COMMAND_QUEUE_LIMIT,
    GAP_DEADLINE_SECONDS,
    MEDIA_QUEUE_LIMIT,
    REORDER_BYTE_LIMIT,
    REORDER_PACKET_LIMIT,
    RETRANSMIT_INTERVAL_SECONDS,
    RETRANSMIT_LIMIT,
)
from .protocol import (
    CS2_FRAME_MAGIC,
    DRW_MAGIC_COMMAND,
    DRW_MAGIC_MEDIA,
    Cs2Command,
    Cs2MediaPacket,
    decode_inbound_cs2_command,
    decode_miss_media_header,
    encode_outbound_cs2_command,
    sequence_distance,
)


_STRUCT_DRW_SEQ = struct.Struct(">H")
_STRUCT_ACK = struct.Struct(">HH")


class UdpCs2Transport:
    """UDP transport for an already-discovered CS2 peer."""

    negotiated_mode = "udp"

    def __init__(
        self,
        *,
        sock,
        peer_addr: tuple[str, int],
        clock,
        retransmit_after,
        gap_after,
        ack_callback=None,
        rejection_callback=None,
    ) -> None:
        self._sock = sock
        self._peer_addr = tuple(peer_addr)
        self._clock = clock
        self._retransmit_after = retransmit_after
        self._gap_after = gap_after
        self._ack_callback = ack_callback
        self._rejection_callback = rejection_callback

        self._next_sequence: int = 0
        self._reorder_buffer: dict[int, bytes] = {}
        self._reorder_bytes: int = 0
        self._command_queue: asyncio.Queue = asyncio.Queue(maxsize=COMMAND_QUEUE_LIMIT)
        self._media_queue: asyncio.Queue = asyncio.Queue(maxsize=MEDIA_QUEUE_LIMIT)
        self._gap_deadline: Optional[float] = None
        self._gap_deadline_task: Optional[asyncio.Task] = None
        self._closed = False
        self._close_event = asyncio.Event()
        self._reader_task: Optional[asyncio.Task] = None
        self._rejected = 0
        self._failed_with: Optional[MissError] = None

    # ---- Public surface ------------------------------------------------

    @property
    def rejected_peer_datagrams(self) -> int:
        return self._rejected

    async def read_command(self, timeout: float | None = None) -> Cs2Command:
        return await self._dequeue(self._command_queue, timeout)

    async def write_command(self, command: Cs2Command) -> None:
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        frame = encode_outbound_cs2_command(
            command.command_id, command.payload, sequence=self._next_sequence
        )
        await self._send_with_retransmit(frame)
        self._next_sequence = (self._next_sequence + 1) & 0xFFFF

    async def read_media_packet(self, timeout: float | None = None) -> Cs2MediaPacket:
        return await self._dequeue(self._media_queue, timeout)

    async def write_media_packet(self, packet: Cs2MediaPacket) -> None:
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        frame = (
            CS2_FRAME_MAGIC
            + DRW_MAGIC_MEDIA
            + self._next_sequence.to_bytes(2, "big")
            + packet.header
            + packet.encrypted_body
        )
        await self._send_with_retransmit(frame)
        self._next_sequence = (self._next_sequence + 1) & 0xFFFF

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._reorder_buffer.clear()
        self._reorder_bytes = 0
        self._gap_deadline = None
        self._close_event.set()
        try:
            self._sock.close()
        except Exception:  # pragma: no cover - defensive
            pass
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
        # Drain queues with the closed sentinel so waiters wake up.
        while not self._command_queue.empty():
            try:
                self._command_queue.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover
                break
        while not self._media_queue.empty():
            try:
                self._media_queue.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover
                break
        await self._fail_queue(self._command_queue)
        await self._fail_queue(self._media_queue)

    # ---- Internals -----------------------------------------------------

    def start_reader(self) -> None:
        if self._reader_task is None:
            self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            while not self._closed:
                try:
                    payload, addr = await self._sock.recvfrom()
                except asyncio.IncompleteReadError:
                    return
                except asyncio.CancelledError:
                    return
                except Exception:  # pragma: no cover - defensive
                    return
                if addr != self._peer_addr:
                    self._rejected += 1
                    if self._rejection_callback is not None:
                        self._rejection_callback(addr)
                    continue
                await self._process_payload(payload)
        except asyncio.CancelledError:
            return

    async def _process_payload(self, payload: bytes) -> None:
        if len(payload) < 12:
            return
        # CS2 prefix: [magic 2][outer_len 2] then DRW framing.
        if payload[0:2] != CS2_FRAME_MAGIC:
            return
        magic = payload[4:6]
        sequence = _STRUCT_DRW_SEQ.unpack_from(payload, 6)[0]
        if magic == DRW_MAGIC_COMMAND:
            body = payload[12:]
            self._ack(sequence)
            distance = sequence_distance(self._next_sequence, sequence)
            if distance == 0:
                self._next_sequence = (sequence + 1) & 0xFFFF
                await self._enqueue_command(decode_inbound_cs2_command(body))
                await self._drain_contiguous()
            elif distance > 0:
                await self._buffer_future(sequence, body)
            # distance < 0 (duplicate or already delivered) — silently ACK'd.
        elif magic == DRW_MAGIC_MEDIA:
            self._ack(sequence)
            if len(payload) < 44:
                return
            try:
                decode_miss_media_header(payload[12:44])
            except MissError:
                return
            pkt = Cs2MediaPacket(header=payload[12:44], encrypted_body=payload[44:])
            distance = sequence_distance(self._next_sequence, sequence)
            if distance == 0:
                self._next_sequence = (sequence + 1) & 0xFFFF
                await self._enqueue_media(pkt)
                await self._drain_contiguous()
            elif distance > 0:
                await self._buffer_future(sequence, payload[12:])

    async def _buffer_future(self, sequence: int, body: bytes) -> None:
        if len(self._reorder_buffer) >= REORDER_PACKET_LIMIT:
            self._fail_sequence_gap()
        if self._reorder_bytes + len(body) > REORDER_BYTE_LIMIT:
            self._fail_sequence_gap()
        self._reorder_buffer[sequence] = body
        self._reorder_bytes += len(body)
        if self._gap_deadline is None:
            self._gap_deadline = self._clock.now + GAP_DEADLINE_SECONDS
            self._start_gap_deadline_task()

    def _start_gap_deadline_task(self) -> None:
        if self._gap_deadline_task is not None and not self._gap_deadline_task.done():
            self._gap_deadline_task.cancel()
        self._gap_deadline_task = asyncio.create_task(self._gap_deadline_watcher())

    async def _gap_deadline_watcher(self) -> None:
        # Poll the deadline using the remaining time so that whichever
        # actor advances the clock (the watcher itself or the test)
        # triggers the gap failure when the deadline is reached.
        try:
            while self._gap_deadline is not None and not self._closed:
                if self._clock.now >= self._gap_deadline:
                    self._fail_sequence_gap()
                    return
                remaining = self._gap_deadline - self._clock.now
                if remaining > 0:
                    await self._clock.sleep(remaining)
        except asyncio.CancelledError:
            return

    async def _drain_contiguous(self) -> None:
        # Pop sequences from the buffer in strict order starting at the
        # next expected sequence. A missing sequence (e.g. seq 2 with seq
        # 3 buffered) leaves the gap open until that sequence arrives.
        while self._next_sequence in self._reorder_buffer:
            body = self._reorder_buffer.pop(self._next_sequence)
            self._reorder_bytes -= len(body)
            # Commands have no media header (first 4 bytes = LE id). Media
            # carries a 32-byte header. Default to media for safety.
            if len(body) >= 4 and self._looks_like_command(body):
                await self._enqueue_command(decode_inbound_cs2_command(body))
            else:
                await self._enqueue_media(
                    Cs2MediaPacket(header=body[:32], encrypted_body=body[32:])
                )
            self._next_sequence = (self._next_sequence + 1) & 0xFFFF
        # If anything remains in the buffer, there's still a gap waiting
        # to be filled; otherwise the gap closed completely.
        if self._reorder_buffer:
            self._gap_deadline = self._clock.now + GAP_DEADLINE_SECONDS
            self._start_gap_deadline_task()
        else:
            self._gap_deadline = None
            if self._gap_deadline_task is not None and not self._gap_deadline_task.done():
                self._gap_deadline_task.cancel()

    @staticmethod
    def _looks_like_command(body: bytes) -> bool:
        # Commands arrive without media headers; their first 4 bytes are the
        # LE command id (a small positive integer in practice). Media packets
        # carry a 32-byte header. We default to media for safety.
        return len(body) < 32

    def _fail_sequence_gap(self) -> None:
        # Clear local state; the connection's gap recovery is the connector's
        # responsibility (reconnect).
        self._reorder_buffer.clear()
        self._reorder_bytes = 0
        self._gap_deadline = None
        if self._gap_deadline_task is not None and not self._gap_deadline_task.done():
            self._gap_deadline_task.cancel()
        # Mark the transport as failed so any pending reads observe the
        # failure rather than waiting forever.
        self._failed_with = MissError(MissErrorCategory.TRANSPORT, "sequence_gap")
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()

    def _ack(self, sequence: int) -> None:
        if self._ack_callback is not None:
            self._ack_callback(self._peer_addr, sequence)

    async def _send_with_retransmit(self, frame: bytes) -> None:
        attempts = 0
        while True:
            attempts += 1
            try:
                await self._sock.sendto(frame, self._peer_addr)
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempts >= RETRANSMIT_LIMIT:
                    raise MissError(MissErrorCategory.TRANSPORT, "transport_send_failed")
                delay = self._retransmit_after(RETRANSMIT_INTERVAL_SECONDS)
                if asyncio.isfuture(delay) or asyncio.iscoroutine(delay):
                    await delay

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

    async def _fail_queue(self, queue: asyncio.Queue) -> None:
        # Inject a sentinel-like wakeup by closing the queue indirectly; we
        # use a private wakeup sentinel stored in the queue.
        try:
            queue.put_nowait(_CLOSED_SENTINEL)
        except asyncio.QueueFull:  # pragma: no cover - queue already drained
            pass


@dataclass(frozen=True)
class _ClosedSentinel:
    pass


_CLOSED_SENTINEL = _ClosedSentinel()


__all__ = ["UdpCs2Transport"]
