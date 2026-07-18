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
from dataclasses import dataclass, field
from pathlib import Path

import pytest

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

