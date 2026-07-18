"""End-to-end MISS session tests over the fake CS2 peer."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.xiaomi_miot.core.xiaomi_p2p import (
    DEFAULT_P2P_PROFILE,
    MissError,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.discovery import (
    DefaultCs2Connector,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.protocol import (
    CS2_FRAME_MAGIC,
    DRW_MAGIC_COMMAND,
    DRW_MAGIC_MEDIA,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.crypto import (
    derive_shared_key,
    miss_encode,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.media import assemble_annex_b
from custom_components.xiaomi_miot.core.xiaomi_p2p.miss import (
    LOGIN_RESPONSE_COMMAND_ID,
    MissSession,
)

from .helpers.xiaomi_p2p_clock import FakeClock
from .helpers.xiaomi_p2p_peer import FakeCs2Peer, make_bootstrap


H264_SPS_1280X720 = bytes(
    [0x67, 0x42, 0xC0, 0x1E, 0xF8, 0x0A, 0x00, 0xB6, 0x00]
)


def _connector(peer: FakeCs2Peer) -> DefaultCs2Connector:
    return DefaultCs2Connector(
        clock=peer.clock,
        bind_socket=lambda port: peer.bind_discovery_socket(port),
        open_tcp=peer.open_tcp_connection,
        retransmit_after=peer.clock.advance,
        gap_after=peer.clock.advance,
        ack_callback=peer.record_ack,
        rejection_callback=peer.record_rejection,
    )


def _drw_frame(magic: bytes, sequence: int, body: bytes) -> bytes:
    return (
        magic
        + sequence.to_bytes(2, "big")
        + len(body).to_bytes(4, "big")
        + body
    )


def _udp_frame(magic: bytes, sequence: int, body: bytes) -> bytes:
    drw = _drw_frame(magic, sequence, body)
    return CS2_FRAME_MAGIC + len(drw).to_bytes(2, "big") + drw


def _login_response_frame(mode: str, sequence: int) -> bytes:
    body = LOGIN_RESPONSE_COMMAND_ID.to_bytes(4, "little")
    if mode == "udp":
        return _udp_frame(DRW_MAGIC_COMMAND, sequence, body)
    return _drw_frame(DRW_MAGIC_COMMAND, sequence, body)


def _media_body(
    key: bytes,
    codec_id: int,
    body: bytes,
    *,
    sequence: int,
    timestamp: int,
) -> bytes:
    header = (
        b"\x00" * 4
        + codec_id.to_bytes(4, "little")
        + sequence.to_bytes(4, "little")
        + b"\x00" * 4
        + timestamp.to_bytes(8, "little")
        + b"\x00" * 8
    )
    return header + miss_encode(key, body)


async def _wait_for(predicate) -> None:
    for _ in range(20):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("fake peer did not observe expected write")


async def _drive_login_and_probe(
    peer: FakeCs2Peer,
    transport,
    bootstrap,
    mode: str,
) -> None:
    key = derive_shared_key(
        bootstrap.client_private_key,
        bootstrap.device_public_key,
    )
    if mode == "udp":
        await _wait_for(lambda: len(peer.udp_sends) >= 2)
        peer.inject_datagram(
            (bootstrap.host, 41000),
            _login_response_frame(mode, transport._next_sequence),
        )
        await _wait_for(lambda: len(peer.udp_sends) >= 3)
        sequence = transport._next_sequence
        peer.inject_datagram(
            (bootstrap.host, 41000),
            _udp_frame(
                DRW_MAGIC_MEDIA,
                sequence,
                _media_body(
                    key,
                    4,
                    assemble_annex_b(
                        [H264_SPS_1280X720, b"\x68pps", b"\x65idr"]
                    ),
                    sequence=0,
                    timestamp=1000,
                ),
            ),
        )
        peer.inject_datagram(
            (bootstrap.host, 41000),
            _udp_frame(
                DRW_MAGIC_MEDIA,
                (sequence + 1) & 0xFFFF,
                _media_body(
                    key,
                    1027,
                    b"\xd5\xd5\xd5\xd5",
                    sequence=1,
                    timestamp=1020,
                ),
            ),
        )
        return

    assert peer.tcp_pair is not None
    await _wait_for(lambda: bool(peer.tcp_pair.writer.buffer))
    peer.tcp_pair.reader.feed_data(
        _login_response_frame(mode, 0)
        + _drw_frame(
            DRW_MAGIC_MEDIA,
            1,
            _media_body(
                key,
                4,
                assemble_annex_b(
                    [H264_SPS_1280X720, b"\x68pps", b"\x65idr"]
                ),
                sequence=0,
                timestamp=1000,
            ),
        )
        + _drw_frame(
            DRW_MAGIC_MEDIA,
            2,
            _media_body(
                key,
                1027,
                b"\xd5\xd5\xd5\xd5",
                sequence=1,
                timestamp=1020,
            ),
        )
    )


async def _start_session(mode: str, clock: FakeClock):
    bootstrap = make_bootstrap()
    peer = FakeCs2Peer(clock)
    if mode == "udp":
        peer.queue_udp_ready((bootstrap.host, 41000))
    else:
        peer.queue_tcp_ready((bootstrap.host, 42000))
    transport = await _connector(peer).connect(
        bootstrap,
        "auto",
        clock.now + 5,
    )
    session = MissSession(
        bootstrap=bootstrap,
        transport=transport,
        profile=DEFAULT_P2P_PROFILE,
        lens="primary",
        clock=clock,
    )
    task = asyncio.create_task(session.connect_and_start(clock.now + 5))
    await _drive_login_and_probe(peer, transport, bootstrap, mode)
    contract = await task
    return session, peer, transport, contract


@pytest.mark.parametrize("mode", ["udp", "tcp"])
async def test_fake_peer_login_and_probe(mode):
    session, peer, transport, contract = await _start_session(
        mode,
        FakeClock(),
    )

    assert transport.negotiated_mode == mode
    assert contract.video_codec == 4
    assert contract.audio_codec == 1027
    assert session.generation == 1
    assert peer.discovery_count == 1

    await session.close()


async def test_udp_sequence_gap_reconnects_without_scanning_buffered_media():
    clock = FakeClock()
    session, peer, transport, contract = await _start_session("udp", clock)
    generation = session.generation
    session.acquire_lease()
    reconnect_peers = []

    async def bootstrap_factory():
        bootstrap = make_bootstrap(host="192.168.1.20")
        reconnect_peer = FakeCs2Peer(clock)
        reconnect_peer.queue_udp_ready((bootstrap.host, 41000))
        reconnect_transport = await _connector(reconnect_peer).connect(
            bootstrap,
            "auto",
            clock.now + 5,
        )
        reconnect_peers.append(reconnect_peer)
        asyncio.create_task(
            _drive_login_and_probe(
                reconnect_peer,
                reconnect_transport,
                bootstrap,
                "udp",
            )
        )
        return bootstrap, reconnect_transport

    session.bootstrap_factory = bootstrap_factory
    key = derive_shared_key(
        session.bootstrap.client_private_key,
        session.bootstrap.device_public_key,
    )
    future_sequence = (transport._next_sequence + 5) & 0xFFFF
    peer.inject_datagram(
        (session.bootstrap.host, 41000),
        _udp_frame(
            DRW_MAGIC_MEDIA,
            future_sequence,
            _media_body(
                key,
                4,
                assemble_annex_b([b"\x01valid-looking-delta"]),
                sequence=9,
                timestamp=9000,
            ),
        ),
    )
    await _wait_for(lambda: transport._failed_with is not None)

    with pytest.raises(MissError, match="sequence_gap"):
        await transport.read_media_packet(timeout=0.1)

    recovered = await session.handle_sequence_gap(clock.now + 10)

    assert recovered == contract
    assert session.contract is contract
    assert session.generation == generation
    assert session._soft_restart_attempts == 0
    assert len(reconnect_peers) == 1

    await session.close()
