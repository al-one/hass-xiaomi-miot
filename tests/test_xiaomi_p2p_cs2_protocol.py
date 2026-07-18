"""Tests for the typed CS2 framing and bounded DRW parser.

CS2 frames use direction-specific byte orders: outbound commands are
big-endian, inbound channel-0 commands are little-endian. The MISS
plaintext command ID is big-endian. The media header is little-endian.
These tests assert the asymmetry rather than collapsing both directions
into one symmetric codec.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.xiaomi_miot.core.xiaomi_p2p import MissError
from custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.protocol import (
    BoundedDrwParser,
    Cs2Command,
    Cs2MediaPacket,
    DrwFrame,
    MAX_PAYLOAD_BYTES,
    decode_inbound_cs2_command,
    decode_miss_media_header,
    encode_outbound_cs2_command,
    encode_outbound_miss_plaintext,
    sequence_distance,
)


FIXTURES = Path(__file__).parent / "fixtures" / "xiaomi_p2p"


def _load_frames():
    with (FIXTURES / "cs2_frames.json").open(encoding="utf-8") as fp:
        return json.load(fp)


def test_direction_specific_command_endianness():
    frame = encode_outbound_cs2_command(0x100, b"{}", sequence=0x1234)
    # DRW sequence is big-endian at offset 6-7.
    assert frame[6:8] == bytes.fromhex("1234")
    # Wrapper command ID is big-endian at offset 12-15.
    assert frame[12:16] == bytes.fromhex("00000100")
    # Inbound channel-0 command frame decodes the same integer from LE bytes.
    inbound = decode_inbound_cs2_command(bytes.fromhex("01010000") + b"ok")
    assert inbound == Cs2Command(0x101, b"ok")


def test_start_media_plaintext_is_big_endian():
    assert encode_outbound_miss_plaintext(0x102, b"{}")[:4] == bytes.fromhex(
        "00000102"
    )


def test_outbound_frame_outer_length_includes_payload():
    frame = encode_outbound_cs2_command(0x100, b"{}", sequence=0x1234)
    outer = int.from_bytes(frame[2:4], "big")
    assert outer == 12 + len(b"{}")


def test_outbound_outer_length_is_big_endian():
    frame = encode_outbound_cs2_command(0x100, b"ABCDEF", sequence=0)
    assert frame[2:4] == (12 + 6).to_bytes(2, "big")


def test_outbound_command_payload_length_is_big_endian():
    frame = encode_outbound_cs2_command(0x100, b"abcdefgh", sequence=0)
    assert frame[8:12] == (8).to_bytes(4, "big")


def test_inbound_command_rejects_short_input():
    with pytest.raises(MissError, match="cs2_malformed"):
        decode_inbound_cs2_command(b"abc")


def test_inbound_command_does_not_swap_endianness():
    # Inbound command IDs are little-endian; the same four bytes encoded
    # big-endian MUST decode to a different integer (the LE decoder
    # interprets them in reverse order).
    le_bytes = bytes.fromhex("01010000")
    be_bytes = bytes.fromhex("00000101")
    le_decoded = decode_inbound_cs2_command(le_bytes + b"x")
    be_decoded = decode_inbound_cs2_command(be_bytes + b"x")
    assert le_decoded.command_id == 0x101
    assert be_decoded.command_id != le_decoded.command_id


def test_sequence_distance_wraparound_orders_correctly():
    # No wraparound: received > expected returns positive distance.
    assert sequence_distance(0x0000, 0x0001) == 1
    # No wraparound: received < expected returns negative distance.
    assert sequence_distance(0x0001, 0x0000) == -1
    # Wraparound: 0xFFFF -> 0x0001 forward = 2 (shortest direction).
    assert sequence_distance(0xFFFF, 0x0001) == 2
    # Wraparound: 0x0001 -> 0xFFFF forward = 65534, shortest signed = -2.
    assert sequence_distance(0x0001, 0xFFFF) == -2
    assert sequence_distance(0x8000, 0x8000) == 0


def test_decode_miss_media_header_layout():
    header = bytes.fromhex(
        "00000000"  # 4 bytes of pre-codec framing
        "05000000"  # codec id 5 (H.265) LE
        "01000000"  # sequence 1 LE
        "00000000"  # flags 0 LE
        "0100000000000000"  # timestamp 1 LE
    ) + b"\x00" * (32 - 20)
    decoded = decode_miss_media_header(header)
    assert decoded.codec_id == 5
    assert decoded.sequence == 1
    assert decoded.flags == 0
    assert decoded.timestamp == 1


def test_decode_miss_media_header_rejects_short_input():
    with pytest.raises(MissError, match="media_header_invalid"):
        decode_miss_media_header(b"\x00" * 31)


def _encode_drw(magic: bytes, sequence: int, payload: bytes) -> bytes:
    return magic + sequence.to_bytes(2, "big") + len(payload).to_bytes(4, "big") + payload


def test_bounded_drw_parser_emits_complete_frames():
    parser = BoundedDrwParser(limit=MAX_PAYLOAD_BYTES)
    frame1 = _encode_drw(b"\x21\x00", 0, b"abcd")
    frame2 = _encode_drw(b"\x21\x02", 1, b"ef")
    parser.feed(frame1 + frame2)
    emitted = list(parser.drain())
    assert len(emitted) == 2
    assert isinstance(emitted[0], DrwFrame)
    assert emitted[0].magic == b"\x21\x00"
    assert emitted[0].sequence == 0
    assert emitted[0].payload == b"abcd"
    assert emitted[1].magic == b"\x21\x02"
    assert emitted[1].sequence == 1
    assert emitted[1].payload == b"ef"


def test_bounded_drw_parser_handles_partial_then_complete():
    parser = BoundedDrwParser(limit=MAX_PAYLOAD_BYTES)
    frame = _encode_drw(b"\x21\x00", 0, b"abcd")
    parser.feed(frame[:3])
    assert list(parser.drain()) == []
    parser.feed(frame[3:5])
    assert list(parser.drain()) == []
    parser.feed(frame[5:])
    emitted = list(parser.drain())
    assert len(emitted) == 1
    assert emitted[0].payload == b"abcd"


def test_bounded_drw_parser_rejects_oversize_advertised_length():
    parser = BoundedDrwParser(limit=8)
    # Magic 0x21 0x00, sequence 0x0000, payload length 0x00010000 (>8).
    bogus = bytes.fromhex("2100000000010000")
    parser.feed(bogus)
    with pytest.raises(MissError, match="drw_oversize"):
        list(parser.drain())


def test_cs2_media_packet_keeps_header_and_body_separate():
    pkt = Cs2MediaPacket(header=b"h" * 32, encrypted_body=b"ciphertext")
    assert pkt.header == b"h" * 32
    assert pkt.encrypted_body == b"ciphertext"


def test_cs2_command_is_frozen():
    cmd = Cs2Command(0x101, b"ok")
    with pytest.raises(Exception):
        cmd.command_id = 0x102  # type: ignore[misc]


@pytest.mark.parametrize("frame", _load_frames()["frames"])
def test_fixture_round_trip(frame):
    kind = frame["kind"]
    if kind == "outbound_command":
        payload = bytes.fromhex(frame["payload_hex"])
        cmd = frame["command_id"]
        seq = frame["sequence"]
        encoded = encode_outbound_cs2_command(cmd, payload, sequence=seq)
        assert encoded.hex() == frame["hex"]
    elif kind == "inbound_command":
        data = bytes.fromhex(frame["hex"])
        decoded = decode_inbound_cs2_command(data)
        assert decoded.command_id == frame["command_id"]
        assert decoded.payload == bytes.fromhex(frame["payload_hex"])
    elif kind == "miss_plaintext":
        cmd = frame["command_id"]
        payload = bytes.fromhex(frame["payload_hex"])
        encoded = encode_outbound_miss_plaintext(cmd, payload)
        assert encoded.hex() == frame["hex"]
    else:
        raise AssertionError(kind)