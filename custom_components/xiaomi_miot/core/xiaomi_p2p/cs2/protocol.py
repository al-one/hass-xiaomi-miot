"""CS2 framing and bounded DRW parser.

The CS2 wire protocol used by Xiaomi MISS-layer P2P cameras is a single-byte
``magic = 0xF1`` followed by a one-byte message kind:

  * 0x30  ``msgLanSearch``   – client → camera: LAN search / discovery request
  * 0x41  ``msgPunchPkt``    – camera → client: punch response (with port)
  * 0x42  ``msgP2PRdyUDP``   – client → camera: ready for UDP data
  * 0x43  ``msgP2PRdyTCP``   – client → camera: ready for TCP data
  * 0xD0  ``msgDrw``         – bidirectional: DRW-multiplexed data frame
  * 0xD1  ``msgDrwAck``      – UDP ACK (echoes channel + sequence)
  * 0xE0  ``msgPing``        – TCP keepalive request
  * 0xE1  ``msgPong``        – TCP keepalive response
  * 0xF0  ``msgClose``       – graceful close
  * 0xF1  ``msgCloseAck``    – graceful close ack

After the two-byte ``0xF1 <kind>`` header, the body layout depends on the
message kind.  ``msgDrw`` frames use a big-endian uint16 length, the DRW
header (channel byte + big-endian uint16 sequence), an optional big-endian
uint32 payload length, and then the payload bytes.

Inbound channel-0 commands (carrying MISS command ids) are framed inside the
DRW channel-0 stream with a little-endian uint32 command id followed by the
command body.  The encrypted MISS plaintext block uses a big-endian uint32
inner command id followed by the plaintext.

Encoders and decoders are deliberately kept as separate functions; the
decoder MUST NOT be used to encode and the encoder MUST NOT be used to decode.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .. import MissError, MissErrorCategory


# Magic byte used to identify CS2 frames.
MAGIC = 0xF1

# Message kinds carried after the magic byte.
MSG_LAN_SEARCH = 0x30
MSG_PUNCH_PKT = 0x41
MSG_P2P_RDY_UDP = 0x42
MSG_P2P_RDY_TCP = 0x43
MSG_DRW = 0xD0
MSG_DRW_ACK = 0xD1
MSG_PING = 0xE0
MSG_PONG = 0xE1
MSG_CLOSE = 0xF0
MSG_CLOSE_ACK = 0xF1

# DRW header byte (single byte inside msgDrw frames).
DRW_MAGIC = 0xD1

# TCP outer magic (prepended before each TCP frame).
TCP_MAGIC = 0x68

# Maximum allowed payload in any single CS2 frame (4 MiB).
MAX_PAYLOAD_BYTES = 4 * 1024 * 1024

# Channel ids used by the multiplexer.
CHANNEL_COMMAND = 0
CHANNEL_MEDIA = 2

# Big-endian and little-endian codec structures.
_STRUCT_LEN_BE = struct.Struct(">H")
_STRUCT_LEN_LE = struct.Struct("<H")
_STRUCT_SEQ_BE = struct.Struct(">H")
_STRUCT_PAYLOAD_LEN_BE = struct.Struct(">I")
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


def encode_msg(message_kind: int, body: bytes = b"") -> bytes:
    """Encode a top-level CS2 message (magic + kind + body)."""

    if not isinstance(body, (bytes, bytearray)):
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_payload_invalid")
    return bytes([MAGIC, message_kind]) + bytes(body)


def encode_drw_frame(
    channel: int,
    sequence: int,
    payload: bytes,
    *,
    include_payload_length: bool = True,
) -> bytes:
    """Encode a DRW-multiplexed frame on the chosen channel.

    Layout (after the outer 0xF1 0xD0 magic+kind prefix is added by the
    transport layer):

      * 2 bytes: DRW frame body length (big-endian uint16) including itself
      * 1 byte:  DRW magic (0xD1)
      * 1 byte:  channel id
      * 2 bytes: sequence number (big-endian uint16)
      * 4 bytes: payload length (big-endian uint32), optional but always
                 present for commands and media
      * N bytes: payload

    For TCP transports the length prefix is two bytes shorter because the
    outer TCP framing already includes the per-frame length; the caller can
    pass ``include_payload_length=False`` to suppress the inner length in
    that case.
    """

    if not 0 <= channel <= 0xFF:
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_channel_invalid")
    if not 0 <= sequence <= 0xFFFF:
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_sequence_invalid")
    if not isinstance(payload, (bytes, bytearray)):
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_payload_invalid")
    payload = bytes(payload)
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_payload_invalid")

    inner = bytes([DRW_MAGIC, channel]) + _STRUCT_SEQ_BE.pack(sequence)
    if include_payload_length:
        inner += _STRUCT_PAYLOAD_LEN_BE.pack(len(payload))
    inner += payload

    # Total length covers DRW magic + channel + seq [+ payload len] + payload.
    # The 2-byte length prefix itself is NOT included (matches go2rtc's
    # ``binary.BigEndian.PutUint16(req[2:], uint16(4+4+4+size))`` formula).
    body_len = len(inner)
    outer = _STRUCT_LEN_BE.pack(body_len)
    return bytes([MAGIC, MSG_DRW]) + outer + inner


def encode_command(command_id: int, payload: bytes, *, sequence: int) -> bytes:
    """Encode an outbound MISS command on DRW channel 0.

    Layout: outer DRW frame carrying a big-endian uint32 command id
    followed by the command payload.  Used by the MISS session to send
    0x100 login / 0x102 start-media / 0x1001 encrypted wrapper commands.

    Note: the command id is big-endian in the wire format (see go2rtc's
    ``marshalCmd`` which uses ``binary.BigEndian.PutUint32``).
    """

    if not isinstance(payload, (bytes, bytearray)):
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_payload_invalid")
    inner = _STRUCT_COMMAND_ID_BE.pack(command_id) + bytes(payload)
    return encode_drw_frame(CHANNEL_COMMAND, sequence, inner)


def decode_inbound_cs2_command(frame: bytes) -> Cs2Command:
    """Parse a single DRW-channel-0 command body.

    The first 4 bytes are the little-endian uint32 command id; the rest is
    the command payload.
    """

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
    """Signed wraparound-aware distance from ``expected`` to ``received``.

    Returns the signed value such that positive means ``received`` is ahead
    of ``expected`` (in the wraparound-aware sense) and negative means it is
    behind.  The result lives in [-32768, 32767].
    """

    diff = (received - expected) & 0xFFFF
    if diff >= 0x8000:
        diff -= 0x10000
    return diff


# Backwards-compat aliases for existing call sites.
CS2_FRAME_MAGIC = bytes([MAGIC])
DRW_MAGIC_COMMAND = bytes([DRW_MAGIC, CHANNEL_COMMAND])
DRW_MAGIC_MEDIA = bytes([DRW_MAGIC, CHANNEL_MEDIA])
DRW_MAGIC_PING = bytes([DRW_MAGIC, 1])  # channel 1 (reference-compatible)


__all__ = [
    "CHANNEL_COMMAND",
    "CHANNEL_MEDIA",
    "CS2_FRAME_MAGIC",
    "Cs2Command",
    "Cs2MediaPacket",
    "DRW_MAGIC",
    "DRW_MAGIC_COMMAND",
    "DRW_MAGIC_MEDIA",
    "DRW_MAGIC_PING",
    "MAGIC",
    "MAX_PAYLOAD_BYTES",
    "MediaHeader",
    "MSG_CLOSE",
    "MSG_CLOSE_ACK",
    "MSG_DRW",
    "MSG_DRW_ACK",
    "MSG_LAN_SEARCH",
    "MSG_P2P_RDY_TCP",
    "MSG_P2P_RDY_UDP",
    "MSG_PING",
    "MSG_PONG",
    "MSG_PUNCH_PKT",
    "TCP_MAGIC",
    "decode_inbound_cs2_command",
    "decode_miss_media_header",
    "encode_command",
    "encode_drw_frame",
    "encode_msg",
    "encode_outbound_miss_plaintext",
    "encode_outbound_cs2_command",
    "sequence_distance",
]