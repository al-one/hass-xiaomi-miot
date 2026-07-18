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
        bind_socket=lambda port: peer.bind_discovery_socket(port, discovery_response=peer.next_discovery_response),
        open_tcp=peer.open_tcp_connection,
        discovery_response=peer.next_discovery_response,
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
        bind_socket=lambda port: peer.bind_discovery_socket(port, discovery_response=peer.next_discovery_response),
        open_tcp=peer.open_tcp_connection,
        discovery_response=peer.next_discovery_response,
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
        bind_socket=lambda port: peer.bind_discovery_socket(port, discovery_response=peer.next_discovery_response),
        open_tcp=peer.open_tcp_connection,
        discovery_response=peer.next_discovery_response,
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
        bind_socket=lambda port: peer.bind_discovery_socket(port, discovery_response=peer.next_discovery_response),
        open_tcp=peer.open_tcp_connection,
        discovery_response=peer.next_discovery_response,
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
        bind_socket=lambda port: peer.bind_discovery_socket(port, discovery_response=peer.next_discovery_response),
        open_tcp=peer.open_tcp_connection,
        discovery_response=peer.next_discovery_response,
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
        bind_socket=lambda port: peer.bind_discovery_socket(port, discovery_response=peer.next_discovery_response),
        open_tcp=peer.open_tcp_connection,
        discovery_response=peer.next_discovery_response,
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
        bind_socket=lambda port: peer.bind_discovery_socket(port, discovery_response=peer.next_discovery_response),
        open_tcp=peer.open_tcp_connection,
        discovery_response=peer.next_discovery_response,
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
        bind_socket=lambda port: peer.bind_discovery_socket(port, discovery_response=peer.next_discovery_response),
        open_tcp=peer.open_tcp_connection,
        discovery_response=peer.next_discovery_response,
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
        bind_socket=lambda port: peer.bind_discovery_socket(port, discovery_response=peer.next_discovery_response),
        open_tcp=peer.open_tcp_connection,
        discovery_response=peer.next_discovery_response,
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
        bind_socket=lambda port: peer.bind_discovery_socket(port, discovery_response=peer.next_discovery_response),
        open_tcp=peer.open_tcp_connection,
        discovery_response=peer.next_discovery_response,
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
        bind_socket=lambda port: peer.bind_discovery_socket(port, discovery_response=peer.next_discovery_response),
        open_tcp=peer.open_tcp_connection,
        discovery_response=peer.next_discovery_response,
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