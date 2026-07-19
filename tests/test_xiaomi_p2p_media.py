"""Tests for MISS media parsing, contract probing, and timestamp normalization.

Covers Task 7: SPS/PPS and VPS/SPS/PPS discovery, complete keyframes,
parameter fingerprints, dimensions, PCMA 8/16 kHz flags, Opus 48000/2,
incompatible Opus video-only fallback, two-second audio wait, contract
equality fields, monotonic recovery after camera timestamp reset, and
bounded-track overflow.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from custom_components.xiaomi_miot.core.xiaomi_p2p import (
    MediaContract,
    NormalizedAudioFrame,
    NormalizedVideoFrame,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.protocol import (
    MediaHeader,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.media import (
    AUDIO_INCOMPATIBLE_FLAG,
    AccessUnitAssembler,
    MediaProbe,
    TimestampNormalizer,
    assemble_annex_b,
    decode_h264_dimensions,
    h264_nal_type,
    h265_nal_type,
)

from .helpers.xiaomi_p2p_clock import FakeClock


# ---- Synthetic H.264 SPS for 1280x720 -------------------------------------

# Hand-encoded Baseline SPS:
#   NAL header byte 0x67 (nal_unit_type=7, SPS)
#   profile_idc=66 (0x42 Baseline), constraint_set_flags=0xC0, level_idc=30 (0x1E)
#   seq_parameter_set_id=0, log2_max_frame_num_minus4=0, pic_order_cnt_type=0,
#   log2_max_pic_order_cnt_lsb_minus4=0, max_num_ref_frames=0,
#   gaps_in_frame_num_value_allowed_flag=0
#   pic_width_in_mbs_minus1=79 (ue=0000001010000),
#   pic_height_in_map_units_minus1=44 (ue=00000101101),
#   frame_mbs_only_flag=1, direct_8x8_inference_flag=0,
#   frame_cropping_flag=0, vui_parameters_present_flag=0.
H264_SPS_1280x720 = bytes(
    [
        0x67,        # NAL header: nal_unit_type=7 (SPS)
        0x42,        # profile_idc = 66 (Baseline)
        0xC0,        # constraint_set_flags
        0x1E,        # level_idc = 30
        0xF8, 0x0A, 0x00, 0xB6, 0x00,  # remaining fields, padded
    ]
)


# ---- Helpers --------------------------------------------------------------


def make_contract(
    *,
    video_codec: int = 4,
    width: int = 1920,
    height: int = 1080,
    audio_codec: int | None = 1027,
    fps: int = 30,
):
    if audio_codec == 1027:
        sample_rate = 8000
        channels = 1
    elif audio_codec == 1032:
        sample_rate = 48000
        channels = 2
    else:
        sample_rate = 0
        channels = 0
    return MediaContract(
        video_codec=video_codec,
        audio_codec=audio_codec,
        video_sps=b"sps-bytes",
        video_pps=b"pps-bytes",
        vps=None,
        width=width,
        height=height,
        fps=fps,
        sample_rate=sample_rate,
        channels=channels,
    )


def make_pcma_frame() -> bytes:
    # Synthetic PCMA payload.
    return b"\xD5\xD5\xD5\xD5"


def make_delta_fragment() -> bytes:
    # H.264 non-IDR slice (nal_unit_type = 1) so it does not constitute a keyframe.
    return b"\x00\x00\x00\x01\x01" + b"non-idr-slice"


# ---- Contract equality ---------------------------------------------------


def test_media_contract_equality_ignores_transport_and_timestamps():
    first = make_contract(video_codec=4, width=1920, height=1080, audio_codec=1027)
    same = replace(first)
    assert first == same
    assert hash(first) == hash(same)


def test_media_contract_distinguishes_codec_change():
    first = make_contract(video_codec=4)
    other = make_contract(video_codec=5)
    assert first != other


# ---- Stall clock / probe state -------------------------------------------


def test_stall_clock_advances_only_for_complete_video():
    clock = FakeClock()
    probe = MediaProbe(clock=clock)
    probe.publish_complete_keyframe(clock.now)
    initial = probe.last_complete_video_at
    probe.accept_audio(make_pcma_frame())
    probe.accept_incomplete_video(make_delta_fragment())
    assert probe.last_complete_video_at == initial


def test_accept_complete_video_advances_clock():
    clock = FakeClock()
    probe = MediaProbe(clock=clock)
    probe.publish_complete_keyframe(clock.now)
    clock.advance(0.5)
    probe.accept_complete_video(b"\x00\x00\x00\x01\x65" + b"idr-slice", clock.now)
    assert probe.last_complete_video_at == clock.now


# ---- AccessUnitAssembler: SPS/PPS and VPS/SPS/PPS discovery -------------


def _h264_sps_nal(body: bytes = b"") -> bytes:
    return bytes([0x67]) + body  # nal_unit_type = 7 (SPS)


def _h264_pps_nal(body: bytes = b"") -> bytes:
    return bytes([0x68]) + body  # nal_unit_type = 8 (PPS)


def _h264_idr_nal(body: bytes = b"") -> bytes:
    return bytes([0x65]) + body  # nal_unit_type = 5 (IDR)


def _h265_vps_nal(body: bytes = b"") -> bytes:
    return bytes([0x40, 0x01]) + body  # nal_unit_type = 32 (VPS)


def _h265_sps_nal(body: bytes = b"") -> bytes:
    return bytes([0x42, 0x01]) + body  # nal_unit_type = 33 (SPS)


def _h265_pps_nal(body: bytes = b"") -> bytes:
    return bytes([0x44, 0x01]) + body  # nal_unit_type = 34 (PPS)


def _h265_idr_nal(body: bytes = b"") -> bytes:
    return bytes([0x26, 0x01]) + body  # nal_unit_type = 19 (IDR_W_RADL)


def test_access_unit_assembler_detects_h264_sps_and_pps():
    sps = _h264_sps_nal(b"sps-data")
    pps = _h264_pps_nal(b"pps-data")
    body = assemble_annex_b([sps, pps])
    assembler = AccessUnitAssembler()
    nals = list(assembler.feed(body))
    assert len(nals) == 2
    assert assembler.sps == sps
    assert assembler.pps == pps
    assert assembler.vps is None


def test_access_unit_assembler_detects_h265_vps_sps_pps():
    vps = _h265_vps_nal(b"vps-data")
    sps = _h265_sps_nal(b"sps-data")
    pps = _h265_pps_nal(b"pps-data")
    body = assemble_annex_b([vps, sps, pps])
    assembler = AccessUnitAssembler()
    list(assembler.feed(body))
    assert assembler.vps == vps
    assert assembler.sps == sps
    assert assembler.pps == pps


def test_access_unit_assembler_returns_complete_h264_keyframe():
    sps = _h264_sps_nal(b"sps")
    pps = _h264_pps_nal(b"pps")
    idr = _h264_idr_nal(b"idr-slice")
    body = assemble_annex_b([sps, pps, idr])
    assembler = AccessUnitAssembler()
    list(assembler.feed(body))
    assert assembler.has_complete_h264_keyframe() is True


def test_access_unit_assembler_incomplete_without_idr():
    sps = _h264_sps_nal(b"sps")
    pps = _h264_pps_nal(b"pps")
    body = assemble_annex_b([sps, pps])
    assembler = AccessUnitAssembler()
    list(assembler.feed(body))
    assert assembler.has_complete_h264_keyframe() is False


def test_parameter_set_fingerprints_match_sha256():
    sps = _h264_sps_nal(b"sps-payload")
    pps = _h264_pps_nal(b"pps-payload")
    body = assemble_annex_b([sps, pps])
    assembler = AccessUnitAssembler()
    list(assembler.feed(body))
    assert assembler.sps_fingerprint == hashlib.sha256(b"sps-payload").digest()
    assert assembler.pps_fingerprint == hashlib.sha256(b"pps-payload").digest()


# ---- Dimensions -----------------------------------------------------------


def test_h264_sps_decodes_1280x720():
    width, height = decode_h264_dimensions(H264_SPS_1280x720)
    assert width == 1280
    assert height == 720


# ---- Audio: PCMA and Opus -----------------------------------------------




def test_probe_emits_normalized_keyframe_and_delta_video():
    clock = FakeClock()
    probe = MediaProbe(clock=clock)
    keyframe_body = assemble_annex_b([
        _h264_sps_nal(b"sps"),
        _h264_pps_nal(b"pps"),
        b"\x65idr",
    ])

    keyframes = probe.feed(
        MediaHeader(codec_id=4, sequence=0, flags=0, timestamp=32000),
        keyframe_body,
    )
    delta = probe.feed(
        MediaHeader(codec_id=4, sequence=1, flags=0, timestamp=33600),
        make_delta_fragment(),
    )

    assert keyframes == [
        NormalizedVideoFrame(
            data=keyframe_body,
            pts=32000,
            dts=32000,
            keyframe=True,
        )
    ]
    assert delta == [
        NormalizedVideoFrame(
            data=make_delta_fragment(),
            pts=33600,
            dts=33600,
            keyframe=False,
        )
    ]


def test_probe_emits_normalized_audio_frame():
    probe = MediaProbe(clock=FakeClock())
    frame = make_pcma_frame()

    emitted = probe.feed(
        MediaHeader(codec_id=1027, sequence=0, flags=0, timestamp=32000),
        frame,
    )

    assert emitted == [
        NormalizedAudioFrame(
            data=frame,
            pts=32000,
            sample_rate=8000,
            channels=1,
        )
    ]


def test_pcma_sample_rate_8khz_when_flag_unset():
    clock = FakeClock()
    probe = MediaProbe(clock=clock)
    probe.publish_complete_keyframe(clock.now)
    header = MediaHeader(codec_id=1027, sequence=0, flags=0, timestamp=0)
    probe.feed(header, make_pcma_frame())
    assert probe.audio_codec == 1027
    assert probe.audio_sample_rate == 8000
    assert probe.audio_channels == 1


def test_pcma_sample_rate_16khz_when_flag_set():
    clock = FakeClock()
    probe = MediaProbe(clock=clock)
    probe.publish_complete_keyframe(clock.now)
    header = MediaHeader(codec_id=1027, sequence=0, flags=0x1, timestamp=0)
    probe.feed(header, make_pcma_frame())
    assert probe.audio_sample_rate == 16000


def test_opus_is_48000_stereo():
    clock = FakeClock()
    probe = MediaProbe(clock=clock)
    probe.publish_complete_keyframe(clock.now)
    header = MediaHeader(codec_id=1032, sequence=0, flags=0, timestamp=0)
    probe.feed(header, b"\xfc\xde\x01\x02")
    assert probe.audio_codec == 1032
    assert probe.audio_sample_rate == 48000
    assert probe.audio_channels == 2


def test_incompatible_opus_falls_back_to_video_only():
    clock = FakeClock()
    probe = MediaProbe(clock=clock)
    probe.publish_complete_keyframe(clock.now)
    # Mark Opus as incompatible via the audio-incompatible flag.
    header = MediaHeader(
        codec_id=1032, sequence=0, flags=AUDIO_INCOMPATIBLE_FLAG, timestamp=0
    )
    probe.feed(header, b"\xfc\xde\x01\x02")
    assert probe.audio_codec is None
    assert probe.video_only is True


# ---- Two-second audio wait ----------------------------------------------


def test_two_second_audio_wait_returns_video_only_when_no_audio():
    clock = FakeClock()
    probe = MediaProbe(clock=clock, audio_wait_seconds=2.0)
    probe.publish_complete_keyframe(clock.now)
    # No audio arrives; advance past the wait deadline.
    clock.advance(2.5)
    assert probe.contract is not None
    assert probe.contract.audio_codec is None
    assert probe.video_only is True


def test_audio_arriving_within_wait_is_recorded():
    clock = FakeClock()
    probe = MediaProbe(clock=clock, audio_wait_seconds=2.0)
    probe.publish_complete_keyframe(clock.now)
    clock.advance(0.5)
    header = MediaHeader(codec_id=1027, sequence=0, flags=0, timestamp=0)
    probe.feed(header, make_pcma_frame())
    assert probe.contract is not None
    assert probe.contract.audio_codec == 1027


# ---- Timestamp normalization ---------------------------------------------


def test_timestamp_normalizer_handles_camera_reset():
    normalizer = TimestampNormalizer()
    assert normalizer.normalize(1000) == 1000
    assert normalizer.normalize(2000) == 2000
    # Camera resets to a small timestamp; output stays monotonic.
    after_reset = normalizer.normalize(100)
    assert after_reset > 2000


def test_timestamp_normalizer_first_emit_is_passed_through():
    normalizer = TimestampNormalizer()
    assert normalizer.normalize(42) == 42


def test_timestamp_normalizer_handles_steady_increase():
    normalizer = TimestampNormalizer()
    assert normalizer.normalize(100) == 100
    assert normalizer.normalize(150) == 150
    assert normalizer.normalize(200) == 200


# ---- Bounded overflow ----------------------------------------------------


def test_assembler_rejects_input_exceeding_byte_limit():
    assembler = AccessUnitAssembler(limit=128)
    # Use bytes that won't form Annex-B start codes; the input grows the buffer.
    big = b"\x42" * 200
    with pytest.raises(Exception):
        list(assembler.feed(big))


# ---- NAL type extraction helpers ---------------------------------------


def test_h264_nal_type_extracts_low_5_bits():
    assert h264_nal_type(bytes([0x67])) == 7  # SPS
    assert h264_nal_type(bytes([0x68])) == 8  # PPS
    assert h264_nal_type(bytes([0x65])) == 5  # IDR


def test_h265_nal_type_extracts_from_first_two_bytes():
    assert h265_nal_type(bytes([0x40, 0x01])) == 32  # VPS
    assert h265_nal_type(bytes([0x42, 0x01])) == 33  # SPS
    assert h265_nal_type(bytes([0x44, 0x01])) == 34  # PPS
    assert h265_nal_type(bytes([0x26, 0x01])) == 19  # IDR_W_RADL
