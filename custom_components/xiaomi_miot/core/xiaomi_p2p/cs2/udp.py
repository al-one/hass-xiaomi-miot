"""Established CS2 UDP transport.

The UDP transport is constructed by ``DefaultCs2Connector`` after a
successful LanSearch handshake (see ``discovery.py``). Once the handshake
completes, the peer endpoint is locked for the lifetime of the transport;
datagrams from any other source are discarded before parsing.

Frame layout on the wire:

  Outer (UDP datagram):
      [0xF1]                   magic
      [0xD0]                   msgDrw
      [BE uint16]              total body length including itself
      [0xD1]                   DRW magic
      [channel byte]           channel id (0 = commands, 2 = media, 3 = tx media)
      [BE uint16]              sequence number
      [BE uint32]              payload length
      [N bytes]                payload

The transport maintains a small reordering window for out-of-order UDP
delivery and replies with ACK frames carrying the channel + sequence.  For
TCP transports the ACK step is skipped (TCP is reliable).
"""

from __future__ import annotations

import asyncio
import logging
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
)
from .protocol import (
    CHANNEL_COMMAND,
    CHANNEL_MEDIA,
    Cs2Command,
    Cs2MediaPacket,
    MAGIC,
    MSG_DRW,
    MSG_DRW_ACK,
    decode_inbound_cs2_command,
    decode_miss_media_header,
    encode_command,
    encode_drw_frame,
    encode_msg,
    sequence_distance,
)

_LOGGER = logging.getLogger(__name__)


_STRUCT_ACK_CHANNEL = struct.Struct(">B")
_STRUCT_ACK_SEQ = struct.Struct(">H")
_STRUCT_PAYLOAD_LEN = struct.Struct(">I")
_STRUCT_TOTAL_LEN = struct.Struct(">H")


@dataclass(frozen=True)
class _ClosedSentinel:
    """Wake-up marker pushed into the command/media queues at close time."""


_CLOSED_SENTINEL = _ClosedSentinel()


