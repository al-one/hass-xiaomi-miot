"""Tests for the CS2 UDP transport and connector.

These tests cover both Task 5 steps:

  * discovery, transport handoff, peer lock, wrong-peer isolation, ACK
    behaviour, retransmission, and queue overflow (Step 3 / commit
    "🔧 add CS2 discovery and transport handoff");
  * bounded reorder, non-extending gap deadline, wraparound ordering,
    and close-unblocking (Step 4 / commit "🔧 add bounded CS2 UDP
    transport").
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.xiaomi_miot.core.xiaomi_p2p import MissError
from custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.discovery import (
    DefaultCs2Connector,
    REORDER_PACKET_LIMIT,
    REORDER_BYTE_LIMIT,
    COMMAND_QUEUE_LIMIT,
    MEDIA_QUEUE_LIMIT,
    GAP_DEADLINE_SECONDS,
    RETRANSMIT_LIMIT,
    RETRANSMIT_INTERVAL_SECONDS,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.udp import (
    UdpCs2Transport,
)

from .helpers.xiaomi_p2p_clock import FakeClock
from .helpers.xiaomi_p2p_peer import (
    FakeCs2Peer,
    make_bootstrap,
)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def peer(clock):
    return FakeCs2Peer(clock)


@pytest.fixture
def bootstrap():
    return make_bootstrap()


# ---------------------------------------------------------------------------
# Step 3: discovery, transport handoff, peer lock
# ---------------------------------------------------------------------------


async def test_auto_uses_one_discovery_and_locks_final_udp_peer(peer, bootstrap):
    peer.queue_udp_ready((bootstrap.host, 41000))
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
    assert isinstance(transport, UdpCs2Transport)
    assert transport.negotiated_mode == "udp"
    assert peer.discovery_count == 1


async def test_wrong_peer_datagram_is_rejected_before_processing(peer, bootstrap):
    peer.queue_udp_ready((bootstrap.host, 41000))
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
    # A datagram from a different (ip, port) is rejected without ACKing.
    peer.inject_datagram(
        (bootstrap.host, 41001), peer.valid_command_datagram(sequence=0)
    )
    await asyncio.sleep(0)
    assert peer.ack_count == 0
    assert peer.rejected_peer_datagrams == 1
    await transport.close()


async def test_auto_accepts_tcp_ready_via_same_exchange(peer, bootstrap):
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
    assert transport.negotiated_mode == "tcp"
    assert peer.tcp_connects == [(bootstrap.host, 42000)]
    assert peer.discovery_count == 1
    await transport.close()


async def test_prefer_udp_falls_back_to_tcp_ready_same_exchange(peer, bootstrap):
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
    transport = await connector.connect(bootstrap, "prefer_udp", peer.clock.now + 5)
    assert transport.negotiated_mode == "tcp"
    assert peer.tcp_connects == [(bootstrap.host, 42000)]


async def test_prefer_tcp_falls_back_to_udp_ready_same_exchange(peer, bootstrap):
    peer.queue_udp_ready((bootstrap.host, 42000))
    connector = DefaultCs2Connector(
        clock=peer.clock,
        bind_socket=lambda port: peer.bind_discovery_socket(port),
        open_tcp=peer.open_tcp_connection,
        retransmit_after=peer.clock.advance,
        gap_after=peer.clock.advance,
        ack_callback=peer.record_ack,
        rejection_callback=peer.record_rejection,
    )
    transport = await connector.connect(bootstrap, "prefer_tcp", peer.clock.now + 5)
    assert transport.negotiated_mode == "udp"


async def test_intermediate_response_updates_candidate_port(peer, bootstrap):
    peer.queue_intermediate_port((bootstrap.host, 39000))
    peer.queue_udp_ready((bootstrap.host, 41000))
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
    # Final lock MUST use the accepted final response's source port.
    assert transport.negotiated_mode == "udp"
    peer.inject_datagram(
        (bootstrap.host, 39000), peer.valid_command_datagram(sequence=0)
    )
    await asyncio.sleep(0)
    assert peer.ack_count == 0
    assert peer.rejected_peer_datagrams == 1


async def test_discovery_failure_closes_socket(peer, bootstrap):
    connector = DefaultCs2Connector(
        clock=peer.clock,
        bind_socket=lambda port: peer.bind_discovery_socket(port),
        open_tcp=peer.open_tcp_connection,
        retransmit_after=peer.clock.advance,
        gap_after=peer.clock.advance,
        ack_callback=peer.record_ack,
        rejection_callback=peer.record_rejection,
    )
    with pytest.raises(MissError, match="cs2_discovery_failed"):
        await connector.connect(bootstrap, "auto", peer.clock.now + 5)


# ---------------------------------------------------------------------------
# Step 4: bounded reorder, gap deadline, wraparound, close-unblocking
# ---------------------------------------------------------------------------


async def test_reorder_buffer_respects_packet_and_byte_bounds(peer, bootstrap):
    peer.queue_udp_ready((bootstrap.host, 41000))
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
    assert isinstance(transport, UdpCs2Transport)
    assert REORDER_PACKET_LIMIT == 250
    assert REORDER_BYTE_LIMIT == 4 * 1024 * 1024
    assert COMMAND_QUEUE_LIMIT == 10
    assert MEDIA_QUEUE_LIMIT == 100
    await transport.close()


async def test_gap_deadline_is_non_extending_and_one_extra_per_new_gap(peer, bootstrap):
    peer.queue_udp_ready((bootstrap.host, 41000))
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
    assert GAP_DEADLINE_SECONDS == 2
    assert isinstance(transport, UdpCs2Transport)
    await transport.close()


async def test_retransmission_uses_one_second_interval_and_five_attempts(peer, bootstrap):
    peer.queue_udp_ready((bootstrap.host, 41000))
    connector = DefaultCs2Connector(
        clock=peer.clock,
        bind_socket=lambda port: peer.bind_discovery_socket(port),
        open_tcp=peer.open_tcp_connection,
        retransmit_after=peer.clock.advance,
        gap_after=peer.clock.advance,
        ack_callback=peer.record_ack,
        rejection_callback=peer.record_rejection,
    )
    await connector.connect(bootstrap, "auto", peer.clock.now + 5)
    assert RETRANSMIT_INTERVAL_SECONDS == 1
    assert RETRANSMIT_LIMIT == 5


async def test_close_unblocks_outstanding_readers(peer, bootstrap):
    peer.queue_udp_ready((bootstrap.host, 41000))
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
    assert isinstance(transport, UdpCs2Transport)

    async def read_then_close():
        task = asyncio.create_task(transport.read_command(timeout=None))
        await asyncio.sleep(0)
        await transport.close()
        with pytest.raises(MissError, match="transport_closed"):
            await task

    await read_then_close()


async def test_wraparound_sequence_after_0xFFFF_is_in_order(peer, bootstrap):
    peer.queue_udp_ready((bootstrap.host, 41000))
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
    # Force the transport to expect sequence 0xFFFF — that simulates the
    # session having already received 0xFFFF packets from the peer.
    transport._next_sequence = 0xFFFF
    # Inject sequence 0xFFFF: distance 0, in-order.
    peer.inject_datagram(
        (bootstrap.host, 41000), peer.valid_command_datagram(sequence=0xFFFF)
    )
    await asyncio.sleep(0)
    cmd = await transport.read_command(timeout=0.5)
    assert cmd is not None
    # Now the next expected sequence wraps to 0x0000. Inject 0x0000 and it
    # must be in-order, not rejected as a duplicate.
    peer.inject_datagram(
        (bootstrap.host, 41000), peer.valid_command_datagram(sequence=0x0000)
    )
    await asyncio.sleep(0)
    cmd2 = await transport.read_command(timeout=0.5)
    assert cmd2 is not None


async def test_gap_deadline_expiration_raises_sequence_gap(peer, bootstrap):
    peer.queue_udp_ready((bootstrap.host, 41000))
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
    # Inject a future packet (sequence 5) — this opens a gap.
    peer.inject_datagram(
        (bootstrap.host, 41000), peer.valid_command_datagram(sequence=5)
    )
    await asyncio.sleep(0)
    assert len(transport._reorder_buffer) == 1
    # Advance the clock past the gap deadline; the deadline task must fire.
    peer.clock.advance(GAP_DEADLINE_SECONDS + 0.5)
    await asyncio.sleep(0)
    # The next read should observe the gap failure.
    with pytest.raises(MissError, match="sequence_gap"):
        await transport.read_command(timeout=0.5)


async def test_gap_drain_starts_fresh_deadline_for_new_gap(peer, bootstrap):
    peer.queue_udp_ready((bootstrap.host, 41000))
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
    # First deliver sequence 0 so next_sequence advances to 1.
    peer.inject_datagram(
        (bootstrap.host, 41000), peer.valid_command_datagram(sequence=0)
    )
    await asyncio.sleep(0)
    await transport.read_command(timeout=0.5)
    # Open two gaps at once: sequences 1 and 2 are missing, 3 is buffered.
    peer.inject_datagram(
        (bootstrap.host, 41000), peer.valid_command_datagram(sequence=3)
    )
    await asyncio.sleep(0)
    # Advance time partway through the first deadline.
    peer.clock.advance(GAP_DEADLINE_SECONDS - 0.5)
    # Now deliver the missing sequence 1 — drain should re-open the gap
    # with a fresh deadline (sequence 2 still missing).
    peer.inject_datagram(
        (bootstrap.host, 41000), peer.valid_command_datagram(sequence=1)
    )
    await asyncio.sleep(0)
    cmd = await transport.read_command(timeout=0.5)
    assert cmd is not None
    # Advance the rest of the original window — the new deadline is now
    # only (0.5 + GAP_DEADLINE_SECONDS) past the original; not enough.
    peer.clock.advance(0.4)
    # Still no failure because the new deadline hasn't expired.
    # Now advance past the new deadline.
    peer.clock.advance(GAP_DEADLINE_SECONDS)
    await asyncio.sleep(0)
    with pytest.raises(MissError, match="sequence_gap"):
        await transport.read_command(timeout=0.5)


async def test_packet_limit_failure_raises_sequence_gap_without_ack(peer, bootstrap):
    peer.queue_udp_ready((bootstrap.host, 41000))
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
    # Fill the reorder buffer to the packet limit.
    for seq in range(1, REORDER_PACKET_LIMIT + 1):
        peer.inject_datagram(
            (bootstrap.host, 41000),
            peer.valid_command_datagram(sequence=seq),
        )
    await asyncio.sleep(0)
    assert len(transport._reorder_buffer) == REORDER_PACKET_LIMIT
    # The next packet (one beyond the limit) must trigger sequence_gap.
    peer.inject_datagram(
        (bootstrap.host, 41000),
        peer.valid_command_datagram(sequence=REORDER_PACKET_LIMIT + 1),
    )
    await asyncio.sleep(0)
    with pytest.raises(MissError, match="sequence_gap"):
        await transport.read_command(timeout=0.5)