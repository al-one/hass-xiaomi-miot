"""MISS session: login, encrypted commands, media probe, and recovery.

This module owns one MISS session per `(did, lens)` connection. It
performs plaintext CS2 login, derives the shared key on acceptance,
encrypts subsequent MISS commands, decrypts media bodies, and drives
the media probe until a complete `MediaContract` is published.

Recovery state (soft restart and full reconnect) is owned by the
manager (Task 12). This module exposes the session-facing primitives
the manager calls into.

Secret material is never logged or included in `MissError` text.
"""

from __future__ import annotations

import asyncio
import json
import random
import secrets
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from . import (
    MediaContract,
    MissError,
    MissErrorCategory,
    P2PProfile,
    SessionKey,
)
from .cs2.protocol import (
    Cs2Command,
    Cs2MediaPacket,
    decode_miss_media_header,
    encode_outbound_miss_plaintext,
)
from .crypto import derive_shared_key, miss_decode, miss_encode
from .media import MediaProbe


# ---- Protocol constants ------------------------------------------------

# CS2 channel-0 command IDs that frame MISS-layer messages.
LOGIN_COMMAND_ID: int = 0x100
LOGIN_RESPONSE_COMMAND_ID: int = 0x101
ENCRYPTED_WRAPPER_COMMAND_ID: int = 0x1001

# MISS plaintext command IDs (carried inside the encrypted wrapper).
START_MEDIA_COMMAND_ID: int = 0x102
STOP_MEDIA_COMMAND_ID: int = 0x103

# The accepted raw_quality range; everything else is rejected with
# `quality_unsupported` before any network I/O.
VALID_RAW_QUALITIES: tuple[int, ...] = (0, 1, 2, 3, 4)

# Steady-state video-stall deadline (no structurally valid complete
# video access unit for ten seconds).
VIDEO_STALL_DEADLINE_SECONDS: float = 10.0

# Five-second monotonic reprobe deadline after start-media completes
# inside a soft restart.
SOFT_RESTART_REPROBE_SECONDS: float = 5.0

# Jittered full-reconnect backoff sequence.
RECONNECT_BACKOFF_SECONDS: tuple[int, ...] = (1, 2, 5, 15, 30)

