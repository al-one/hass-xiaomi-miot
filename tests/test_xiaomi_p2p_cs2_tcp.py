"""Tests for the CS2 TCP transport and connector.

These tests cover Task 6:
  * discovery cannot redirect the IP,
  * byte-by-byte, concatenated, and command/media separation,
  * DRW ping throttling (≤ 1 ping per second while processing writes),
  * EOF propagation as a distinct failure,
  * idempotent close unblocks readers and writers.
"""

from __future__ import annotations

import asyncio
import struct

import pytest

from custom_components.xiaomi_miot.core.xiaomi_p2p import MissError
from custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.discovery import (
    DefaultCs2Connector,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.protocol import (
    DRW_MAGIC_COMMAND,
    DRW_MAGIC_MEDIA,
    Cs2Command,
    Cs2MediaPacket,
    DRW_MAGIC_PING,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.tcp import TcpCs2Transport

from .helpers.xiaomi_p2p_clock import FakeClock
from .helpers.xiaomi_p2p_peer import (
    FakeCs2Peer,
    FakeTcpPair,
    make_bootstrap,
)


_STRUCT_DRW_PAYLOAD_LEN = struct.Struct(">I")


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def peer(clock):
    return FakeCs2Peer(clock)


@pytest.fixture
def bootstrap():
    return make_bootstrap()


@pytest.fixture
def tcp_pair():
    return FakeTcpPair()


# ---------------------------------------------------------------------------
# Discovery: TCP-ready cannot redirect the IP
# ---------------------------------------------------------------------------


async def test_tcp_ready_cannot_redirect_ip(peer, bootstrap):
    # Bootstrap IP is 192.168.1.20; a TCP-ready from 192.168.1.99 must be rejected.
    peer.queue_tcp_ready(("192.168.1.99", 41000))
    connector = DefaultCs2Connector(
        clock=peer.clock,
        bind_socket=lambda port: peer.bind_discovery_socket(port),
        open_tcp=peer.open_tcp_connection,
        retransmit_after=peer.clock.advance,
        gap_after=peer.clock.advance,
        ack_callback=peer.record_ack,
        rejection_callback=peer.record_rejection,
    )
    with pytest.raises(MissError, match="cs2_discovery_invalid"):
        await connector.connect(bootstrap, "prefer_tcp", peer.clock.now + 5)
    assert peer.tcp_connects == []


async def test_tcp_ready_handoff_opens_tcp_with_pinned_ip(peer, bootstrap):
    peer.queue_tcp_ready((bootstrap.host, 42000))
    connector = DefaultCs2Connector(
        clock=peer.clock,
        bind_socket=lambda port: peer.bind_discovery_socket(port),
        open_tcp=peer.open_tcp_connection,
        retransmit_after=peer.clock.advance,
        gap_after=peer.clock.advance,
        ack_callback=peer.record_ack,
        rejection_callback=peer.record_rejection,
    )
    transport = await connector.connect(bootstrap, "auto", peer.clock.now + 5)
    assert isinstance(transport, TcpCs2Transport)
    assert transport.negotiated_mode == "tcp"
    assert peer.tcp_connects == [(bootstrap.host, 42000)]
    assert peer.tcp_pair is not None
    await transport.close()


# ---------------------------------------------------------------------------
# Frame parsing: byte-by-byte, concatenated, command/media separation
# ---------------------------------------------------------------------------


def _drw_command_frame(command_id: int, payload: bytes, sequence: int = 0) -> bytes:
    # Inbound channel-0 commands carry the command ID little-endian.
    body = command_id.to_bytes(4, "little") + payload
    return (
        DRW_MAGIC_COMMAND
        + sequence.to_bytes(2, "big")
        + len(body).to_bytes(4, "big")
        + body
    )


def _drw_media_frame(header: bytes, encrypted_body: bytes, sequence: int = 0) -> bytes:
    body = header + encrypted_body
    return (
        DRW_MAGIC_MEDIA
        + sequence.to_bytes(2, "big")
        + len(body).to_bytes(4, "big")
        + body
    )


def _count_pings(buffer: bytes) -> int:
    count = 0
    while buffer:
        if len(buffer) < 8:
            break
        length = _STRUCT_DRW_PAYLOAD_LEN.unpack_from(buffer, 4)[0]
        if buffer[:2] == DRW_MAGIC_PING:
            count += 1
        buffer = buffer[8 + length:]
    return count


async def test_tcp_frame_byte_by_byte(tcp_pair, clock):
    transport = TcpCs2Transport(
        reader=tcp_pair.reader, writer=tcp_pair.writer, clock=clock
    )
    transport.start_reader()
    frame = _drw_command_frame(0x100, b"{}", sequence=0)
    for byte in frame:
        tcp_pair.reader.feed_data(bytes([byte]))
        await asyncio.sleep(0)
    cmd = await transport.read_command(timeout=0.5)
    assert cmd.command_id == 0x100
    assert cmd.payload == b"{}"
    await transport.close()


async def test_tcp_concatenated_frames_in_one_read(tcp_pair, clock):
    transport = TcpCs2Transport(
        reader=tcp_pair.reader, writer=tcp_pair.writer, clock=clock
    )
    transport.start_reader()
    frame1 = _drw_command_frame(0x101, b"a", sequence=0)
    frame2 = _drw_command_frame(0x102, b"b", sequence=1)
    tcp_pair.reader.feed_data(frame1 + frame2)
    await asyncio.sleep(0)
    cmd1 = await transport.read_command(timeout=0.5)
    cmd2 = await transport.read_command(timeout=0.5)
    assert cmd1.command_id == 0x101
    assert cmd1.payload == b"a"
    assert cmd2.command_id == 0x102
    assert cmd2.payload == b"b"
    await transport.close()


async def test_tcp_command_and_media_separation(tcp_pair, clock):
    transport = TcpCs2Transport(
        reader=tcp_pair.reader, writer=tcp_pair.writer, clock=clock
    )
    transport.start_reader()
    cmd_frame = _drw_command_frame(0x103, b"cmd", sequence=0)
    media_header = b"\x00" * 32
    media_frame = _drw_media_frame(media_header, b"encrypted", sequence=1)
    tcp_pair.reader.feed_data(cmd_frame + media_frame)
    await asyncio.sleep(0)
    cmd = await transport.read_command(timeout=0.5)
    pkt = await transport.read_media_packet(timeout=0.5)
    assert cmd.command_id == 0x103
    assert cmd.payload == b"cmd"
    assert pkt.header == media_header
    assert pkt.encrypted_body == b"encrypted"
    await transport.close()


# ---------------------------------------------------------------------------
# DRW ping throttling (≤ 1 ping per second while processing writes)
# ---------------------------------------------------------------------------


async def test_tcp_ping_emitted_with_first_write(tcp_pair, clock):
    transport = TcpCs2Transport(
        reader=tcp_pair.reader, writer=tcp_pair.writer, clock=clock
    )
    transport.start_reader()
    cmd = Cs2Command(command_id=0x100, payload=b"{}")
    await transport.write_command(cmd)
    assert _count_pings(tcp_pair.writer.buffer) == 1
    await transport.close()


async def test_tcp_ping_throttled_within_one_second(tcp_pair, clock):
    transport = TcpCs2Transport(
        reader=tcp_pair.reader, writer=tcp_pair.writer, clock=clock
    )
    transport.start_reader()
    cmd = Cs2Command(command_id=0x100, payload=b"{}")
    # Five writes spaced 0.2s apart: total 0.8s, well under 1s budget.
    for _ in range(5):
        await transport.write_command(cmd)
        clock.advance(0.2)
    assert _count_pings(tcp_pair.writer.buffer) == 1
    await transport.close()


async def test_tcp_ping_reemitted_after_one_second(tcp_pair, clock):
    transport = TcpCs2Transport(
        reader=tcp_pair.reader, writer=tcp_pair.writer, clock=clock
    )
    transport.start_reader()
    cmd = Cs2Command(command_id=0x100, payload=b"{}")
    await transport.write_command(cmd)  # t=0.0: 1st ping
    clock.advance(1.5)
    await transport.write_command(cmd)  # t=1.5: 2nd ping
    clock.advance(1.5)
    await transport.write_command(cmd)  # t=3.0: 3rd ping
    assert _count_pings(tcp_pair.writer.buffer) == 3
    await transport.close()


async def test_tcp_ping_also_emitted_before_first_media_write(tcp_pair, clock):
    transport = TcpCs2Transport(
        reader=tcp_pair.reader, writer=tcp_pair.writer, clock=clock
    )
    transport.start_reader()
    pkt = Cs2MediaPacket(header=b"\x00" * 32, encrypted_body=b"abc")
    await transport.write_media_packet(pkt)
    assert _count_pings(tcp_pair.writer.buffer) == 1
    await transport.close()


# ---------------------------------------------------------------------------
# EOF propagation and idempotent close
# ---------------------------------------------------------------------------


async def test_tcp_eof_propagates_as_connection_lost(tcp_pair, clock):
    transport = TcpCs2Transport(
        reader=tcp_pair.reader, writer=tcp_pair.writer, clock=clock
    )
    transport.start_reader()
    tcp_pair.reader.feed_eof()
    await asyncio.sleep(0)
    with pytest.raises(MissError, match="connection_lost"):
        await transport.read_command(timeout=0.5)
    await transport.close()


async def test_tcp_eof_propagates_to_media_readers(tcp_pair, clock):
    transport = TcpCs2Transport(
        reader=tcp_pair.reader, writer=tcp_pair.writer, clock=clock
    )
    transport.start_reader()
    tcp_pair.reader.feed_eof()
    await asyncio.sleep(0)
    with pytest.raises(MissError, match="connection_lost"):
        await transport.read_media_packet(timeout=0.5)
    await transport.close()


async def test_tcp_close_unblocks_outstanding_readers(tcp_pair, clock):
    transport = TcpCs2Transport(
        reader=tcp_pair.reader, writer=tcp_pair.writer, clock=clock
    )
    transport.start_reader()

    async def read_then_close():
        task = asyncio.create_task(transport.read_command(timeout=None))
        await asyncio.sleep(0)
        await transport.close()
        with pytest.raises(MissError, match="transport_closed"):
            await task

    await read_then_close()


async def test_tcp_close_is_idempotent(tcp_pair, clock):
    transport = TcpCs2Transport(
        reader=tcp_pair.reader, writer=tcp_pair.writer, clock=clock
    )
    transport.start_reader()
    await transport.close()
    # Second close must not raise.
    await transport.close()


async def test_tcp_writer_after_close_rejects(tcp_pair, clock):
    transport = TcpCs2Transport(
        reader=tcp_pair.reader, writer=tcp_pair.writer, clock=clock
    )
    transport.start_reader()
    await transport.close()
    with pytest.raises(MissError, match="transport_closed"):
        await transport.write_command(Cs2Command(command_id=0x100, payload=b"{}"))
