"""Public immutable types, enums, errors, profiles, and factories for MISS+CS2.

All public dataclasses here are frozen and slotted. Sensitive bootstrap
material is excluded from `repr` via `field(repr=False)` so accidental
logging never exposes keys, signatures, or tokens. Errors carry only a
non-sensitive category and caller-supplied detail; the framework never
embeds DIDs, hosts, ports, tokens, or payload data into exception text.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Final, Literal


class MissErrorCategory(str, enum.Enum):
    """Categorical failure type for MISS operations.

    Exceptions MUST carry one of these values plus caller-supplied,
    already-sanitized detail. They MUST NOT carry raw payloads, keys,
    signatures, hosts, ports, tokens, or device identifiers.
    """

    CLOUD = "cloud"
    TRANSPORT = "transport"
    AUTH = "auth"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    MEDIA = "media"


@dataclass(frozen=True, slots=True)
class MissError(Exception):
    """MISS layer error.

    The error message contains only the category value and a non-sensitive
    detail string supplied explicitly by the caller. Bootstrap material,
    keys, signatures, raw payloads, hosts, ports, tokens, and device
    identifiers MUST NOT appear in `str(self)`.
    """

    category: MissErrorCategory
    detail: str = ""

    def __str__(self) -> str:
        if not self.detail:
            return f"miss[{self.category.value}]"
        return f"miss[{self.category.value}]: {self.detail}"


@dataclass(frozen=True, slots=True)
class MissBootstrap:
    """Setup-time MISS bootstrap material.

    Secret fields are excluded from `repr` to prevent accidental
    disclosure via logs, diagnostics, or exception rendering. The
    dataclass is frozen so callers cannot mutate fields after creation.
    """

    host: str
    p2p_id: str | None
    client_private_key: bytes = field(repr=False)
    client_public_key: bytes = field(repr=False)
    device_public_key: bytes = field(repr=False)
    signature: str = field(repr=False)
    vendor: int


TransportMode = Literal["auto", "prefer_udp", "prefer_tcp"]


@dataclass(frozen=True, slots=True)
class P2PProfile:
    """Per-model negotiation defaults for MISS streaming.

    `transport` is the policy used at the CS2 connector layer. `auto`
    means the connector may pick either transport after a single
    discovery exchange; `prefer_udp` and `prefer_tcp` bias that choice
    without forcing a transport.
    """

    lenses: tuple[str, ...]
    transport: TransportMode
    raw_quality: int
    request_audio: bool
    required_video_codec: int | None
    required_audio_codec: int | None


@dataclass(frozen=True, slots=True)
class MediaContract:
    """Negotiated media parameters for an active MISS session.

    Carries the codec and timing parameters required for FFmpeg and
    downstream RTP packetization. Values are negotiated once at session
    start and MUST be treated as immutable for the lifetime of the
    session.
    """

    video_codec: int
    audio_codec: int | None
    video_sps: bytes
    video_pps: bytes
    vps: bytes | None
    width: int
    height: int
    fps: int
    sample_rate: int
    channels: int


@dataclass(frozen=True, slots=True)
class NormalizedVideoFrame:
    """A single normalized video access unit.

    `data` is the full Annex-B formatted access unit starting with a
    start code. `pts` and `dts` are 32 kHz clock ticks aligned to the
    media contract's `fps`. `keyframe` is True for IDR/payload type
    carrying parameter sets.
    """

    data: bytes
    pts: int
    dts: int
    keyframe: bool


@dataclass(frozen=True, slots=True)
class NormalizedAudioFrame:
    """A single normalized audio access unit.

    `data` is a single audio frame at `sample_rate` Hz with `channels`
    channels. `pts` is the 32 kHz clock tick matching the video stream.
    """

    data: bytes
    pts: int
    sample_rate: int
    channels: int


@dataclass(frozen=True, slots=True)
class SessionKey:
    """Opaque reference to an active MISS session.

    Wraps a token that downstream layers (MediaBridge, MediaServer) use
    to address the owning session without exposing internal state.
    """

    token: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Process-local snapshot of an active session for diagnostics.

    Intentionally carries only non-sensitive scalars (counts, lifetimes,
    transport mode). MUST NOT include keys, signatures, hosts, ports,
    tokens, route URLs, or payload data.
    """

    did_hash: int
    transport: TransportMode
    frames_emitted: int
    audio_frames_emitted: int
    retries: int
    started_at: float
    last_frame_at: float


DEFAULT_P2P_PROFILE: Final[P2PProfile] = P2PProfile(
    lenses=("primary",),
    transport="auto",
    raw_quality=0,
    request_audio=True,
    required_video_codec=None,
    required_audio_codec=None,
)


P2P_PROFILES: Final[dict[str, P2PProfile]] = {
    "isa.camera.hlc7": P2PProfile(
        lenses=("primary",),
        transport="prefer_udp",
        raw_quality=2,
        request_audio=True,
        required_video_codec=5,
        required_audio_codec=1027,
    ),
    "chuangmi.camera.039c01": P2PProfile(
        lenses=("primary",),
        transport="prefer_tcp",
        raw_quality=2,
        request_audio=True,
        required_video_codec=5,
        required_audio_codec=1032,
    ),
    "mxiang.camera.c500ch": P2PProfile(
        lenses=("primary", "secondary"),
        transport="auto",
        raw_quality=0,
        request_audio=True,
        required_video_codec=None,
        required_audio_codec=None,
    ),
}


__all__ = [
    "DEFAULT_P2P_PROFILE",
    "MediaContract",
    "MissBootstrap",
    "MissError",
    "MissErrorCategory",
    "NormalizedAudioFrame",
    "NormalizedVideoFrame",
    "P2P_PROFILES",
    "P2PProfile",
    "SessionKey",
    "SessionSnapshot",
    "TransportMode",
]