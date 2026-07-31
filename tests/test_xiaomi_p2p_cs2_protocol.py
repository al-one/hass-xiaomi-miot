"""Tests for the typed CS2 framing.

The CS2 wire protocol uses a single-byte ``0xF1`` magic followed by a
message kind.  Encoded DRW frames layout the channel/sequence/payload
inside a body whose length is the first two big-endian bytes.  The
MISS plaintext block uses a big-endian uint32 command id, mirroring
the reference implementation in go2rtc.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.xiaomi_miot.core.xiaomi_p2p import MissError
from custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.protocol import (
    MAGIC,
    MSG_DRW,
    CHANNEL_COMMAND,
    Cs2Command,
    Cs2MediaPacket,
    decode_inbound_cs2_command,
    decode_miss_media_header,
    encode_command,
    encode_drw_frame,
    encode_msg,
    encode_outbound_miss_plaintext,
    sequence_distance,
)


FIXTURES = Path(__file__).parent / "fixtures" / "xiaomi_p2p"


def test_lan_search_message_layout():
    msg = encode_msg(0x30, b"\x00\x00")
    assert msg == bytes([MAGIC, 0x30, 0, 0])


def test_outbound_drw_frame_layout():
    # cmd id 0x100 + payload b'{}' = 6 bytes total
    frame = encode_command(0x100, b"{}", sequence=0x1234)
    assert frame[0:2] == bytes([MAGIC, MSG_DRW])
    # DRW body length includes DRW magic + channel + seq + payload_len +
    # payload (= 4 + 4 + 6 = 14).
    assert frame[2:4] == (14).to_bytes(2, "big")
    # DRW magic + channel
    assert frame[4:6] == bytes([0xD1, CHANNEL_COMMAND])
    # Sequence big-endian
    assert frame[6:8] == bytes.fromhex("1234")
    # Payload length big-endian (= 4 cmd id bytes + payload bytes)
    assert frame[8:12] == (4 + len(b"{}")).to_bytes(4, "big")
    # Channel-0 command body is little-endian command id followed by payload.
    assert frame[12:16] == bytes.fromhex("00000100")
    assert frame[16:] == b"{}"


def test_inbound_command_decodes_le_command_id():
    inbound = decode_inbound_cs2_command(bytes.fromhex("01010000") + b"ok")
    assert inbound == Cs2Command(0x101, b"ok")


def test_inbound_command_rejects_short_input():
    with pytest.raises(MissError, match="cs2_malformed"):
        decode_inbound_cs2_command(b"abc")


def test_inbound_command_does_not_swap_endianness():
    le_bytes = bytes.fromhex("01010000")
    be_bytes = bytes.fromhex("00000101")
    le_decoded = decode_inbound_cs2_command(le_bytes + b"x")
    be_decoded = decode_inbound_cs2_command(be_bytes + b"x")
    assert le_decoded.command_id == 0x101
    assert be_decoded.command_id != le_decoded.command_id


def test_miss_plaintext_block_is_big_endian():
    assert encode_outbound_miss_plaintext(0x102, b"{}")[:4] == bytes.fromhex(
        "00000102"
    )


def test_media_header_parses_little_endian_fields():
    hdr = bytearray(32)
    import struct as _s

    _s.pack_into("<I", hdr, 4, 5)        # codec
    _s.pack_into("<I", hdr, 8, 7)        # sequence
    _s.pack_into("<I", hdr, 12, 1)       # flags
    _s.pack_into("<Q", hdr, 16, 12345)   # timestamp
    parsed = decode_miss_media_header(bytes(hdr))
    assert parsed.codec_id == 5
    assert parsed.sequence == 7
    assert parsed.flags == 1
    assert parsed.timestamp == 12345


def test_drw_frame_payload_length_is_consistent():
    payload = b"abcdefgh"
    frame = encode_drw_frame(0, 0, payload)
    body_len = int.from_bytes(frame[2:4], "big")
    payload_len = int.from_bytes(frame[8:12], "big")
    assert body_len == 4 + 4 + len(payload)
    assert payload_len == len(payload)
    assert frame[12:] == payload


def test_sequence_distance_wraparound_orders_correctly():
    assert sequence_distance(0x0000, 0x0001) == 1
    assert sequence_distance(0x0001, 0x0000) == -1
    assert sequence_distance(0xFFFF, 0x0001) == 2
    assert sequence_distance(0x0001, 0xFFFF) == -2
    assert sequence_distance(0x8000, 0x8000) == 0