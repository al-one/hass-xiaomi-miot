"""Tests for MISS session login, encrypted commands, and initial probe.

Covers Task 8 Step 1-2 (login/start_media initial probe slice):
  * plaintext 0x100 login format,
  * encrypted 0x1001 wrapper for subsequent commands,
  * start-media payload format for primary/secondary lens,
  * stop-media command,
  * generic quality rejection category,
  * mandatory profile codec rejection,
  * optional audio wait,
  * unknown but valid MISS message counting,
  * malformed state termination,
  * cancellation without reconnect.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from custom_components.xiaomi_miot.core.xiaomi_p2p import miss as miss_module
from custom_components.xiaomi_miot.core.xiaomi_p2p import (
    MediaContract,
    MissError,
    MissErrorCategory,
    P2PProfile,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.protocol import (
    Cs2Command,
    Cs2MediaPacket,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.crypto import (
    derive_shared_key,
    miss_decode,
    miss_encode,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.media import assemble_annex_b
from custom_components.xiaomi_miot.core.xiaomi_p2p.miss import (
    LOGIN_COMMAND_ID,
    LOGIN_RESPONSE_COMMAND_ID,
    ENCRYPTED_WRAPPER_COMMAND_ID,
    START_MEDIA_COMMAND_ID,
    STOP_MEDIA_COMMAND_ID,
    VIDEO_STALL_DEADLINE_SECONDS,
    MissSession,
)

from .helpers.xiaomi_p2p_clock import FakeClock
from .helpers.xiaomi_p2p_peer import make_bootstrap


# ---- Fake CS2 transport for the MISS layer -----------------------------


@dataclass
class FakeMissTransport:
    """In-memory CS2 transport used to drive `MissSession`.

    Captures the most recent outbound command and decrypts its payload
    when the wrapper is `0x1001`. Scripted inbound commands and media
    packets are queued for the session to consume.
    """

    clock: object
    negotiated_mode: str = "udp"
    last_command_id: int | None = field(default=None, init=False)
    last_decrypted_json: dict | None = field(default=None, init=False)
    last_decrypted_inner_id: int | None = field(default=None, init=False)
    write_count: int = field(default=0, init=False)
    closed: bool = field(default=False, init=False)
    pending_commands: list[Cs2Command] = field(default_factory=list, init=False)
    pending_media: list[Cs2MediaPacket] = field(default_factory=list, init=False)
    outbound_commands: list[Cs2Command] = field(default_factory=list, init=False)
    last_read_command_timeout: float | None = field(default=None, init=False)
    last_read_media_timeout: float | None = field(default=None, init=False)
    _closed_error: MissError | None = field(default=None, init=False)
    _shared_key: bytes | None = field(default=None, init=False)

    def attach_shared_key(self, key: bytes) -> None:
        self._shared_key = key

    async def read_command(self, timeout=None):
        self.last_read_command_timeout = timeout
        if self._closed_error is not None:
            raise self._closed_error
        if not self.pending_commands:
            raise asyncio.IncompleteReadError(b"", 0)
        return self.pending_commands.pop(0)

    async def write_command(self, command):
        if self.closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        self.write_count += 1
        self.last_command_id = command.command_id
        self.outbound_commands.append(command)
        if command.command_id == ENCRYPTED_WRAPPER_COMMAND_ID and self._shared_key is not None:
            plaintext = miss_decode(self._shared_key, command.payload)
            self.last_decrypted_inner_id = int.from_bytes(plaintext[:4], "big")
            try:
                self.last_decrypted_json = json.loads(plaintext[4:].decode("utf-8"))
            except Exception:
                self.last_decrypted_json = None
        return None

    async def read_media_packet(self, timeout=None):
        self.last_read_media_timeout = timeout
        if self._closed_error is not None:
            raise self._closed_error
        if not self.pending_media:
            if timeout is not None:
                self.clock.advance(timeout)
                raise MissError(MissErrorCategory.TIMEOUT, "read_timeout")
            raise asyncio.IncompleteReadError(b"", 0)
        return self.pending_media.pop(0)

    async def write_media_packet(self, packet):
        if self.closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        return None

    async def close(self):
        self.closed = True
        self._closed_error = MissError(MissErrorCategory.TRANSPORT, "transport_closed")


# ---- Fixtures ----------------------------------------------------------


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def bootstrap():
    return make_bootstrap(host="192.168.1.20")


@pytest.fixture
def transport(clock):
    return FakeMissTransport(clock=clock)


@pytest.fixture
def default_profile():
    return P2PProfile(
        lenses=("primary",),
        transport="auto",
        raw_quality=0,
        request_audio=True,
        required_video_codec=None,
        required_audio_codec=None,
    )


@pytest.fixture
def session(bootstrap, transport, clock, default_profile):
    shared_key = derive_shared_key(
        bootstrap.client_private_key, bootstrap.device_public_key
    )
    transport.attach_shared_key(shared_key)
    return MissSession(
        bootstrap=bootstrap,
        transport=transport,
        profile=default_profile,
        lens="primary",
        clock=clock,
    )


H264_SPS_1280X720 = bytes(
    [0x67, 0x42, 0xC0, 0x1E, 0xF8, 0x0A, 0x00, 0xB6, 0x00]
)


def test_fixed_command_vectors_preserve_direction_specific_ids():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/xiaomi_p2p/miss_commands.json").read_text()
    )

    assert bytes.fromhex(fixture["login_plaintext"]["hex"]) == bytes.fromhex(
        "00000100"
    )
    assert bytes.fromhex(fixture["login_response"]["hex"]) == bytes.fromhex(
        "01010000"
    )
    assert bytes.fromhex(fixture["start_media_inner"]["hex"]) == bytes.fromhex(
        "00000102"
    )


def make_media_packet(
    key: bytes,
    codec_id: int,
    body: bytes,
    *,
    sequence: int = 0,
    flags: int = 0,
    timestamp: int = 1000,
) -> Cs2MediaPacket:
    header = (
        b"\x00" * 4
        + codec_id.to_bytes(4, "little")
        + sequence.to_bytes(4, "little")
        + flags.to_bytes(4, "little")
        + timestamp.to_bytes(8, "little")
        + b"\x00" * 8
    )
    return Cs2MediaPacket(header=header, encrypted_body=miss_encode(key, body))


def test_session_repr_hides_runtime_secrets(session):
    session._shared_key = b"shared-key-secret".ljust(32, b"x")
    session._contract = MediaContract(
        video_codec=4,
        audio_codec=None,
        video_sps=b"sps-secret",
        video_pps=b"pps-secret",
        vps=None,
        width=1280,
        height=720,
        fps=30,
        sample_rate=0,
        channels=0,
    )

    text = repr(session)

    assert "192.168.1.20" not in text
    assert "shared-key-secret" not in text
    assert "sps-secret" not in text
    assert "sps-secret" not in repr(session._contract)


# ---- Initial publication gate -----------------------------------------


async def test_connect_and_start_publishes_complete_contract(
    session, transport, bootstrap, clock
):
    shared_key = derive_shared_key(
        bootstrap.client_private_key, bootstrap.device_public_key
    )
    transport.pending_commands.append(
        Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b"")
    )
    transport.pending_media.extend(
        [
            make_media_packet(
                shared_key,
                4,
                assemble_annex_b(
                    [
                        H264_SPS_1280X720,
                        b"\x68pps",
                        b"\x65idr",
                    ]
                ),
            ),
            make_media_packet(
                shared_key,
                1027,
                b"\xd5\xd5\xd5\xd5",
                sequence=1,
                timestamp=1020,
            ),
        ]
    )

    contract = await session.connect_and_start(clock.now + 5)

    assert contract.video_codec == 4
    assert contract.audio_codec == 1027
    assert (contract.width, contract.height) == (1280, 720)
    assert session.generation == 1
    assert session.state == "published"
    assert [command.command_id for command in transport.outbound_commands] == [
        LOGIN_COMMAND_ID,
        ENCRYPTED_WRAPPER_COMMAND_ID,
    ]


async def test_optional_audio_wait_publishes_video_only_after_two_seconds(
    session, transport, bootstrap, clock
):
    shared_key = derive_shared_key(
        bootstrap.client_private_key, bootstrap.device_public_key
    )
    transport.pending_commands.append(
        Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b"")
    )
    transport.pending_media.append(
        make_media_packet(
            shared_key,
            4,
            assemble_annex_b(
                [H264_SPS_1280X720, b"\x68pps", b"\x65idr"]
            ),
        )
    )

    contract = await session.connect_and_start(clock.now + 5)

    assert contract.audio_codec is None
    assert session.state == "published"
    assert transport.last_read_media_timeout == 2.0


async def test_required_audio_absence_rejects_candidate(
    bootstrap, transport, clock
):
    profile = P2PProfile(
        lenses=("primary",),
        transport="auto",
        raw_quality=0,
        request_audio=True,
        required_video_codec=None,
        required_audio_codec=1027,
    )
    shared_key = derive_shared_key(
        bootstrap.client_private_key, bootstrap.device_public_key
    )
    transport.attach_shared_key(shared_key)
    transport.pending_commands.append(
        Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b"")
    )
    transport.pending_media.append(
        make_media_packet(
            shared_key,
            4,
            assemble_annex_b(
                [H264_SPS_1280X720, b"\x68pps", b"\x65idr"]
            ),
        )
    )
    sess = MissSession(
        bootstrap=bootstrap,
        transport=transport,
        profile=profile,
        lens="primary",
        clock=clock,
    )

    with pytest.raises(MissError, match="codec_required_unsatisfied"):
        await sess.connect_and_start(clock.now + 5)


async def test_connect_and_start_rejects_required_video_codec(
    bootstrap, transport, clock
):
    profile = P2PProfile(
        lenses=("primary",),
        transport="auto",
        raw_quality=0,
        request_audio=False,
        required_video_codec=5,
        required_audio_codec=None,
    )
    shared_key = derive_shared_key(
        bootstrap.client_private_key, bootstrap.device_public_key
    )
    transport.attach_shared_key(shared_key)
    transport.pending_commands.append(
        Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b"")
    )
    transport.pending_media.append(
        make_media_packet(
            shared_key,
            4,
            assemble_annex_b(
                [H264_SPS_1280X720, b"\x68pps", b"\x65idr"]
            ),
        )
    )
    sess = MissSession(
        bootstrap=bootstrap,
        transport=transport,
        profile=profile,
        lens="primary",
        clock=clock,
    )

    with pytest.raises(MissError, match="codec_required_unsatisfied"):
        await sess.connect_and_start(clock.now + 5)


async def test_login_rejection_closes_initial_session(session, transport, clock):
    transport.pending_commands.append(
        Cs2Command(
            command_id=LOGIN_RESPONSE_COMMAND_ID,
            payload=b'{"code":-1}',
        )
    )

    with pytest.raises(MissError, match="login_rejected"):
        await session.connect_and_start(clock.now + 5)

    assert session.state == "failed"
    assert transport.closed is True
    assert transport.last_read_command_timeout == 5


async def test_non_object_login_response_is_sanitized(session, transport, clock):
    transport.pending_commands.append(
        Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b"[]")
    )

    with pytest.raises(MissError, match="login_response_malformed"):
        await session.connect_and_start(clock.now + 5)

    assert session.state == "failed"
    assert transport.closed is True


async def test_invalid_json_login_response_suppresses_payload_context(
    session,
    transport,
    clock,
):
    transport.pending_commands.append(
        Cs2Command(
            command_id=LOGIN_RESPONSE_COMMAND_ID,
            payload=b'{"token":"sensitive-value"',
        )
    )

    with pytest.raises(MissError) as error:
        await session.connect_and_start(clock.now + 5)

    assert error.value.detail == "login_response_malformed"
    assert error.value.__suppress_context__ is True
    assert "sensitive-value" not in str(error.value)


async def test_login_write_is_bounded_by_deadline(
    bootstrap, clock, default_profile
):
    class BlockingWriteTransport(FakeMissTransport):
        async def write_command(self, command):
            await asyncio.Future()

    sess = MissSession(
        bootstrap=bootstrap,
        transport=BlockingWriteTransport(clock=clock),
        profile=default_profile,
        lens="primary",
        clock=clock,
    )

    with pytest.raises(MissError, match="operation_timeout"):
        await sess.connect_and_start(clock.now + 0.01)

    assert sess.state == "failed"
    assert sess.transport.closed is True


async def test_start_media_write_is_bounded_by_deadline(
    bootstrap, clock, default_profile
):
    class BlockingStartTransport(FakeMissTransport):
        async def write_command(self, command):
            if command.command_id == ENCRYPTED_WRAPPER_COMMAND_ID:
                await asyncio.Future()
            await super().write_command(command)

    transport = BlockingStartTransport(clock=clock)
    transport.pending_commands.append(
        Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b"")
    )
    sess = MissSession(
        bootstrap=bootstrap,
        transport=transport,
        profile=default_profile,
        lens="primary",
        clock=clock,
    )

    with pytest.raises(MissError, match="operation_timeout"):
        await sess.connect_and_start(clock.now + 0.01)

    assert sess.state == "failed"
    assert transport.closed is True


async def test_login_sends_plaintext_command_zero(session, transport):
    """Step 1: login command ID 0x100 carries plaintext JSON before encryption."""
    await session._send_login()
    assert transport.last_command_id == LOGIN_COMMAND_ID
    login = json.loads(transport.outbound_commands[-1].payload)
    assert login == {
        "cmd": "login",
        "pubkey": session.bootstrap.client_public_key.hex(),
        "p2p_id": "peer",
        "sign": "sig-redacted",
    }


async def test_login_response_is_recognized(session, transport):
    """Login response 0x101 transitions the session to ENCRYPTED state."""
    transport.pending_commands.append(
        Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b"")
    )
    await session._await_login_response(session.clock.now + 5)
    assert session._state == "encrypted"


# ---- Start media payload ----------------------------------------------


@pytest.mark.parametrize(
    ("lens", "expected"),
    [
        ("primary", {"videoquality": 0, "enableaudio": 1}),
        ("secondary", {"videoquality": -1, "videoquality2": 0, "enableaudio": 1}),
    ],
)
async def test_start_media_payload_format(bootstrap, transport, clock, lens, expected):
    """Primary uses videoquality; secondary uses videoquality + videoquality2."""
    profile = P2PProfile(
        lenses=("primary", "secondary"),
        transport="auto",
        raw_quality=0,
        request_audio=True,
        required_video_codec=None,
        required_audio_codec=None,
    )
    sess = MissSession(
        bootstrap=bootstrap,
        transport=transport,
        profile=profile,
        lens=lens,
        clock=clock,
    )
    sess._shared_key = derive_shared_key(
        bootstrap.client_private_key, bootstrap.device_public_key
    )
    transport.attach_shared_key(sess._shared_key)
    await sess.start_media(
        lens=lens,
        raw_quality=0,
        request_audio=True,
    )
    assert transport.last_command_id == ENCRYPTED_WRAPPER_COMMAND_ID
    assert transport.last_decrypted_inner_id == START_MEDIA_COMMAND_ID
    assert transport.last_decrypted_json == expected


async def test_start_media_quality_other_than_zero_uses_raw_quality(session, transport):
    """A non-zero raw_quality replaces 0 with the chosen value."""
    sess = MissSession(
        bootstrap=session.bootstrap,
        transport=transport,
        profile=session.profile,
        lens="primary",
        clock=session.clock,
        raw_quality=2,
    )
    sess._shared_key = derive_shared_key(
        session.bootstrap.client_private_key, session.bootstrap.device_public_key
    )
    await sess.start_media(
        lens="primary",
        raw_quality=2,
        request_audio=True,
    )
    assert transport.last_decrypted_json == {"videoquality": 2, "enableaudio": 1}


# ---- Stop media -------------------------------------------------------


async def test_stop_media_sends_encrypted_command(session, transport):
    """Stop-media uses command id 0x103 encrypted under the shared key."""
    session._shared_key = derive_shared_key(
        session.bootstrap.client_private_key, session.bootstrap.device_public_key
    )
    session._state = "published"
    await session.stop_media()
    assert transport.last_command_id == ENCRYPTED_WRAPPER_COMMAND_ID
    assert transport.last_decrypted_inner_id == STOP_MEDIA_COMMAND_ID
    assert transport.last_decrypted_json == {"stop": 1}


# ---- Quality rejection -------------------------------------------------


async def test_generic_quality_rejected_with_quality_unsupported_category():
    """A profile with raw_quality outside {0..4} raises `quality_unsupported`."""
    bad_profile = P2PProfile(
        lenses=("primary",),
        transport="auto",
        raw_quality=99,
        request_audio=True,
        required_video_codec=None,
        required_audio_codec=None,
    )
    sess = MissSession(
        bootstrap=make_bootstrap(),
        transport=FakeMissTransport(clock=FakeClock()),
        profile=bad_profile,
        lens="primary",
        clock=FakeClock(),
    )
    with pytest.raises(MissError) as exc:
        await sess.connect_and_start(sess.clock.now + 5)
    assert exc.value.category == MissErrorCategory.MEDIA
    assert "quality_unsupported" in exc.value.detail
    assert sess.transport.outbound_commands == []


# ---- Unknown message --------------------------------------------------


async def test_unknown_login_message_is_counted_and_ignored(
    session, transport, bootstrap, clock
):
    shared_key = derive_shared_key(
        bootstrap.client_private_key, bootstrap.device_public_key
    )
    transport.pending_commands.extend(
        [
            Cs2Command(command_id=0xDEAD, payload=b"{}"),
            Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b""),
        ]
    )
    transport.pending_media.extend(
        [
            make_media_packet(
                shared_key,
                4,
                assemble_annex_b(
                    [H264_SPS_1280X720, b"\x68pps", b"\x65idr"]
                ),
            ),
            make_media_packet(shared_key, 1027, b"\xd5" * 4, sequence=1),
        ]
    )

    await session.connect_and_start(clock.now + 5)

    assert session._unknown_messages == 1



# ---- Malformed state -------------------------------------------------


async def test_second_initial_connect_is_rejected_as_invalid_state(
    session, transport, bootstrap, clock
):
    shared_key = derive_shared_key(
        bootstrap.client_private_key, bootstrap.device_public_key
    )
    transport.pending_commands.append(
        Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b"")
    )
    transport.pending_media.extend(
        [
            make_media_packet(
                shared_key,
                4,
                assemble_annex_b(
                    [H264_SPS_1280X720, b"\x68pps", b"\x65idr"]
                ),
            ),
            make_media_packet(shared_key, 1027, b"\xd5" * 4, sequence=1),
        ]
    )
    await session.connect_and_start(clock.now + 5)

    with pytest.raises(MissError, match="session_state_invalid"):
        await session.connect_and_start(clock.now + 5)


# ---- Cancellation -----------------------------------------------------


async def test_cancellation_during_public_login_closes_session(
    bootstrap, clock, default_profile
):
    class BlockingLoginTransport(FakeMissTransport):
        def __init__(self, clock):
            super().__init__(clock=clock)
            self.read_started = asyncio.Event()

        async def read_command(self, timeout=None):
            self.last_read_command_timeout = timeout
            self.read_started.set()
            await asyncio.Future()

    transport = BlockingLoginTransport(clock)
    sess = MissSession(
        bootstrap=bootstrap,
        transport=transport,
        profile=default_profile,
        lens="primary",
        clock=clock,
    )
    task = asyncio.create_task(sess.connect_and_start(clock.now + 5))
    await transport.read_started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert sess.state == "failed"
    assert sess._closed is True
    assert sess._shared_key is None
    assert sess.contract is None
    assert transport.closed is True
    assert sess._reconnect_count == 0


async def test_cancellation_during_media_probe_clears_runtime_state(
    bootstrap, clock, default_profile
):
    class BlockingMediaTransport(FakeMissTransport):
        def __init__(self, clock):
            super().__init__(clock=clock)
            self.media_read_started = asyncio.Event()

        async def read_media_packet(self, timeout=None):
            self.last_read_media_timeout = timeout
            self.media_read_started.set()
            await asyncio.Future()

    transport = BlockingMediaTransport(clock)
    transport.pending_commands.append(
        Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b"")
    )
    sess = MissSession(
        bootstrap=bootstrap,
        transport=transport,
        profile=default_profile,
        lens="primary",
        clock=clock,
    )
    task = asyncio.create_task(sess.connect_and_start(clock.now + 5))
    await transport.media_read_started.wait()
    assert sess._shared_key is not None

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert sess.state == "failed"
    assert sess._closed is True
    assert sess._shared_key is None
    assert sess.contract is None
    assert sess._candidate_video_codec is None
    assert sess._candidate_audio_codec is None
    assert sess._last_complete_video_at is None
    assert sess._probe.contract is None
    assert transport.closed is True


# ---- Recovery / session slice -------------------------------------------


@pytest.fixture
def published_session(bootstrap, clock, default_profile):
    """Session that already completed an initial probe + publish."""
    shared_key = derive_shared_key(
        bootstrap.client_private_key, bootstrap.device_public_key
    )

    class _Transport(FakeMissTransport):
        def attach_shared_key(self, key):
            super().attach_shared_key(key)
            self._key = key

    transport = _Transport(clock=clock)
    transport._key = shared_key
    transport.attach_shared_key(shared_key)
    transport.pending_commands.append(
        Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b"")
    )
    transport.pending_media.extend(
        [
            make_media_packet(
                shared_key,
                4,
                assemble_annex_b([H264_SPS_1280X720, b"\x68pps", b"\x65idr"]),
            ),
            make_media_packet(
                shared_key,
                1027,
                b"\xd5\xd5\xd5\xd5",
                sequence=1,
                timestamp=1020,
            ),
        ]
    )
    sess = MissSession(
        bootstrap=bootstrap,
        transport=transport,
        profile=default_profile,
        lens="primary",
        clock=clock,
    )
    return sess, transport, shared_key


async def _publish(sess):
    return await sess.connect_and_start(sess.clock.now + 5)


async def test_subscribe_returns_unique_opaque_tokens_for_current_generation(
    published_session,
):
    sess, _, _ = published_session
    await _publish(sess)

    first = sess.subscribe(generation=sess.generation)
    second = sess.subscribe(generation=sess.generation)

    assert first != second
    assert len(first.token) == 16
    assert len(sess._subscriptions) == 2
    assert sess.subscription_future(first).done() is False


async def test_subscribe_rejects_stale_generation(published_session):
    sess, _, _ = published_session
    await _publish(sess)
    with pytest.raises(MissError, match="subscription_stale_generation"):
        sess.subscribe(generation=sess.generation - 1)


async def test_soft_restart_matching_contract_keeps_generation(
    published_session, default_profile
):
    sess, transport, shared_key = published_session
    await _publish(sess)
    generation = sess.generation
    sess.acquire_lease()
    # Resend the same complete keyframe + audio so the soft restart reprobes
    # a matching contract.
    transport.pending_media.extend(
        [
            make_media_packet(
                shared_key,
                4,
                assemble_annex_b([H264_SPS_1280X720, b"\x68pps", b"\x65idr"]),
                sequence=10,
                timestamp=1500,
            ),
            make_media_packet(
                shared_key,
                1027,
                b"\xd5\xd5\xd5\xd5",
                sequence=11,
                timestamp=1510,
            ),
        ]
    )

    await sess.soft_restart(sess.clock.now + 5)

    assert sess.generation == generation
    assert sess._soft_restart_used is False
    assert sess._soft_restart_attempts == 1
    assert sess._soft_restart_successes == 1
    assert transport.closed is False
    stop_calls = [
        cmd
        for cmd in transport.outbound_commands
        if cmd.command_id == ENCRYPTED_WRAPPER_COMMAND_ID
    ]
    decrypted_ids = []
    for cmd in stop_calls:
        plaintext = miss_decode(shared_key, cmd.payload)
        decrypted_ids.append(int.from_bytes(plaintext[:4], "big"))
    assert STOP_MEDIA_COMMAND_ID in decrypted_ids


async def test_soft_restart_increments_generation_on_mismatch(
    published_session
):
    sess, transport, shared_key = published_session
    await _publish(sess)
    generation = sess.generation
    sess.acquire_lease()
    subscription = sess.subscribe(generation=generation)
    terminal = sess.subscription_future(subscription)

    # Change a parameter set so the recovered contract differs.
    big_sps = H264_SPS_1280X720[:-1] + bytes([0x24])
    transport.pending_media.extend(
        [
            make_media_packet(
                shared_key,
                4,
                assemble_annex_b([big_sps, b"\x68pps2", b"\x65idr2"]),
                sequence=20,
                timestamp=2000,
            ),
            make_media_packet(
                shared_key,
                1027,
                b"\xd5\xd5\xd5\xd5",
                sequence=21,
                timestamp=2010,
            ),
        ]
    )

    await sess.soft_restart(sess.clock.now + 5)

    assert terminal.done() is True
    with pytest.raises(MissError, match="codec_contract_changed"):
        await terminal
    assert sess.generation == generation + 1
    assert sess._soft_restart_used is False


async def test_soft_restart_rejects_incompatible_candidate_before_publication(
    published_session,
):
    sess, transport, shared_key = published_session
    sess.profile = replace(sess.profile, required_video_codec=4)
    contract = await _publish(sess)
    generation = sess.generation
    initial_complete_at = sess._last_complete_video_at
    sess.acquire_lease()
    sess.clock.advance(1)
    transport.pending_media.extend(
        [
            make_media_packet(
                shared_key,
                5,
                assemble_annex_b(
                    [
                        b"\x40\x01vps",
                        b"\x42\x01sps",
                        b"\x44\x01pps",
                        b"\x26\x01idr",
                    ]
                ),
                sequence=30,
                timestamp=2500,
            ),
            make_media_packet(
                shared_key,
                1027,
                b"\xd5\xd5\xd5\xd5",
                sequence=31,
                timestamp=2510,
            ),
        ]
    )

    with pytest.raises(MissError, match="codec_required_unsatisfied"):
        await sess.soft_restart(sess.clock.now + 5)

    assert sess.contract is contract
    assert sess.generation == generation
    assert sess._last_complete_video_at == initial_complete_at
    assert sess.state == "reprobing"


async def test_soft_restart_stop_and_start_share_command_deadline(
    published_session,
):
    sess, transport, shared_key = published_session
    await _publish(sess)
    sess.acquire_lease()
    original_write = transport.write_command

    async def consume_deadline(command):
        if command.command_id == ENCRYPTED_WRAPPER_COMMAND_ID:
            plaintext = miss_decode(shared_key, command.payload)
            if int.from_bytes(plaintext[:4], "big") == STOP_MEDIA_COMMAND_ID:
                sess.clock.advance(5)
        await original_write(command)

    transport.write_command = consume_deadline
    outbound_before = len(transport.outbound_commands)

    with pytest.raises(MissError, match="operation_timeout"):
        await sess.soft_restart(sess.clock.now + 5)

    recovery_commands = transport.outbound_commands[outbound_before:]
    assert len(recovery_commands) == 1
    plaintext = miss_decode(shared_key, recovery_commands[0].payload)
    assert int.from_bytes(plaintext[:4], "big") == STOP_MEDIA_COMMAND_ID


async def test_soft_restart_stops_when_lease_expires_after_stop(
    published_session,
):
    sess, transport, shared_key = published_session
    await _publish(sess)
    sess.acquire_lease()
    original_write = transport.write_command

    async def release_after_stop(command):
        await original_write(command)
        if command.command_id == ENCRYPTED_WRAPPER_COMMAND_ID:
            plaintext = miss_decode(shared_key, command.payload)
            if int.from_bytes(plaintext[:4], "big") == STOP_MEDIA_COMMAND_ID:
                sess.release_lease()

    transport.write_command = release_after_stop
    outbound_before = len(transport.outbound_commands)

    with pytest.raises(MissError, match="recovery_no_active_lease"):
        await sess.soft_restart(sess.clock.now + 5)

    assert transport.closed is True
    assert len(transport.outbound_commands) == outbound_before + 1


async def test_soft_restart_requires_active_lease(published_session):
    sess, _, _ = published_session
    await _publish(sess)
    with pytest.raises(MissError, match="recovery_no_active_lease"):
        await sess.soft_restart(sess.clock.now + 5)


async def test_full_reconnect_matching_contract_uses_fresh_bootstrap(
    published_session,
):
    sess, transport, _ = published_session
    contract = await _publish(sess)
    generation = sess.generation
    sess.acquire_lease()
    subscription = sess.subscribe(generation=generation)
    terminal = sess.subscription_future(subscription)
    bootstrap_count = {"calls": 0}
    sess.bootstrap_factory = _make_reconnect_factory(
        sess, bootstrap_count
    )
    before = sess._reconnect_count

    recovered = await sess.reconnect(sess.clock.now + 5)

    assert recovered == contract
    assert sess.contract is contract
    assert sess.generation == generation
    assert terminal.done() is False
    assert bootstrap_count["calls"] == 1
    assert sess._reconnect_count == before + 1
    assert sess.bootstrap.host == "192.168.1.99"
    assert transport.closed is True


async def test_full_reconnect_mismatch_terminates_old_generation(
    published_session,
):
    sess, _, _ = published_session
    contract = await _publish(sess)
    generation = sess.generation
    sess.acquire_lease()
    subscription = sess.subscribe(generation=generation)
    terminal = sess.subscription_future(subscription)
    bootstrap_count = {"calls": 0}
    sess.bootstrap_factory = _make_reconnect_factory(
        sess,
        bootstrap_count,
        pps=b"\x68replacement-pps",
    )

    recovered = await sess.reconnect(sess.clock.now + 5)

    assert recovered != contract
    assert terminal.done() is True
    with pytest.raises(MissError, match="codec_contract_changed"):
        await terminal
    assert sess.contract is recovered
    assert sess.generation == generation + 1
    assert bootstrap_count["calls"] == 1


async def test_full_reconnect_requires_active_lease(published_session):
    sess, _, _ = published_session
    await _publish(sess)
    with pytest.raises(MissError, match="recovery_no_active_lease"):
        await sess.reconnect(sess.clock.now + 5)


async def test_sequence_gap_forces_full_reconnect(published_session):
    sess, transport, _ = published_session
    await _publish(sess)
    sess.acquire_lease()
    bootstrap_count = {"calls": 0}
    sess.bootstrap_factory = _make_reconnect_factory(
        sess, bootstrap_count
    )

    await sess.handle_sequence_gap(sess.clock.now + 5)

    assert bootstrap_count["calls"] == 1
    assert sess._soft_restart_attempts == 0
    assert transport.closed is True


async def test_recovery_retries_with_backoff_then_resets(
    published_session,
    monkeypatch,
):
    sess, _, _ = published_session
    await _publish(sess)
    sess.acquire_lease()
    bootstrap_count = {"calls": 0}
    sleeps = []
    monkeypatch.setattr(
        miss_module.random,
        "uniform",
        lambda lower, upper: (lower + upper) / 2,
    )

    async def record_sleep(delay):
        sleeps.append(delay)
        await sess.clock.sleep(delay)

    sess._sleep = record_sleep
    sess.bootstrap_factory = _make_reconnect_factory(
        sess,
        bootstrap_count,
        failures=5,
    )

    await sess.reconnect(sess.clock.now + 60)

    assert bootstrap_count["calls"] == 6
    assert sleeps == [1, 2, 5, 15, 30]
    assert sess._reconnect_attempt == 0


async def test_recovery_backoff_is_jittered_and_capped(
    published_session,
    monkeypatch,
):
    sess, _, _ = published_session
    await _publish(sess)
    bounds = []

    def upper_bound(lower, upper):
        bounds.append((lower, upper))
        return upper

    monkeypatch.setattr(miss_module.random, "uniform", upper_bound)

    assert sess._recovery_backoff_delay(attempt=1) == pytest.approx(1.2)
    assert sess._recovery_backoff_delay(attempt=5) == 30
    assert sess._recovery_backoff_delay(attempt=10) == 30
    assert bounds == [(0.8, 1.2), (24.0, 36.0), (24.0, 36.0)]


async def test_recovery_stops_when_final_lease_is_released_during_backoff(
    published_session,
):
    sess, _, _ = published_session
    await _publish(sess)
    sess.acquire_lease()
    bootstrap_count = {"calls": 0}

    async def release_lease(delay):
        sess.release_lease()
        await sess.clock.sleep(delay)

    sess._sleep = release_lease
    sess.bootstrap_factory = _make_reconnect_factory(
        sess,
        bootstrap_count,
        failures=1,
    )

    with pytest.raises(MissError, match="recovery_no_active_lease"):
        await sess.reconnect(sess.clock.now + 10)

    assert bootstrap_count["calls"] == 1


async def test_reconnect_factory_is_bounded_by_deadline(
    published_session,
):
    sess, _, _ = published_session
    await _publish(sess)
    sess.acquire_lease()

    async def blocked_factory():
        await asyncio.Future()

    sess.bootstrap_factory = blocked_factory

    with pytest.raises(MissError, match="reconnect_timeout"):
        await sess.reconnect(sess.clock.now + 0.01)


async def test_reconnect_closes_candidate_when_lease_expires_during_factory(
    published_session,
):
    sess, _, _ = published_session
    contract = await _publish(sess)
    generation = sess.generation
    sess.acquire_lease()
    candidate = FakeMissTransport(clock=sess.clock)

    async def release_during_factory():
        sess.release_lease()
        return make_bootstrap(host="192.168.1.99"), candidate

    sess.bootstrap_factory = release_during_factory

    with pytest.raises(MissError, match="recovery_no_active_lease"):
        await sess.reconnect(sess.clock.now + 5)

    assert candidate.closed is True
    assert sess.contract is contract
    assert sess.generation == generation


async def test_stall_clock_triggers_one_soft_restart(published_session):
    sess, transport, shared_key = published_session
    await _publish(sess)
    sess.acquire_lease()
    bootstrap_count = {"calls": 0}
    sess.clock.advance(VIDEO_STALL_DEADLINE_SECONDS + 1)
    transport.pending_media.extend(
        [
            make_media_packet(
                shared_key,
                4,
                assemble_annex_b(
                    [H264_SPS_1280X720, b"\x68pps", b"\x65idr"]
                ),
                sequence=40,
                timestamp=3000,
            ),
            make_media_packet(
                shared_key,
                1027,
                b"\xd5\xd5\xd5\xd5",
                sequence=41,
                timestamp=3010,
            ),
        ]
    )
    sess.bootstrap_factory = _make_reconnect_factory(
        sess, bootstrap_count
    )

    await sess.run_stall_recovery(deadline=sess.clock.now + 30)

    assert sess._soft_restart_used is False
    assert sess._soft_restart_attempts == 1
    assert sess._soft_restart_successes == 1
    assert bootstrap_count["calls"] == 0
    assert sess._last_complete_video_at == sess.clock.now


async def test_stall_clock_after_soft_restart_failure_forces_reconnect(
    published_session,
):
    sess, _, _ = published_session
    await _publish(sess)
    sess.acquire_lease()
    bootstrap_count = {"calls": 0}
    sess.bootstrap_factory = _make_reconnect_factory(
        sess, bootstrap_count
    )
    sess.clock.advance(VIDEO_STALL_DEADLINE_SECONDS + 1)

    await sess.run_stall_recovery(deadline=sess.clock.now + 30)

    assert sess._soft_restart_attempts == 1
    assert sess._soft_restart_successes == 0
    assert sess._soft_restart_used is False
    assert bootstrap_count["calls"] == 1


async def test_only_complete_video_refreshes_stall_clock(
    published_session,
):
    sess, _, shared_key = published_session
    await _publish(sess)
    initial = sess._last_complete_video_at
    sess.clock.advance(4)

    await sess._process_media_packet(
        make_media_packet(
            shared_key,
            1027,
            b"\xd5\xd5\xd5\xd5",
            sequence=50,
            timestamp=4000,
        )
    )

    assert sess._last_complete_video_at == initial
    sess.clock.advance(1)

    await sess._process_media_packet(
        make_media_packet(
            shared_key,
            4,
            assemble_annex_b([b"\x01delta"]),
            sequence=51,
            timestamp=4010,
        )
    )

    assert sess._last_complete_video_at == sess.clock.now


async def test_concurrent_sequence_gaps_share_one_reconnect_owner(
    published_session,
):
    sess, _, _ = published_session
    await _publish(sess)
    sess.acquire_lease()
    entered = asyncio.Event()
    release = asyncio.Event()
    bootstrap_count = {"calls": 0}

    class BlockingTransport(FakeMissTransport):
        async def write_command(self, command):
            if command.command_id == LOGIN_COMMAND_ID and not entered.is_set():
                entered.set()
                await release.wait()
            return await super().write_command(command)

    async def factory():
        bootstrap_count["calls"] += 1
        bootstrap = make_bootstrap(host="192.168.1.99")
        shared_key = derive_shared_key(
            bootstrap.client_private_key,
            bootstrap.device_public_key,
        )
        transport_type = (
            BlockingTransport
            if bootstrap_count["calls"] == 1
            else FakeMissTransport
        )
        transport = transport_type(clock=sess.clock)
        transport.attach_shared_key(shared_key)
        transport.pending_commands.append(
            Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b"")
        )
        transport.pending_media.extend(
            [
                make_media_packet(
                    shared_key,
                    4,
                    assemble_annex_b(
                        [H264_SPS_1280X720, b"\x68pps", b"\x65idr"]
                    ),
                ),
                make_media_packet(
                    shared_key,
                    1027,
                    b"\xd5\xd5\xd5\xd5",
                    sequence=1,
                    timestamp=1020,
                ),
            ]
        )
        return bootstrap, transport

    sess.bootstrap_factory = factory
    deadline = sess.clock.now + 30
    first = asyncio.create_task(sess.handle_sequence_gap(deadline))
    await entered.wait()
    second = asyncio.create_task(sess.handle_sequence_gap(deadline))
    await asyncio.sleep(0)
    release.set()

    first_contract, second_contract = await asyncio.gather(first, second)

    assert first_contract == second_contract
    assert bootstrap_count["calls"] == 1


async def test_concurrent_recovery_waiters_share_owner_failure(
    published_session,
):
    sess, _, _ = published_session
    await _publish(sess)
    sess.acquire_lease()
    entered = asyncio.Event()
    release = asyncio.Event()
    bootstrap_count = {"calls": 0}

    async def failing_factory():
        bootstrap_count["calls"] += 1
        entered.set()
        await release.wait()
        raise MissError(
            MissErrorCategory.TRANSPORT,
            "reconnect_attempt_failed",
        )

    sess.bootstrap_factory = failing_factory
    deadline = sess.clock.now + 0.5
    first = asyncio.create_task(sess.handle_sequence_gap(deadline))
    await entered.wait()
    second = asyncio.create_task(sess.handle_sequence_gap(deadline))
    await asyncio.sleep(0)
    release.set()

    results = await asyncio.gather(first, second, return_exceptions=True)

    assert bootstrap_count["calls"] == 1
    assert all(
        isinstance(result, MissError)
        and result.detail == "reconnect_attempt_failed"
        for result in results
    )


def _make_reconnect_factory(
    sess,
    counter,
    *,
    sps=H264_SPS_1280X720,
    pps=b"\x68pps",
    failures=0,
):
    async def factory():
        counter["calls"] += 1
        if counter["calls"] <= failures:
            raise MissError(
                MissErrorCategory.TRANSPORT,
                "reconnect_attempt_failed",
            )
        bootstrap = make_bootstrap(host="192.168.1.99")
        shared_key = derive_shared_key(
            bootstrap.client_private_key,
            bootstrap.device_public_key,
        )
        transport = FakeMissTransport(clock=sess.clock)
        transport.attach_shared_key(shared_key)
        transport.pending_commands.append(
            Cs2Command(command_id=LOGIN_RESPONSE_COMMAND_ID, payload=b"")
        )
        transport.pending_media.extend(
            [
                make_media_packet(
                    shared_key,
                    4,
                    assemble_annex_b([sps, pps, b"\x65idr"]),
                ),
                make_media_packet(
                    shared_key,
                    1027,
                    b"\xd5\xd5\xd5\xd5",
                    sequence=1,
                    timestamp=1020,
                ),
            ]
        )
        return bootstrap, transport

    return factory


async def test_stop_media_sends_encrypted_command_after_publication(
    published_session,
):
    sess, _, _ = published_session
    await _publish(sess)
    outbound_before = list(sess.transport.outbound_commands)
    await sess.stop_media()
    assert sess.transport.last_command_id == ENCRYPTED_WRAPPER_COMMAND_ID
    assert sess.transport.last_decrypted_json == {"stop": 1}
    assert len(sess.transport.outbound_commands) == len(outbound_before) + 1

