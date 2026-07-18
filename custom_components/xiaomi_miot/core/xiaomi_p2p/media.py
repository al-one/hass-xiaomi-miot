"""MISS media parsing, contract probing, and timestamp normalization.

The MISS media stream arrives as a sequence of `Cs2MediaPacket`s
containing a plaintext 32-byte header followed by an encrypted body.
This module:

  * parses Annex-B NAL units for H.264 / H.265 with bounded memory,
  * discovers SPS / PPS (and VPS for H.265),
  * detects complete keyframes (parameter sets + IDR slice),
  * emits immutable `MediaContract`s once the probe is complete,
  * normalizes camera timestamps strictly monotonically.

The session feeds decrypted media bodies to this module; the session
itself owns MISS decryption. Parameter-set bytes and fingerprints
remain private runtime data and are NEVER exposed through diagnostics
or entity state.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterator, Optional

from . import MediaContract, MissError, MissErrorCategory


# ---- Constants -----------------------------------------------------------

# H.264 / H.265 NAL unit types that matter for parameter-set detection
# and keyframe identification.
H264_NAL_SLICE = 1
H264_NAL_IDR = 5
H264_NAL_SEI = 6
H264_NAL_SPS = 7
H264_NAL_PPS = 8

H265_NAL_VPS = 32
H265_NAL_SPS = 33
H265_NAL_PPS = 34
H265_NAL_IDR_W_RADL = 19
H265_NAL_IDR_N_LP = 20
H265_NAL_IDR = (H265_NAL_IDR_W_RADL, H265_NAL_IDR_N_LP)

# MISS media-header flags. Bit 0 selects PCMA sample rate (0 = 8 kHz,
# 1 = 16 kHz). Bit 2 marks an audio codec as incompatible with the
# reference profile (probe falls back to video-only).
PCMA_16KHZ_FLAG = 0x1
AUDIO_INCOMPATIBLE_FLAG = 0x4

# Codec IDs declared by the MISS protocol.
CODEC_H264 = 4
CODEC_H265 = 5
CODEC_PCMA = 1027
CODEC_OPUS = 1032

# Default bound for incomplete per-track assembly buffer.
DEFAULT_TRACK_BYTE_LIMIT = 8 * 1024 * 1024

# Default two-second audio wait.
DEFAULT_AUDIO_WAIT_SECONDS = 2.0


# ---- Helpers ------------------------------------------------------------


def h264_nal_type(nal: bytes) -> int:
    """Return the H.264 NAL unit type (low 5 bits of the first byte)."""

    if not nal:
        raise MissError(MissErrorCategory.MEDIA, "media_nal_invalid")
    return nal[0] & 0x1F


def h265_nal_type(nal: bytes) -> int:
    """Return the H.265 NAL unit type (bits 1-6 of the first byte)."""

    if len(nal) < 2:
        raise MissError(MissErrorCategory.MEDIA, "media_nal_invalid")
    return (nal[0] >> 1) & 0x3F


def assemble_annex_b(nal_units: list[bytes]) -> bytes:
    """Concatenate NAL units separated by 4-byte Annex-B start codes."""

    out = bytearray()
    for nal in nal_units:
        out.extend(b"\x00\x00\x00\x01")
        out.extend(nal)
    return bytes(out)


# ---- H.264 SPS dimension decoder ----------------------------------------


class _BitReader:
    """Read individual bits / exp-Golomb codes from a byte buffer."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._bit_pos = 0

    def read_bits(self, n: int) -> int:
        if n < 0:
            raise ValueError("read_bits requires non-negative count")
        value = 0
        for _ in range(n):
            byte_idx = self._bit_pos // 8
            bit_idx = 7 - (self._bit_pos % 8)
            if byte_idx >= len(self._data):
                raise MissError(MissErrorCategory.MEDIA, "sps_truncated")
            value = (value << 1) | ((self._data[byte_idx] >> bit_idx) & 1)
            self._bit_pos += 1
        return value

    def read_ue(self) -> int:
        """Unsigned exp-Golomb."""

        leading = 0
        while self.read_bits(1) == 0:
            leading += 1
        if leading == 0:
            return 0
        suffix = self.read_bits(leading)
        return (1 << leading) - 1 + suffix

    def read_se(self) -> int:
        """Signed exp-Golomb."""

        code = self.read_ue()
        if code & 1:
            return (code + 1) // 2
        return -(code // 2)


def decode_h264_dimensions(sps: bytes) -> tuple[int, int]:
    """Decode width / height from a Baseline / Main / High H.264 SPS.

    The parser handles the common subset (no scaling lists, no MBAFF)
    and returns the cropped picture dimensions in pixels. Raises
    `MissError(MEDIA)` on malformed input.
    """

    if len(sps) < 4:
        raise MissError(MissErrorCategory.MEDIA, "sps_truncated")
    # H.264 SPS NAL header is 1 byte; the Annex-B framing is not present
    # here because the assembler strips it.
    reader = _BitReader(sps[1:])
    profile_idc = reader.read_bits(8)
    reader.read_bits(16)  # constraint_set_flags + level_idc
    reader.read_ue()  # seq_parameter_set_id
    if profile_idc in (100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134):
        chroma_format_idc = reader.read_ue()
        if chroma_format_idc == 3:
            reader.read_bits(1)  # separate_colour_plane_flag
        reader.read_ue()  # bit_depth_luma_minus8
        reader.read_ue()  # bit_depth_chroma_minus8
        if reader.read_bits(1):  # qpprime_y_zero_transform_bypass_flag
            pass
        if reader.read_bits(1):  # seq_scaling_matrix_present_flag
            # Skip scaling lists (rare; skip conservatively by reading the
            # max possible count and stopping when bits run out).
            scaling_list_count = 12 if chroma_format_idc == 3 else 8
            for _ in range(scaling_list_count):
                if not reader.read_bits(1):
                    continue
                size = 16
                last = 8
                for _ in range(size):
                    if last != 128:
                        delta = reader.read_se()
                        last = (last + delta + 256) & 0xFF
    reader.read_ue()  # log2_max_frame_num_minus4
    pic_order_cnt_type = reader.read_ue()
    if pic_order_cnt_type == 0:
        reader.read_ue()  # log2_max_pic_order_cnt_lsb_minus4
    elif pic_order_cnt_type == 1:
        reader.read_bits(1)  # delta_pic_order_always_zero_flag
        reader.read_se()  # offset_for_non_ref_pic
        reader.read_se()  # offset_for_top_to_bottom_field
        num_ref_frames = reader.read_ue()
        for _ in range(num_ref_frames):
            reader.read_se()
    reader.read_ue()  # max_num_ref_frames
    reader.read_bits(1)  # gaps_in_frame_num_value_allowed_flag
    width_mbs_minus1 = reader.read_ue()
    height_map_units_minus1 = reader.read_ue()
    frame_mbs_only_flag = reader.read_bits(1)
    if not frame_mbs_only_flag:
        reader.read_bits(1)  # mb_adaptive_frame_field_flag
    reader.read_bits(1)  # direct_8x8_inference_flag
    crop_left = crop_right = crop_top = crop_bottom = 0
    if reader.read_bits(1):  # frame_cropping_flag
        crop_left = reader.read_ue()
        crop_right = reader.read_ue()
        crop_top = reader.read_ue()
        crop_bottom = reader.read_ue()

    width = (width_mbs_minus1 + 1) * 16 - 2 * (crop_left + crop_right)
    height_mbs = (height_map_units_minus1 + 1) * (1 if frame_mbs_only_flag else 2)
    height = height_mbs * 16 - 2 * (crop_top + crop_bottom)
    return width, height


# ---- AccessUnitAssembler ------------------------------------------------


class AccessUnitAssembler:
    """Bounded Annex-B NAL unit parser for H.264 / H.265.

    The assembler buffers incomplete NAL units across `feed()` calls
    and yields each complete NAL unit. The most recent parameter-set
    NAL units (H.264 SPS/PPS or H.265 VPS/SPS/PPS) are recorded so the
    probe can build the `MediaContract`. Memory is bounded by `limit`.
    """

    def __init__(self, *, limit: int = DEFAULT_TRACK_BYTE_LIMIT) -> None:
        self._limit = limit
        self._buffer = bytearray()
        self._sps: Optional[bytes] = None
        self._pps: Optional[bytes] = None
        self._vps: Optional[bytes] = None
        self._h264_idr_seen = False
        self._h265_idr_seen = False

    @property
    def sps(self) -> Optional[bytes]:
        return self._sps

    @property
    def pps(self) -> Optional[bytes]:
        return self._pps

    @property
    def vps(self) -> Optional[bytes]:
        return self._vps

    @property
    def sps_fingerprint(self) -> Optional[bytes]:
        if self._sps is None:
            return None
        return hashlib.sha256(self._strip_nal_header(self._sps)).digest()

    @property
    def pps_fingerprint(self) -> Optional[bytes]:
        if self._pps is None:
            return None
        return hashlib.sha256(self._strip_nal_header(self._pps)).digest()

    @property
    def vps_fingerprint(self) -> Optional[bytes]:
        if self._vps is None:
            return None
        return hashlib.sha256(self._strip_nal_header(self._vps)).digest()

    @staticmethod
    def _strip_nal_header(nal: bytes) -> bytes:
        # H.264 parameter sets use a 1-byte NAL header; H.265 uses 2 bytes.
        if not nal:
            return nal
        h264_type = nal[0] & 0x1F
        if h264_type in (H264_NAL_SPS, H264_NAL_PPS):
            return nal[1:]
        if len(nal) >= 2:
            h265_type = (nal[0] >> 1) & 0x3F
            if h265_type in (H265_NAL_VPS, H265_NAL_SPS, H265_NAL_PPS):
                return nal[2:]
        return nal

    def has_complete_h264_keyframe(self) -> bool:
        return (
            self._sps is not None
            and self._pps is not None
            and self._h264_idr_seen
        )

    def has_complete_h265_keyframe(self) -> bool:
        return (
            self._vps is not None
            and self._sps is not None
            and self._pps is not None
            and self._h265_idr_seen
        )

    def feed(self, body: bytes) -> Iterator[bytes]:
        if len(self._buffer) + len(body) > self._limit:
            raise MissError(MissErrorCategory.MEDIA, "track_overflow")
        self._buffer.extend(body)
        # Yield complete NAL units between Annex-B start codes. The final
        # NAL (without a following start code) is also yielded: the caller
        # owns media-packet boundaries and is responsible for knowing when
        # a NAL is complete.
        while True:
            start_idx = self._find_start_code(0)
            if start_idx < 0:
                if len(self._buffer) > 3:
                    del self._buffer[:-3]
                return
            start_code_len = 4 if self._buffer[start_idx:start_idx + 4] == b"\x00\x00\x00\x01" else 3
            nal_start = start_idx + start_code_len
            next_idx = self._find_start_code(nal_start)
            if next_idx < 0:
                buffered_nal = bytes(self._buffer[nal_start:])
                if buffered_nal:
                    self._absorb_parameter_set(buffered_nal)
                    yield buffered_nal
                self._buffer.clear()
                return
            nal = bytes(self._buffer[nal_start:next_idx])
            if nal:
                self._absorb_parameter_set(nal)
                yield nal
            del self._buffer[:next_idx]

    def _find_start_code(self, start: int) -> int:
        i = start
        buf = self._buffer
        while i + 3 <= len(buf):
            if buf[i] == 0 and buf[i + 1] == 0:
                if buf[i + 2] == 1:
                    return i
                if buf[i + 2] == 0 and i + 3 < len(buf) and buf[i + 3] == 1:
                    return i
            i += 1
        return -1

    def _absorb_parameter_set(self, nal: bytes) -> None:
        if not nal:
            return
        h264_type = nal[0] & 0x1F
        if h264_type == H264_NAL_SPS:
            self._sps = nal
            return
        if h264_type == H264_NAL_PPS:
            self._pps = nal
            return
        if h264_type == H264_NAL_IDR:
            self._h264_idr_seen = True
            return
        if len(nal) >= 2:
            h265_type = (nal[0] >> 1) & 0x3F
            if h265_type == H265_NAL_VPS:
                self._vps = nal
            elif h265_type == H265_NAL_SPS:
                self._sps = nal
            elif h265_type == H265_NAL_PPS:
                self._pps = nal
            elif h265_type in H265_NAL_IDR:
                self._h265_idr_seen = True


# ---- TimestampNormalizer -------------------------------------------------


class TimestampNormalizer:
    """Map camera timestamps to strictly monotonic output.

    The camera can reset its timestamp counter (e.g. on reboot or
    recovery). After a reset, the new value is mapped to
    `last_emit + 1` so downstream RTP timestamps stay monotonic.
    """

    def __init__(self) -> None:
        self._last_emit: Optional[int] = None

    def normalize(self, value: int) -> int:
        if self._last_emit is None or value > self._last_emit:
            self._last_emit = value
            return value
        # Reset or duplicate: shift forward to remain monotonic.
        self._last_emit = self._last_emit + 1
        return self._last_emit

    @property
    def last_emit(self) -> Optional[int]:
        return self._last_emit


# ---- MediaProbe ----------------------------------------------------------


@dataclass
class _AudioState:
    codec: int
    sample_rate: int
    channels: int


class MediaProbe:
    """Probe an in-flight MISS media stream for codec contract.

    The probe has two input modes:

    * Production: `feed(header, body)` for each decrypted media packet.
    * Test seam: `publish_complete_keyframe`, `accept_audio`,
      `accept_incomplete_video`, and `accept_complete_video` for
      deterministic state manipulation.

    A `MediaContract` becomes available on the `contract` property as
    soon as a complete keyframe (parameter sets + IDR for H.264/H.265)
    has been seen AND the optional two-second audio wait has either
    produced audio or elapsed. Audio that arrives after the wait or
    that is marked incompatible falls back to video-only.
    """

    def __init__(
        self,
        *,
        clock=None,
        audio_wait_seconds: float = DEFAULT_AUDIO_WAIT_SECONDS,
        track_byte_limit: int = DEFAULT_TRACK_BYTE_LIMIT,
    ) -> None:
        self._clock = clock
        self._audio_wait_seconds = audio_wait_seconds
        self._assembler = AccessUnitAssembler(limit=track_byte_limit)
        self._video_codec: Optional[int] = None
        self._width: Optional[int] = None
        self._height: Optional[int] = None
        self._audio: Optional[_AudioState] = None
        self._video_only = False
        self._audio_arrival_at: Optional[float] = None
        self._complete_video_at: Optional[float] = None
        self._contract: Optional[MediaContract] = None
        self._complete_seen = False
        self._normalizer = TimestampNormalizer()

    # ---- Public surface ------------------------------------------------

    @property
    def contract(self) -> Optional[MediaContract]:
        self._maybe_publish_contract()
        return self._contract

    @property
    def last_complete_video_at(self) -> Optional[float]:
        return self._complete_video_at

    @property
    def video_only(self) -> bool:
        self._maybe_publish_contract()
        return self._video_only

    @property
    def audio_codec(self) -> Optional[int]:
        return self._audio.codec if self._audio is not None else None

    @property
    def audio_sample_rate(self) -> Optional[int]:
        return self._audio.sample_rate if self._audio is not None else None

    @property
    def audio_channels(self) -> Optional[int]:
        return self._audio.channels if self._audio is not None else None

    # ---- Test seam ----------------------------------------------------

    def publish_complete_keyframe(self, at: float) -> None:
        """Mark a complete keyframe as observed at time `at`."""

        self._complete_seen = True
        self._complete_video_at = at
        if self._video_codec is None:
            # Default to H.264 when the seam is used without a prior feed.
            self._video_codec = CODEC_H264
        self._maybe_publish_contract()

    def accept_incomplete_video(self, frame: bytes) -> None:
        """Record an incomplete video NAL unit. Does not advance the clock."""

        # Intentionally does not touch self._complete_video_at.
        return None

    def accept_complete_video(self, frame: bytes, at: float) -> None:
        """Record a complete video frame at time `at`."""

        self._complete_seen = True
        self._complete_video_at = at
        if self._video_codec is None:
            self._video_codec = CODEC_H264
        self._maybe_publish_contract()

    def accept_audio(self, frame: bytes) -> None:
        """Record an audio frame using the probe's current codec expectation.

        Defaults to PCMA 8 kHz mono when no prior feed established audio
        codec; the explicit feed() path sets the real sample rate.
        """

        if self._audio is None:
            self._audio = _AudioState(codec=CODEC_PCMA, sample_rate=8000, channels=1)
            self._audio_arrival_at = self._clock.now if self._clock is not None else 0.0
        self._maybe_publish_contract()

    # ---- Production feed -----------------------------------------------

    def feed(self, header: MediaHeader, body: bytes) -> None:
        if header.codec_id in (CODEC_H264, CODEC_H265):
            self._video_codec = header.codec_id
            # Drain parameter sets / IDRs from the body so a complete
            # keyframe is recognized once all required NALs are seen.
            for nal in self._assembler.feed(body):
                if not nal:
                    continue
                nal_type_h264 = nal[0] & 0x1F
                if header.codec_id == CODEC_H264:
                    if self._assembler.has_complete_h264_keyframe() and self._complete_video_at is None:
                        ts = self._normalizer.normalize(header.timestamp)
                        self._complete_seen = True
                        self._complete_video_at = self._clock.now if self._clock is not None else float(ts)
                else:
                    if self._assembler.has_complete_h265_keyframe() and self._complete_video_at is None:
                        ts = self._normalizer.normalize(header.timestamp)
                        self._complete_seen = True
                        self._complete_video_at = self._clock.now if self._clock is not None else float(ts)
            # Decode dimensions once SPS is available.
            if self._width is None and self._assembler.sps is not None and header.codec_id == CODEC_H264:
                try:
                    w, h = decode_h264_dimensions(self._assembler.sps)
                except MissError:
                    pass
                else:
                    self._width, self._height = w, h
            self._maybe_publish_contract()
        elif header.codec_id in (CODEC_PCMA, CODEC_OPUS):
            if header.flags & AUDIO_INCOMPATIBLE_FLAG:
                self._video_only = True
                self._audio = None
            elif header.codec_id == CODEC_PCMA:
                sample_rate = 16000 if (header.flags & PCMA_16KHZ_FLAG) else 8000
                self._audio = _AudioState(codec=CODEC_PCMA, sample_rate=sample_rate, channels=1)
                if self._clock is not None:
                    self._audio_arrival_at = self._clock.now
            else:  # CODEC_OPUS
                self._audio = _AudioState(codec=CODEC_OPUS, sample_rate=48000, channels=2)
                if self._clock is not None:
                    self._audio_arrival_at = self._clock.now
            self._maybe_publish_contract()

    # ---- Internals -----------------------------------------------------

    def _maybe_publish_contract(self) -> None:
        if self._contract is not None:
            return
        if not self._complete_seen:
            return
        # Try to decode video dimensions from cached SPS when not yet known.
        if self._video_codec == CODEC_H264 and self._assembler.sps is not None:
            if self._width is None:
                try:
                    self._width, self._height = decode_h264_dimensions(self._assembler.sps)
                except MissError:
                    pass
        # Default to 1280x720 if no dimensions were decoded (e.g. test seam).
        width = self._width if self._width is not None else 1280
        height = self._height if self._height is not None else 720
        codec = self._video_codec if self._video_codec is not None else CODEC_H264

        # Audio wait gate: if audio hasn't arrived and the wait window
        # is not yet closed, defer the contract. Otherwise publish
        # video-only.
        audio = self._audio
        if audio is None and self._clock is not None and self._complete_video_at is not None:
            elapsed = self._clock.now - self._complete_video_at
            if elapsed < self._audio_wait_seconds:
                # Window still open — defer.
                return
            self._video_only = True

        self._contract = MediaContract(
            video_codec=codec,
            audio_codec=audio.codec if audio is not None else None,
            video_sps=self._assembler.sps if self._assembler.sps is not None else b"",
            video_pps=self._assembler.pps if self._assembler.pps is not None else b"",
            vps=self._assembler.vps,
            width=width,
            height=height,
            fps=30,
            sample_rate=audio.sample_rate if audio is not None else 0,
            channels=audio.channels if audio is not None else 0,
        )


__all__ = [
    "AUDIO_INCOMPATIBLE_FLAG",
    "AccessUnitAssembler",
    "CODEC_H264",
    "CODEC_H265",
    "CODEC_OPUS",
    "CODEC_PCMA",
    "DEFAULT_AUDIO_WAIT_SECONDS",
    "DEFAULT_TRACK_BYTE_LIMIT",
    "H264_NAL_IDR",
    "H264_NAL_PPS",
    "H264_NAL_SPS",
    "MediaProbe",
    "PCMA_16KHZ_FLAG",
    "TimestampNormalizer",
    "assemble_annex_b",
    "decode_h264_dimensions",
    "h264_nal_type",
    "h265_nal_type",
]
