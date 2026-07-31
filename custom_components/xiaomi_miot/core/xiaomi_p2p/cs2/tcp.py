"""Established CS2 TCP transport.

The TCP transport is constructed by ``DefaultCs2Connector`` after a
successful LanSearch handshake when the camera accepts the TCP ready
packet.  On the wire each frame is:

  [BE uint16 body length][0x68 magicTCP][6 bytes reserved][frame body]

where ``frame body`` is a DRW frame (see ``protocol.py``).  The transport
parses inbound frames into channel-0 commands and channel-2 media
packets; outbound frames are wrapped in DRW headers and written via the
``StreamWriter`` (no extra header bytes because ``magicTCP`` is
provided by the outer TCP frame, not the inner DRW frame).

While processing writes, the transport emits an opportunistic ping
every second to keep the connection alive (mirroring the go2rtc TCP
keepalive).
"""

from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass
from typing import Optional

from .. import MissError, MissErrorCategory
from .bounds import COMMAND_QUEUE_LIMIT, MEDIA_QUEUE_LIMIT
from .protocol import (
    CHANNEL_COMMAND,
    CHANNEL_MEDIA,
    Cs2Command,
    Cs2MediaPacket,
    MSG_PING,
    encode_drw_frame,
    encode_msg,
)

_LOGGER = logging.getLogger(__name__)


_STRUCT_TCP_LEN = struct.Struct(">H")
_STRUCT_RESERVED = struct.Struct(">HHHHH")
_STRUCT_PAYLOAD_LEN = struct.Struct(">I")


PING_INTERVAL_SECONDS: float = 1.0
TCP_MAGIC_BYTE = 0x68


@dataclass(frozen=True)
class _ClosedSentinel:
    """Wake-up marker pushed into the command/media queues at close time."""


_CLOSED_SENTINEL = _ClosedSentinel()