class UdpCs2Transport:
    """UDP transport for an already-discovered CS2 peer."""

    negotiated_mode = "udp"

    def __init__(
        self,
        *,
        sock,
        peer_addr: tuple[str, int],
        clock,
        retransmit_after=None,
        gap_after=None,
        ack_callback=None,
        rejection_callback=None,
    ) -> None:
        self._sock = sock
        self._peer_addr: tuple[str, int] = (peer_addr[0], int(peer_addr[1]))
        self._clock = clock
        self._retransmit_after = retransmit_after
        self._gap_after = gap_after
        self._ack_callback = ack_callback
        self._rejection_callback = rejection_callback

        self._seq_ch0: int = 0  # next outbound command sequence
        self._seq_ch3: int = 0  # next outbound media sequence
        self._rcv_seq_ch0: int = 0  # next expected inbound command sequence
        self._rcv_seq_ch2: int = 0  # next expected inbound media sequence
        self._reorder_buffer: dict[int, tuple[int, bytes]] = {}
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
        self._cmd_ack_callback = None  # set per-WriteCommand by the caller

    @property
    def _next_sequence(self) -> int:
        return self._rcv_seq_ch0

    @_next_sequence.setter
    def _next_sequence(self, value: int) -> None:
        self._rcv_seq_ch0 = value

    # ---- Public surface ------------------------------------------------

    @property
    def rejected_peer_datagrams(self) -> int:
        return self._rejected

    async def read_command(self, timeout: float | None = None) -> Cs2Command:
        return await self._dequeue(self._command_queue, timeout)

    async def write_command(self, command: Cs2Command) -> None:
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        seq = self._seq_ch0
        self._seq_ch0 = (self._seq_ch0 + 1) & 0xFFFF
        frame = encode_command(
            command.command_id, command.payload, sequence=seq
        )
        await self._send_datagram(frame)

    async def read_media_packet(self, timeout: float | None = None) -> Cs2MediaPacket:
        return await self._dequeue(self._media_queue, timeout)

    async def write_media_packet(self, packet: Cs2MediaPacket) -> None:
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        seq = self._seq_ch3
        self._seq_ch3 = (self._seq_ch3 + 1) & 0xFFFF
        # Channel 3 carries outbound media; same DRW layout as channel 0/2
        # but we pre-concatenate the 32-byte header + encrypted body.
        body = packet.header + packet.encrypted_body
        frame = encode_drw_frame(3, seq, body)
        await self._send_datagram(frame)

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
                if addr[0] != self._peer_addr[0] or addr[1] != self._peer_addr[1]:
                    self._rejected += 1
                    if self._rejection_callback is not None:
                        self._rejection_callback(addr)
                    continue
                await self._process_payload(payload)
        except asyncio.CancelledError:
            return

    async def _process_payload(self, payload: bytes) -> None:
        if len(payload) < 2:
            return
        if payload[0] != MAGIC:
            return
        kind = payload[1]
        body = payload[2:]

        if kind == MSG_DRW:
            await self._process_drw(body)
        elif kind == MSG_DRW_ACK:
            # Acknowledgement of an outbound DRW frame; we don't currently
            # use it to gate retransmits because UDP here is on the LAN.
            return
        # Other kinds (PING / PONG / CLOSE etc.) are silently ignored.

    async def _process_drw(self, body: bytes) -> None:
        # Layout: [BE uint16 total_len][0xD1][channel][BE uint16 seq]
        #         [BE uint32 payload_len][payload]
        if len(body) < 8:
            return
        total_len = _STRUCT_TOTAL_LEN.unpack_from(body, 0)[0]
        if total_len < 8 or total_len > len(body):
            return
        if body[2] != 0xD1:
            return
        channel = body[3]
        sequence = (body[4] << 8) | body[5]
        payload_len = _STRUCT_PAYLOAD_LEN.unpack_from(body, 6)[0]
        if payload_len > total_len - 8:
            return
        payload = body[8:8 + payload_len]
        await self._send_ack(channel, sequence)

        if channel == CHANNEL_COMMAND:
            self._deliver_command(sequence, payload)
        elif channel == CHANNEL_MEDIA:
            self._deliver_media(sequence, payload)
        # Other channels (3 = peer media) are ignored on the receive path.

    async def _send_ack(self, channel: int, sequence: int) -> None:
        # Layout: 0xF1 0xD1 [channel] [seq_hi] [seq_lo]
        try:
            await self._sock.sendto(
                encode_msg(
                    MSG_DRW_ACK,
                    _STRUCT_ACK_CHANNEL.pack(channel)
                    + _STRUCT_ACK_SEQ.pack(sequence),
                ),
                self._peer_addr,
            )
        except Exception:  # pragma: no cover - best effort
            pass

    def _deliver_command(self, sequence: int, body: bytes) -> None:
        distance = sequence_distance(self._rcv_seq_ch0, sequence)
        if distance == 0:
            self._rcv_seq_ch0 = (sequence + 1) & 0xFFFF
            self._enqueue_command(decode_inbound_cs2_command(body))
            self._drain_command_contiguous()
        elif distance > 0:
            self._buffer_future(sequence, CHANNEL_COMMAND, body)
        # distance < 0 (duplicate) — drop.

    def _deliver_media(self, sequence: int, body: bytes) -> None:
        if len(body) < 32:
            return
        try:
            decode_miss_media_header(body[:32])
        except MissError:
            return
        pkt = Cs2MediaPacket(header=body[:32], encrypted_body=body[32:])
        distance = sequence_distance(self._rcv_seq_ch2, sequence)
        if distance == 0:
            self._rcv_seq_ch2 = (sequence + 1) & 0xFFFF
            self._enqueue_media(pkt)
            self._drain_media_contiguous()
        elif distance > 0:
            self._buffer_future(sequence, CHANNEL_MEDIA, pkt)

    def _buffer_future(self, sequence: int, channel: int, body) -> None:
        if len(self._reorder_buffer) >= REORDER_PACKET_LIMIT:
            self._fail_sequence_gap()
            return
        if channel == CHANNEL_MEDIA and not isinstance(body, Cs2MediaPacket):
            return
        size = len(body) if isinstance(body, (bytes, bytearray)) else len(body.header) + len(body.encrypted_body)
        if self._reorder_bytes + size > REORDER_BYTE_LIMIT:
            self._fail_sequence_gap()
            return
        self._reorder_buffer[sequence] = (channel, body)
        self._reorder_bytes += size
        if self._gap_deadline is None:
            self._gap_deadline = self._clock.now + GAP_DEADLINE_SECONDS
            self._start_gap_deadline_task()

    def _start_gap_deadline_task(self) -> None:
        task = asyncio.ensure_future(self._gap_deadline_watcher())
        self._gap_deadline_task = task

    async def _gap_deadline_watcher(self) -> None:
        try:
            while (
                self._gap_deadline is not None
                and not self._closed
                and self._reorder_buffer
            ):
                remaining = self._gap_deadline - self._clock.now
                if remaining <= 0:
                    self._fail_sequence_gap()
                    return
                await asyncio.sleep(min(remaining, 0.05))
        except asyncio.CancelledError:
            return

    def _cancel_gap_deadline(self) -> None:
        self._gap_deadline = None
        if self._gap_deadline_task is not None and not self._gap_deadline_task.done():
            self._gap_deadline_task.cancel()

    def _drain_command_contiguous(self) -> None:
        while True:
            entry = self._reorder_buffer.pop(0, None)
            if entry is None:
                if not self._reorder_buffer:
                    self._cancel_gap_deadline()
                return
            channel, body = entry
            if channel != CHANNEL_COMMAND:
                continue
            self._enqueue_command(decode_inbound_cs2_command(body))

    def _drain_media_contiguous(self) -> None:
        while True:
            entry = self._reorder_buffer.pop(0, None)
            if entry is None:
                if not self._reorder_buffer:
                    self._cancel_gap_deadline()
                return
            channel, pkt = entry
            if channel != CHANNEL_MEDIA or not isinstance(pkt, Cs2MediaPacket):
                continue
            self._enqueue_media(pkt)

    def _fail_sequence_gap(self) -> None:
        self._reorder_buffer.clear()
        self._reorder_bytes = 0
        self._gap_deadline = None
        self._failed_with = MissError(MissErrorCategory.TRANSPORT, "sequence_gap")
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()

    async def _send_datagram(self, frame: bytes) -> None:
        try:
            await self._sock.sendto(frame, self._peer_addr)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_send_failed") from exc

    def _enqueue_command(self, command: Cs2Command) -> None:
        if self._closed:
            return
        try:
            self._command_queue.put_nowait(command)
        except asyncio.QueueFull:
            raise MissError(MissErrorCategory.TRANSPORT, "command_queue_overflow")

    def _enqueue_media(self, packet: Cs2MediaPacket) -> None:
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
        try:
            queue.put_nowait(_CLOSED_SENTINEL)
        except asyncio.QueueFull:  # pragma: no cover - queue already drained
            pass


__all__ = ["UdpCs2Transport"]