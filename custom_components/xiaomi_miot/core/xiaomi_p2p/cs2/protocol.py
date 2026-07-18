"""CS2 framing and bounded DRW parser.

CS2 frames use direction-specific byte orders:
  * outbound commands: outer length, DRW sequence, command payload
    length, and wrapper command ID are big-endian;
  * inbound channel-0 commands: little-endian uint32 command ID;
  * MISS plaintext command ID (carried inside wrapper `0x1001`):
    big-endian uint32;
  * media header: little-endian uint32 codec id, sequence, flags, and
    little-endian uint64 timestamp.

Encoders and decoders are deliberately kept as separate functions; the
decoder MUST NOT be used to encode and the encoder MUST NOT be used to
decode.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .. import MissError, MissErrorCategory


# Magic values used to identify CS2 and DRW frames on the wire.
CS2_FRAME_MAGIC = b"\xff\xf1"
DRW_MAGIC_COMMAND = b"\x21\x00"  # channel 0
DRW_MAGIC_MEDIA = b"\x21\x02"  # channel 2
DRW_MAGIC_PING = b"\x21\x01"  # channel 1, reference-compatible keepalive

# Maximum allowed payload in any single CS2 frame (4 MiB).
MAX_PAYLOAD_BYTES = 4 * 1024 * 1024

# Size of a CS2 command outer header before the inner payload.
_OUTER_HEADER_SIZE = 16

# Size of a DRW header (magic/channel + sequence + payload length).
_DRW_HEADER_SIZE = 8

# Big-endian and little-endian codec structures.
_STRUCT_OUTER_LEN = struct.Struct(">H")
_STRUCT_DRW_SEQ = struct.Struct(">H")
_STRUCT_PAYLOAD_LEN = struct.Struct(">I")
_STRUCT_COMMAND_ID_BE = struct.Struct(">I")
_STRUCT_COMMAND_ID_LE = struct.Struct("<I")
_STRUCT_HEADER_CODEC = struct.Struct("<I")
_STRUCT_HEADER_SEQUENCE = struct.Struct("<I")
_STRUCT_HEADER_FLAGS = struct.Struct("<I")
_STRUCT_HEADER_TIMESTAMP = struct.Struct("<Q")


@dataclass(frozen=True, slots=True)
class Cs2Command:
    """Inbound channel-0 CS2 command."""

    command_id: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class Cs2MediaPacket:
    """Inbound channel-2 CS2 media packet: plaintext 32-byte header + encrypted body."""

    header: bytes
    encrypted_body: bytes


@dataclass(frozen=True, slots=True)
class MediaHeader:
    """Parsed MISS 32-byte media header."""

    codec_id: int
    sequence: int
    flags: int
    timestamp: int


@dataclass(frozen=True, slots=True)
class DrwFrame:
    """One DRW frame: magic/channel, sequence, payload."""

    magic: bytes
    sequence: int
    payload: bytes


def encode_outbound_cs2_command(
    command_id: int, payload: bytes, *, sequence: int
) -> bytes:
    """Encode an outbound CS2 command frame on channel 0."""

    if not isinstance(payload, (bytes, bytearray)):
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_payload_invalid")
    payload = bytes(payload)
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_payload_invalid")
    if not 0 <= sequence <= 0xFFFF:
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_sequence_invalid")

    outer_length = _OUTER_HEADER_SIZE - 4 + len(payload)
    header = (
        CS2_FRAME_MAGIC
        + _STRUCT_OUTER_LEN.pack(outer_length)
        + DRW_MAGIC_COMMAND
        + _STRUCT_DRW_SEQ.pack(sequence)
        + _STRUCT_PAYLOAD_LEN.pack(len(payload))
        + _STRUCT_COMMAND_ID_BE.pack(command_id)
    )
    return header + payload


def decode_inbound_cs2_command(frame: bytes) -> Cs2Command:
    """Parse an inbound channel-0 CS2 command frame (little-endian command id)."""

    if len(frame) < 4:
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_malformed")
    command_id = _STRUCT_COMMAND_ID_LE.unpack_from(frame, 0)[0]
    return Cs2Command(command_id=command_id, payload=bytes(frame[4:]))


def encode_outbound_miss_plaintext(command_id: int, body: bytes) -> bytes:
    """Build the encrypted MISS plaintext block (big-endian command id + body)."""

    if not isinstance(body, (bytes, bytearray)):
        raise MissError(MissErrorCategory.TRANSPORT, "miss_plaintext_invalid")
    return _STRUCT_COMMAND_ID_BE.pack(command_id) + bytes(body)


def decode_miss_media_header(header: bytes) -> MediaHeader:
    """Parse a 32-byte MISS media header."""

    if len(header) < 32:
        raise MissError(MissErrorCategory.MEDIA, "media_header_invalid")
    codec_id = _STRUCT_HEADER_CODEC.unpack_from(header, 4)[0]
    sequence = _STRUCT_HEADER_SEQUENCE.unpack_from(header, 8)[0]
    flags = _STRUCT_HEADER_FLAGS.unpack_from(header, 12)[0]
    timestamp = _STRUCT_HEADER_TIMESTAMP.unpack_from(header, 16)[0]
    return MediaHeader(
        codec_id=codec_id,
        sequence=sequence,
        flags=flags,
        timestamp=timestamp,
    )


def sequence_distance(expected: int, received: int) -> int:
    """Signed wraparound-aware distance from `expected` to `received`.

    Returns the signed value such that positive means `received` is
    ahead of `expected` (in the wraparound-aware sense) and negative
    means it is behind. The result lives in [-32768, 32767].
    """

    diff = (received - expected) & 0xFFFF
    if diff >= 0x8000:
        diff -= 0x10000
    return diff


class BoundedDrwParser:
    """Bounded length-prefixed DRW frame parser.

    Each DRW frame layout:
      * bytes 0-1: magic/channel (2 bytes)
      * bytes 2-3: sequence (uint16 big-endian)
      * bytes 4-7: payload length (uint32 big-endian)
      * bytes 8+:  payload of that exact length

    `feed()` accepts an arbitrary number of bytes. `drain()` yields
    zero or more complete frames. An advertised length greater than
    `limit` is rejected eagerly: the parser raises `MissError` instead
    of allocating or retaining the body.
    """

    def __init__(self, *, limit: int = MAX_PAYLOAD_BYTES) -> None:
        self._limit = limit
        self._buffer = bytearray()
        self._poisoned = False

    def feed(self, data: bytes) -> None:
        if self._poisoned:
            return
        if not isinstance(data, (bytes, bytearray)):
            raise MissError(MissErrorCategory.TRANSPORT, "drw_feed_invalid")
        self._buffer.extend(data)

    def drain(self):
        if self._poisoned:
            return
        out: list[DrwFrame] = []
        while True:
            if len(self._buffer) < _DRW_HEADER_SIZE:
                break
            magic = bytes(self._buffer[:2])
            sequence = _STRUCT_DRW_SEQ.unpack_from(self._buffer, 2)[0]
            payload_length = _STRUCT_PAYLOAD_LEN.unpack_from(self._buffer, 4)[0]
            if payload_length > self._limit:
                self._poisoned = True
                self._buffer.clear()
                raise MissError(MissErrorCategory.TRANSPORT, "drw_oversize")
            total = _DRW_HEADER_SIZE + payload_length
            if len(self._buffer) < total:
                break
            payload = bytes(self._buffer[_DRW_HEADER_SIZE:total])
            out.append(DrwFrame(magic=magic, sequence=sequence, payload=payload))
            del self._buffer[:total]
        for frame in out:
            yield frame


__all__ = [
    "BoundedDrwParser",
    "CS2_FRAME_MAGIC",
    "Cs2Command",
    "Cs2MediaPacket",
    "DRW_MAGIC_COMMAND",
    "DRW_MAGIC_MEDIA",
    "DRW_MAGIC_PING",
    "DrwFrame",
    "MAX_PAYLOAD_BYTES",
    "MediaHeader",
    "decode_inbound_cs2_command",
    "decode_miss_media_header",
    "encode_outbound_cs2_command",
    "encode_outbound_miss_plaintext",
    "sequence_distance",
]