class TcpCs2Transport:
    """TCP transport for an already-discovered CS2 peer."""

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
        self._seq_ch0: int = 0
        self._seq_ch3: int = 0
        self._seq_ping: int = 0
        self._last_ping_at: Optional[float] = None
        self._buffer = bytearray()
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
        seq = self._seq_ch0
        self._seq_ch0 = (self._seq_ch0 + 1) & 0xFFFF
        inner = command_id_to_be_bytes(command.command_id) + command.payload
        frame = encode_drw_frame(CHANNEL_COMMAND, seq, inner)
        await self._send_frame(frame)

    async def read_media_packet(self, timeout: float | None = None) -> Cs2MediaPacket:
        return await self._dequeue(self._media_queue, timeout)

    async def write_media_packet(self, packet: Cs2MediaPacket) -> None:
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        seq = self._seq_ch3
        self._seq_ch3 = (self._seq_ch3 + 1) & 0xFFFF
        body = packet.header + packet.encrypted_body
        frame = encode_drw_frame(3, seq, body)
        await self._send_frame(frame)

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
                    _LOGGER.warning(
                        "CS2 TCP transport got IncompleteReadError; "
                        "connection lost"
                    )
                    self._mark_eof()
                    return
                except asyncio.CancelledError:
                    return
                except ConnectionError as exc:
                    _LOGGER.warning(
                        "CS2 TCP transport connection error: %s", exc,
                    )
                    self._mark_eof()
                    return
                if not chunk:
                    self._mark_eof()
                    return
                try:
                    self._process_chunk(chunk)
                except MissError as exc:
                    self._failed_with = exc
                    _LOGGER.warning(
                        "CS2 TCP reader exiting due to %s/%s",
                        exc.category.value, exc.detail,
                    )
                    self._fail_queue_sync(self._command_queue)
                    self._fail_queue_sync(self._media_queue)
                    return
        except asyncio.CancelledError:
            return

    def _process_chunk(self, chunk: bytes) -> None:
        self._buffer.extend(chunk)
        while True:
            # Each TCP frame: [BE uint16 len][0x68][5 reserved][body].
            if len(self._buffer) < 8:
                return
            frame_len = _STRUCT_TCP_LEN.unpack_from(self._buffer, 0)[0]
            magic = self._buffer[2]
            if magic != TCP_MAGIC_BYTE:
                raise MissError(
                    MissErrorCategory.TRANSPORT, "tcp_magic_invalid"
                )
            total = 8 + frame_len
            if len(self._buffer) < total:
                return
            body = bytes(self._buffer[8:total])
            del self._buffer[:total]
            self._process_drw_body(body)

    def _process_drw_body(self, body: bytes) -> None:
        # Wire layout for an inbound TCP body (matches the go2rtc cs2
        # worker, which assumes the frame still carries the outer
        # 0xF1 0xD0 magic+kind):
        #   [0xF1][0xD0][BE uint16 total_len][0xD1][channel][BE uint16 seq]
        #   [BE uint32 payload_len][payload]
        if len(body) < 12:
            return
        if body[0] != 0xF1 or body[1] != 0xD0:
            return
        total_len = (body[2] << 8) | body[3]
        if total_len < 8 or total_len > len(body) - 4:
            raise MissError(MissErrorCategory.TRANSPORT, "drw_length_invalid")
        if body[4] != 0xD1:
            return
        channel = body[5]
        payload_len = _STRUCT_PAYLOAD_LEN.unpack_from(body, 8)[0]
        if payload_len > total_len - 8:
            raise MissError(
                MissErrorCategory.TRANSPORT, "drw_payload_length_invalid"
            )
        payload = body[12:12 + payload_len]
        if channel == CHANNEL_COMMAND:
            self._deliver_command(payload)
        elif channel == CHANNEL_MEDIA:
            self._deliver_media(payload)
        # Other channels (e.g. 3 for peer media on TCP) are ignored.

    def _deliver_command(self, body: bytes) -> None:
        if len(body) < 4:
            return
        # Channel-0 commands carry the command id in BIG-endian on the wire.
        command_id = struct.unpack(">I", body[:4])[0]
        self._enqueue_command(
            Cs2Command(command_id=command_id, payload=bytes(body[4:]))
        )

    def _deliver_media(self, body: bytes) -> None:
        if len(body) < 32:
            return
        self._enqueue_media(
            Cs2MediaPacket(header=body[:32], encrypted_body=body[32:])
        )

    def _mark_eof(self) -> None:
        if self._failed_with is None:
            self._failed_with = MissError(
                MissErrorCategory.TRANSPORT, "connection_lost"
            )
        self._fail_queue_sync(self._command_queue)
        self._fail_queue_sync(self._media_queue)

    async def _send_frame(self, frame: bytes) -> None:
        # Send opportunistic ping every second to keep the connection alive.
        now = self._clock.now
        if self._last_ping_at is None or now - self._last_ping_at >= PING_INTERVAL_SECONDS:
            ping = encode_msg(MSG_PING)
            self._writer.write(
                _STRUCT_TCP_LEN.pack(len(ping))
                + bytes([TCP_MAGIC_BYTE])
                + b"\x00" * 5
                + ping
            )
            await self._writer.drain()
            self._last_ping_at = now

        self._writer.write(
            _STRUCT_TCP_LEN.pack(len(frame))
            + bytes([TCP_MAGIC_BYTE])
            + b"\x00" * 5
            + frame
        )
        await self._writer.drain()

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

    @staticmethod
    def _fail_queue_sync(queue: asyncio.Queue) -> None:
        try:
            queue.put_nowait(_CLOSED_SENTINEL)
        except asyncio.QueueFull:  # pragma: no cover - queue already full
            pass


def command_id_to_be_bytes(command_id: int) -> bytes:
    """Encode a command id as a 4-byte big-endian uint32."""
    return struct.pack(">I", command_id & 0xFFFFFFFF)


__all__ = ["PING_INTERVAL_SECONDS", "TcpCs2Transport"]