@dataclass
class MissSession:
    """One MISS session owned by the entry-level manager.

    The session is created from a fresh bootstrap after a single CS2
    discovery exchange that yields an already-established `transport`.
    After login is accepted, all subsequent MISS commands are encrypted
    under the shared key and carried inside wrapper `0x1001`. Media
    bodies are decrypted with the same shared key.
    """

    bootstrap: object = field(repr=False)
    transport: object = field(repr=False)
    profile: P2PProfile
    lens: str
    clock: object = field(repr=False)
    raw_quality: int | None = None
    request_audio: bool | None = None

    # Internal state.
    _state: str = field(default="disconnected", init=False)
    _shared_key: Optional[bytes] = field(default=None, init=False, repr=False)
    _probe: MediaProbe = field(default=None, init=False, repr=False)
    _contract: Optional[MediaContract] = field(default=None, init=False, repr=False)
    _generation: int = field(default=0, init=False)
    _candidate_video_codec: Optional[int] = field(default=None, init=False)
    _candidate_audio_codec: Optional[int] = field(default=None, init=False)
    _unknown_messages: int = field(default=0, init=False)
    _closed: bool = field(default=False, init=False)
    bootstrap_factory: Optional[
        Callable[[], Awaitable[tuple[object, object]]]
    ] = field(default=None, repr=False)
    _active_leases: int = field(default=0, init=False)
    _subscriptions: dict[SessionKey, asyncio.Future[None]] = field(
        default_factory=dict, init=False, repr=False
    )
    _recovery_lock: asyncio.Lock = field(init=False, repr=False)
    _recovery_task: Optional[asyncio.Task[MediaContract]] = field(
        default=None, init=False, repr=False
    )
    _reconnect_count: int = field(default=0, init=False)
    _reconnect_attempt: int = field(default=0, init=False)
    _soft_restart_used: bool = field(default=False, init=False)
    _soft_restart_attempts: int = field(default=0, init=False)
    _soft_restart_successes: int = field(default=0, init=False)
    _last_complete_video_at: Optional[float] = field(default=None, init=False)
    _sleep: Optional[Callable[[float], Awaitable[None]]] = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        if self.raw_quality is None:
            self.raw_quality = self.profile.raw_quality
        if self.request_audio is None:
            self.request_audio = self.profile.request_audio
        self._probe = MediaProbe(
            clock=self.clock,
            audio_wait_seconds=2.0 if self.request_audio else 0.0,
        )
        self._recovery_lock = asyncio.Lock()
        self._sleep = self.clock.sleep

    @property
    def state(self) -> str:
        return self._state

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def contract(self) -> MediaContract | None:
        return self._contract

    async def connect_and_start(self, deadline: float) -> MediaContract:
        """Login, start media, and publish the initial complete contract."""
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "session_closed")
        if self._state != "disconnected":
            raise MissError(MissErrorCategory.MEDIA, "session_state_invalid")
        if self.clock.now >= deadline:
            raise MissError(MissErrorCategory.TIMEOUT, "media_probe_timeout")
        if self.lens not in self.profile.lenses:
            raise MissError(MissErrorCategory.MEDIA, "lens_not_supported")
        self._validate_quality()
        self._state = "connecting"
        try:
            await self._attempt_login(deadline)
            await self._send_start_media(deadline)
            self._state = "probing"
            while self.clock.now < deadline:
                contract = self._probe.contract
                if contract is not None:
                    return self._publish_initial_contract(contract)

                timeout = deadline - self.clock.now
                complete_at = self._probe.last_complete_video_at
                if complete_at is not None and self.request_audio:
                    timeout = min(timeout, max(0.0, complete_at + 2.0 - self.clock.now))
                if timeout <= 0:
                    continue
                try:
                    packet = await self.transport.read_media_packet(timeout=timeout)
                except MissError as exc:
                    if exc.category != MissErrorCategory.TIMEOUT:
                        raise
                    contract = self._probe.contract
                    if contract is not None:
                        return self._publish_initial_contract(contract)
                    if self.clock.now >= deadline:
                        break
                    continue
                await self._process_media_packet(packet)
            raise MissError(MissErrorCategory.TIMEOUT, "media_probe_timeout")
        except asyncio.CancelledError:
            await self._abort()
            raise
        except asyncio.IncompleteReadError:
            self._state = "failed"
            await self.transport.close()
            raise MissError(
                MissErrorCategory.TRANSPORT, "connection_lost"
            ) from None
        except MissError:
            self._state = "failed"
            await self.transport.close()
            raise

    def _publish_initial_contract(self, contract: MediaContract) -> MediaContract:
        self._candidate_video_codec = contract.video_codec
        self._candidate_audio_codec = contract.audio_codec
        self._enforce_mandatory_codecs()
        self._contract = contract
        self._generation = 1
        self._last_complete_video_at = self._probe.last_complete_video_at
        self._state = "published"
        return contract

    async def start_media(
        self,
        *,
        lens: str,
        raw_quality: int,
        request_audio: bool,
    ) -> None:
        """Send one resolved start-media command on an authenticated session."""
        if lens not in self.profile.lenses:
            raise MissError(MissErrorCategory.MEDIA, "lens_not_supported")
        previous = (self.lens, self.raw_quality, self.request_audio)
        self.lens, self.raw_quality, self.request_audio = (
            lens,
            raw_quality,
            request_audio,
        )
        try:
            self._validate_quality()
            await self._send_start_media()
        finally:
            self.lens, self.raw_quality, self.request_audio = previous

    # ---- Internal state helpers ---------------------------------------

    def _require_state(self, *allowed: str) -> None:
        if self._state not in allowed:
            raise MissError(MissErrorCategory.MEDIA, "session_state_invalid")

    def _record_unknown(self, command_id: int) -> None:
        self._unknown_messages += 1
        # Unknown command IDs are counted and ignored per the spec.

    # ---- Quality and codec validation -------------------------------

    def _validate_quality(self) -> None:
        if self.raw_quality not in VALID_RAW_QUALITIES:
            raise MissError(
                MissErrorCategory.MEDIA,
                "quality_unsupported",
            )

    def _enforce_mandatory_codecs(self) -> None:
        required_video = self.profile.required_video_codec
        required_audio = self.profile.required_audio_codec
        if (
            required_video is not None
            and self._candidate_video_codec != required_video
        ):
            raise MissError(
                MissErrorCategory.MEDIA,
                "codec_required_unsatisfied",
            )
        if (
            required_audio is not None
            and self._candidate_audio_codec != required_audio
        ):
            raise MissError(
                MissErrorCategory.MEDIA,
                "codec_required_unsatisfied",
            )

    # ---- Login sequence -----------------------------------------------

    async def _default_login_impl(self, deadline: float) -> None:
        """Default login: send plaintext 0x100 and await plaintext 0x101."""
        await self._send_login(deadline)
        await self._await_login_response(deadline)

    async def _send_login(self, deadline: float | None = None) -> None:
        """Send the plaintext CS2 login command on wrapper id 0x100."""
        body = self._build_login_body()
        await self._write_command(
            Cs2Command(command_id=LOGIN_COMMAND_ID, payload=body), deadline
        )

    def _build_login_body(self) -> bytes:
        """Build the plaintext JSON login body.

        The body carries the ephemeral client public key and the cloud
        signature from the bootstrap. Hex encoding is deliberately
        lowercase.
        """
        public_key_hex = self.bootstrap.client_public_key.hex()
        payload = {
            "cmd": "login",
            "pubkey": public_key_hex,
            "p2p_id": self.bootstrap.p2p_id or "",
            "sign": self.bootstrap.signature,
        }
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    async def _await_login_response(self, deadline: float) -> None:
        """Wait for the plaintext login response command id 0x101."""
        while self.clock.now < deadline:
            cmd = await self.transport.read_command(
                timeout=deadline - self.clock.now
            )
            if cmd.command_id != LOGIN_RESPONSE_COMMAND_ID:
                self._record_unknown(cmd.command_id)
                continue
            if cmd.payload:
                try:
                    response = json.loads(cmd.payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise MissError(
                        MissErrorCategory.AUTH, "login_response_malformed"
                    ) from None
                if not isinstance(response, dict):
                    raise MissError(
                        MissErrorCategory.AUTH, "login_response_malformed"
                    )
                if response.get("code", 0) != 0 or response.get("result") is False:
                    raise MissError(MissErrorCategory.AUTH, "login_rejected")
            self._shared_key = derive_shared_key(
                self.bootstrap.client_private_key,
                self.bootstrap.device_public_key,
            )
            self._state = "encrypted"
            return
        raise MissError(MissErrorCategory.TIMEOUT, "login_timeout")

    async def _attempt_login(self, deadline: float) -> None:
        """Run login and propagate cancellation without reconnecting."""
        self._state = "logging_in"
        try:
            await self._default_login_impl(deadline)
        except asyncio.CancelledError:
            self._state = "disconnected"
            raise

    # ---- Encrypted MISS command helper -------------------------------

    async def _write_command(
        self, command: Cs2Command, deadline: float | None
    ) -> None:
        if deadline is None:
            await self.transport.write_command(command)
            return
        remaining = deadline - self.clock.now
        if remaining <= 0:
            raise MissError(MissErrorCategory.TIMEOUT, "operation_timeout")
        try:
            await asyncio.wait_for(
                self.transport.write_command(command), timeout=remaining
            )
        except TimeoutError:
            raise MissError(
                MissErrorCategory.TIMEOUT, "operation_timeout"
            ) from None

    async def _send_miss_command(
        self,
        inner_id: int,
        body: dict | bytes,
        deadline: float | None = None,
    ) -> None:
        """Encrypt `body` under the shared key and send as wrapper 0x1001."""
        if self._shared_key is None:
            raise MissError(
                MissErrorCategory.AUTH,
                "shared_key_missing",
            )
        if isinstance(body, dict):
            payload_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
        else:
            payload_bytes = bytes(body)
        plaintext = encode_outbound_miss_plaintext(inner_id, payload_bytes)
        encrypted = miss_encode(self._shared_key, plaintext)
        await self._write_command(
            Cs2Command(
                command_id=ENCRYPTED_WRAPPER_COMMAND_ID,
                payload=encrypted,
            ),
            deadline,
        )

    # ---- Start / stop media -------------------------------------------

    async def _send_start_media(self, deadline: float | None = None) -> None:
        """Send the resolved start-media payload under the shared key."""
        if self.lens == "primary":
            payload: dict[str, Any] = {
                "videoquality": self.raw_quality,
                "enableaudio": 1 if self.request_audio else 0,
            }
        elif self.lens == "secondary":
            payload = {
                "videoquality": -1,
                "videoquality2": self.raw_quality,
                "enableaudio": 1 if self.request_audio else 0,
            }
        else:
            raise MissError(
                MissErrorCategory.MEDIA,
                "lens_not_supported",
            )
        await self._send_miss_command(
            START_MEDIA_COMMAND_ID, payload, deadline
        )

    async def stop_media(self, deadline: float | None = None) -> None:
        """Send the stop-media command under the shared key."""
        await self._send_miss_command(
            STOP_MEDIA_COMMAND_ID, {"stop": 1}, deadline
        )

    # ---- Subscriptions ------------------------------------------------

    def acquire_lease(self) -> None:
        self._active_leases += 1

    def release_lease(self) -> None:
        if self._active_leases <= 0:
            raise MissError(MissErrorCategory.MEDIA, "lease_not_active")
        self._active_leases -= 1

    def subscribe(self, *, generation: int) -> SessionKey:
        if self._state != "published" or self._contract is None:
            raise MissError(MissErrorCategory.MEDIA, "session_state_invalid")
        if generation != self._generation:
            raise MissError(
                MissErrorCategory.MEDIA, "subscription_stale_generation"
            )
        key = SessionKey(token=secrets.token_bytes(16))
        self._subscriptions[key] = asyncio.get_running_loop().create_future()
        return key

    def subscription_future(
        self, key: SessionKey
    ) -> asyncio.Future[None]:
        try:
            return self._subscriptions[key]
        except KeyError:
            raise MissError(
                MissErrorCategory.MEDIA, "subscription_not_found"
            ) from None

    def unsubscribe(self, key: SessionKey) -> None:
        future = self._subscriptions.pop(key, None)
        if future is not None and not future.done():
            future.cancel()

    # ---- Recovery primitives -----------------------------------------

    async def _serialize_recovery(
        self,
        operation: Callable[[], Awaitable[MediaContract]],
    ) -> MediaContract:
        async with self._recovery_lock:
            task = self._recovery_task
            if task is None:
                task = asyncio.create_task(operation())
                self._recovery_task = task
                task.add_done_callback(self._finish_recovery_task)
        return await asyncio.shield(task)

    def _finish_recovery_task(
        self, task: asyncio.Task[MediaContract]
    ) -> None:
        if not task.cancelled():
            task.exception()
        if self._recovery_task is task:
            self._recovery_task = None

    async def soft_restart(self, deadline: float) -> MediaContract:
        return await self._serialize_recovery(
            lambda: self._soft_restart(deadline)
        )

    async def _soft_restart(self, command_deadline: float) -> MediaContract:
        self._require_active_lease()
        if self._soft_restart_used:
            raise MissError(
                MissErrorCategory.MEDIA, "soft_restart_already_used"
            )
        if self._state != "published":
            raise MissError(MissErrorCategory.MEDIA, "session_state_invalid")
        self._soft_restart_used = True
        self._soft_restart_attempts += 1
        await self.stop_media(command_deadline)
        await self._require_active_lease_after_io()
        await self._send_start_media(command_deadline)
        await self._require_active_lease_after_io()
        self._state = "reprobing"
        candidate = await self._reprobe_until_complete_keyframe(
            self.clock.now + SOFT_RESTART_REPROBE_SECONDS
        )
        await self._require_active_lease_after_io()
        self._validate_candidate_contract(candidate)
        self._adopt_recovered_contract(candidate)
        self._state = "published"
        self._soft_restart_successes += 1
        self._reset_recovery_episode()
        return candidate

    async def _reprobe_until_complete_keyframe(
        self, deadline: float
    ) -> MediaContract:
        self._probe = MediaProbe(
            clock=self.clock,
            audio_wait_seconds=2.0 if self.request_audio else 0.0,
        )
        while self.clock.now < deadline:
            contract = self._probe.contract
            if contract is not None:
                return contract
            timeout = deadline - self.clock.now
            complete_at = self._probe.last_complete_video_at
            if complete_at is not None and self.request_audio:
                timeout = min(
                    timeout,
                    max(0.0, complete_at + 2.0 - self.clock.now),
                )
            if timeout <= 0:
                continue
            try:
                packet = await self.transport.read_media_packet(
                    timeout=timeout
                )
            except MissError as exc:
                if exc.category != MissErrorCategory.TIMEOUT:
                    raise
                contract = self._probe.contract
                if contract is not None:
                    return contract
                if self.clock.now >= deadline:
                    break
                continue
            await self._process_media_packet(packet)
        raise MissError(MissErrorCategory.TIMEOUT, "reprobe_timeout")

    def _validate_candidate_contract(
        self, candidate: MediaContract
    ) -> None:
        self._candidate_video_codec = candidate.video_codec
        self._candidate_audio_codec = candidate.audio_codec
        self._enforce_mandatory_codecs()

    def _adopt_recovered_contract(self, candidate: MediaContract) -> None:
        if self._contract is None:
            raise MissError(MissErrorCategory.MEDIA, "contract_missing")
        if candidate == self._contract:
            self._last_complete_video_at = self._probe.last_complete_video_at
            return
        for future in self._subscriptions.values():
            if not future.done():
                future.set_exception(
                    MissError(
                        MissErrorCategory.MEDIA,
                        "codec_contract_changed",
                    )
                )
                future.add_done_callback(lambda done: done.exception())
        self._generation += 1
        self._contract = candidate
        self._last_complete_video_at = self._probe.last_complete_video_at

    def _reset_recovery_episode(self) -> None:
        self._soft_restart_used = False
        self._reconnect_attempt = 0

    def _require_active_lease(self) -> None:
        if self._active_leases <= 0:
            raise MissError(
                MissErrorCategory.MEDIA, "recovery_no_active_lease"
            )

    async def _require_active_lease_after_io(self) -> None:
        try:
            self._require_active_lease()
        except MissError:
            await self.transport.close()
            raise

    async def reconnect(self, deadline: float) -> MediaContract:
        return await self._serialize_recovery(
            lambda: self._reconnect(deadline)
        )

    async def _reconnect(self, deadline: float) -> MediaContract:
        self._require_active_lease()
        if self.bootstrap_factory is None:
            raise MissError(
                MissErrorCategory.MEDIA, "bootstrap_factory_missing"
            )
        last_error = MissError(
            MissErrorCategory.TRANSPORT, "reconnect_failed"
        )
        while self.clock.now < deadline:
            self._require_active_lease()
            if self._reconnect_attempt:
                delay = self._recovery_backoff_delay(
                    attempt=self._reconnect_attempt
                )
                if self.clock.now + delay >= deadline:
                    break
                await self._sleep(delay)
                self._require_active_lease()
            self._reconnect_attempt += 1
            self._reconnect_count += 1
            try:
                await self.transport.close()
                bootstrap, transport = (
                    await self._obtain_reconnect_transport(deadline)
                )
                self.bootstrap = bootstrap
                self.transport = transport
                await self._require_active_lease_after_io()
                candidate = await self._connect_candidate(deadline)
                self._require_active_lease()
            except asyncio.CancelledError:
                await self.transport.close()
                raise
            except MissError as exc:
                last_error = exc
                try:
                    await self.transport.close()
                except Exception:  # pragma: no cover - defensive
                    pass
                continue
            self._adopt_recovered_contract(candidate)
            self._state = "published"
            self._closed = False
            self._reset_recovery_episode()
            return candidate
        try:
            await self.transport.close()
        except Exception:  # pragma: no cover - defensive
            pass
        self._state = "failed"
        self._closed = True
        raise last_error

    async def _obtain_reconnect_transport(
        self, deadline: float
    ) -> tuple[object, object]:
        factory = self.bootstrap_factory
        if factory is None:
            raise MissError(
                MissErrorCategory.MEDIA, "bootstrap_factory_missing"
            )
        remaining = deadline - self.clock.now
        if remaining <= 0:
            raise MissError(
                MissErrorCategory.TIMEOUT, "reconnect_timeout"
            )
        try:
            result = await asyncio.wait_for(
                factory(), timeout=remaining
            )
        except TimeoutError:
            raise MissError(
                MissErrorCategory.TIMEOUT, "reconnect_timeout"
            ) from None
        bootstrap, transport = result
        if self.clock.now >= deadline:
            await transport.close()
            raise MissError(
                MissErrorCategory.TIMEOUT, "reconnect_timeout"
            )
        return bootstrap, transport

    async def _connect_candidate(self, deadline: float) -> MediaContract:
        self._shared_key = None
        self._candidate_video_codec = None
        self._candidate_audio_codec = None
        self._state = "reconnecting"
        self._closed = False
        await self._attempt_login(deadline)
        await self._require_active_lease_after_io()
        await self._send_start_media(deadline)
        await self._require_active_lease_after_io()
        self._state = "reprobing"
        candidate = await self._reprobe_until_complete_keyframe(deadline)
        await self._require_active_lease_after_io()
        self._validate_candidate_contract(candidate)
        return candidate

    async def handle_sequence_gap(self, deadline: float) -> MediaContract:
        return await self._serialize_recovery(
            lambda: self._reconnect(deadline)
        )

    def _recovery_backoff_delay(self, *, attempt: int) -> float:
        sequence = RECONNECT_BACKOFF_SECONDS
        if attempt <= 0:
            base = sequence[0]
        elif attempt > len(sequence):
            base = sequence[-1]
        else:
            base = sequence[attempt - 1]
        return min(
            float(sequence[-1]),
            random.uniform(base * 0.8, base * 1.2),
        )

    async def run_stall_recovery(
        self, *, deadline: float
    ) -> MediaContract:
        return await self._serialize_recovery(
            lambda: self._recover_stall(deadline)
        )

    async def _recover_stall(self, deadline: float) -> MediaContract:
        self._require_active_lease()
        if self._state != "published":
            raise MissError(
                MissErrorCategory.MEDIA, "session_state_invalid"
            )
        if self._last_complete_video_at is None:
            raise MissError(
                MissErrorCategory.MEDIA, "stall_clock_not_started"
            )
        if (
            self.clock.now - self._last_complete_video_at
            < VIDEO_STALL_DEADLINE_SECONDS
        ):
            raise MissError(
                MissErrorCategory.MEDIA, "stall_clock_not_elapsed"
            )
        if not self._soft_restart_used:
            try:
                return await self._soft_restart(deadline)
            except MissError:
                pass
        return await self._reconnect(deadline)

    # ---- Media feed helpers ------------------------------------------

    async def _process_media_packet(self, packet: Cs2MediaPacket) -> None:
        """Decrypt and feed one media packet to the probe."""
        if self._shared_key is None:
            raise MissError(
                MissErrorCategory.AUTH,
                "shared_key_missing",
            )
        header = decode_miss_media_header(packet.header)
        body = miss_decode(self._shared_key, packet.encrypted_body)
        previous_complete_at = self._probe.last_complete_video_at
        self._probe.feed(header, body)
        complete_at = self._probe.last_complete_video_at
        if (
            self._state == "published"
            and complete_at != previous_complete_at
        ):
            self._last_complete_video_at = complete_at

    async def _abort(self) -> None:
        self._shared_key = None
        self._contract = None
        self._candidate_video_codec = None
        self._candidate_audio_codec = None
        self._last_complete_video_at = None
        self._probe = MediaProbe(
            clock=self.clock,
            audio_wait_seconds=2.0 if self.request_audio else 0.0,
        )
        self._state = "failed"
        await self.close()

    # ---- Close --------------------------------------------------------

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self.transport.close()
        except Exception:  # pragma: no cover - defensive
            pass


__all__ = [
    "ENCRYPTED_WRAPPER_COMMAND_ID",
    "LOGIN_COMMAND_ID",
    "LOGIN_RESPONSE_COMMAND_ID",
    "MissSession",
    "RECONNECT_BACKOFF_SECONDS",
    "SOFT_RESTART_REPROBE_SECONDS",
    "START_MEDIA_COMMAND_ID",
    "STOP_MEDIA_COMMAND_ID",
    "VALID_RAW_QUALITIES",
    "VIDEO_STALL_DEADLINE_SECONDS",
]
