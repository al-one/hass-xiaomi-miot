"""Tests for RTP packetization, RTCP sender reports, and SDP."""

from __future__ import annotations

import base64
import struct

import pytest

from custom_components.xiaomi_miot.core.xiaomi_p2p import MediaContract
from custom_components.xiaomi_miot.core.xiaomi_p2p.rtp import (
    MAX_RTP_DATAGRAM_SIZE,
    RtcpSender,
    RtpPacket,
    RtpPacketizer,
    RtpTrack,
    build_sdp,
    packetize_video,
    payload_mapping,
)


def make_contract(
    *,
    video_codec=4,
    audio_codec=1027,
    sample_rate=8000,
    channels=1,
):
    return MediaContract(
        video_codec=video_codec,
        audio_codec=audio_codec,
        video_sps=b"\x67sps",
        video_pps=b"\x68pps",
        vps=b"\x40\x01vps" if video_codec == 5 else None,
        width=1280,
        height=720,
        fps=30,
        sample_rate=sample_rate,
        channels=channels,
    )


def test_rtp_packet_serializes_standard_header():
    packet = RtpPacket(
        payload=b"abc",
        marker=True,
        sequence=0x1234,
        timestamp=0x01020304,
        ssrc=0x11223344,
        payload_type=96,
    )

    wire = packet.to_bytes()

    assert wire[:2] == bytes([0x80, 0xE0])
    assert struct.unpack(">HII", wire[2:12]) == (
        0x1234,
        0x01020304,
        0x11223344,
    )
    assert wire[12:] == b"abc"


@pytest.mark.parametrize("codec", [4, 5])
def test_video_packets_never_exceed_1200_bytes(codec):
    header = b"\x65" if codec == 4 else b"\x26\x01"
    packets = packetize_video(
        codec,
        b"\x00\x00\x00\x01" + header + b"x" * 5000,
    )

    assert packets
    assert max(len(packet.to_bytes()) for packet in packets) <= 1200
    assert packets[-1].marker is True
    assert all(packet.marker is False for packet in packets[:-1])


def test_h264_single_nal_and_fu_a_headers():
    packetizer = RtpPacketizer(video_ssrc=1, audio_ssrc=2)
    single = packetizer.packetize_video(
        4,
        b"\x00\x00\x00\x01\x65small",
        pts=0,
    )
    fragmented = packetizer.packetize_video(
        4,
        b"\x00\x00\x00\x01\x65" + b"x" * 3000,
        pts=32000,
    )

    assert single[0].payload == b"\x65small"
    assert single[0].marker is True
    assert fragmented[0].payload[0] & 0x1F == 28
    assert fragmented[0].payload[1] & 0x80
    assert fragmented[-1].payload[1] & 0x40
    assert fragmented[-1].timestamp - single[0].timestamp == 90000


def test_h264_fragmentation_preserves_forbidden_and_nri_bits():
    packets = RtpPacketizer(video_ssrc=1, audio_ssrc=2).packetize_video(
        4,
        b"\x00\x00\x00\x01\x41" + b"x" * 3000,
        pts=0,
    )

    assert packets[0].payload[0] & 0xE0 == 0x40


def test_h265_fragmentation_uses_fu_type_49():
    packets = RtpPacketizer(video_ssrc=1, audio_ssrc=2).packetize_video(
        5,
        b"\x00\x00\x00\x01\x26\x01" + b"x" * 3000,
        pts=0,
    )

    assert (packets[0].payload[0] >> 1) & 0x3F == 49
    assert packets[0].payload[2] & 0x80
    assert packets[-1].payload[2] & 0x40


def test_sequence_wrap_and_independent_ssrcs():
    packetizer = RtpPacketizer(
        video_ssrc=0x11111111,
        audio_ssrc=0x22222222,
        video_sequence=0xFFFF,
        audio_sequence=7,
    )

    first = packetizer.packetize_video(4, b"\x00\x00\x00\x01\x65a", pts=0)
    second = packetizer.packetize_video(4, b"\x00\x00\x00\x01\x61b", pts=1)
    audio = packetizer.packetize_audio(
        1027,
        b"audio",
        pts=0,
        sample_rate=8000,
    )

    assert first[0].sequence == 0xFFFF
    assert second[0].sequence == 0
    assert first[0].ssrc == 0x11111111
    assert audio.ssrc == 0x22222222
    assert audio.sequence == 7


def test_pcma_and_opus_payload_mapping():
    assert payload_mapping(1027, 8000) == (8, "PCMA/8000/1")
    assert payload_mapping(1027, 16000) == (97, "PCMA/16000/1")
    assert payload_mapping(1032, 48000) == (111, "opus/48000/2")


def test_common_media_origin_scales_track_timestamps():
    packetizer = RtpPacketizer(
        video_ssrc=1,
        audio_ssrc=2,
        video_timestamp=100,
        audio_timestamp=200,
    )

    video = packetizer.packetize_video(
        4,
        b"\x00\x00\x00\x01\x65a",
        pts=32000,
    )[0]
    audio = packetizer.packetize_audio(
        1027,
        b"a",
        pts=32000,
        sample_rate=8000,
    )
    later_video = packetizer.packetize_video(
        4,
        b"\x00\x00\x00\x01\x61b",
        pts=64000,
    )[0]
    later_audio = packetizer.packetize_audio(
        1027,
        b"b",
        pts=64000,
        sample_rate=8000,
    )

    assert video.timestamp == 100
    assert audio.timestamp == 200
    assert later_video.timestamp == 90100
    assert later_audio.timestamp == 8200


def test_rtcp_compound_report_first_then_every_five_seconds():
    track = RtpTrack(
        payload_type=96,
        clock_rate=90000,
        ssrc=0x11223344,
        sequence=0,
        timestamp_base=0,
    )
    track.record_packet(payload_octets=100, timestamp=9000)
    sender = RtcpSender(cname="camera")

    first = sender.maybe_report(track, now=10.0, ntp_seconds=1000.25)
    early = sender.maybe_report(track, now=14.9, ntp_seconds=1005.0)
    second = sender.maybe_report(track, now=15.0, ntp_seconds=1005.25)

    assert first is not None
    assert first[1] == 200
    assert first[28 + 1] == 202
    assert struct.unpack(">I", first[20:24])[0] == 1
    assert struct.unpack(">I", first[24:28])[0] == 100
    assert early is None
    assert second is not None


def test_rtcp_first_report_is_scheduled_independently_per_track():
    sender = RtcpSender(cname="camera")
    video = RtpTrack(96, 90000, 1)
    audio = RtpTrack(8, 8000, 2)
    video.record_packet(payload_octets=1, timestamp=9000, emitted_at=10.0)
    audio.record_packet(payload_octets=1, timestamp=800, emitted_at=10.0)

    assert sender.maybe_report(video, now=10.0, ntp_seconds=1000.0) is not None
    assert sender.maybe_report(audio, now=10.0, ntp_seconds=1000.0) is not None


def test_rtcp_waits_for_first_rtp_packet():
    sender = RtcpSender(cname="camera")
    track = RtpTrack(96, 90000, 1)

    assert sender.maybe_report(track, now=10.0, ntp_seconds=1000.0) is None


def test_rtcp_timestamp_matches_ntp_sampling_instant():
    sender = RtcpSender(cname="camera")
    track = RtpTrack(96, 90000, 1)
    track.record_packet(payload_octets=1, timestamp=9000, emitted_at=10.0)

    report = sender.maybe_report(track, now=10.25, ntp_seconds=1000.25)

    assert report is not None
    assert struct.unpack(">I", report[16:20])[0] == 31500


def test_rtcp_sender_report_wraps_32bit_fields():
    sender = RtcpSender(cname="camera")
    track = RtpTrack(96, 90000, 1, timestamp_base=0xFFFFFFF0)
    track.record_packet(
        payload_octets=0x1_0000_0001,
        timestamp=0x1_0000_0010,
        emitted_at=10.0,
        packet_count=0x1_0000_0002,
    )

    report = sender.maybe_report(track, now=10.0, ntp_seconds=1000.0)

    assert report is not None
    assert struct.unpack(">I", report[16:20])[0] == 0x10
    assert struct.unpack(">I", report[20:24])[0] == 2
    assert struct.unpack(">I", report[24:28])[0] == 1


@pytest.mark.parametrize(
    ("contract", "expected"),
    [
        (make_contract(video_codec=4), "a=rtpmap:96 H264/90000"),
        (make_contract(video_codec=5), "a=rtpmap:98 H265/90000"),
        (
            make_contract(audio_codec=1027, sample_rate=16000),
            "a=rtpmap:97 PCMA/16000/1",
        ),
        (
            make_contract(audio_codec=1032, sample_rate=48000, channels=2),
            "a=rtpmap:111 opus/48000/2",
        ),
    ],
)
def test_sdp_contains_exact_codec_attributes(contract, expected):
    parameters = {
        "vps": contract.vps,
        "sps": contract.video_sps,
        "pps": contract.video_pps,
    }
    sdp = build_sdp(
        contract,
        {"video": (5000, 5001), "audio": (5002, 5003)},
        parameters,
    )

    assert "c=IN IP4 127.0.0.1" in sdp
    assert "t=0 0" in sdp
    assert "a=rtcp:5001 IN IP4 127.0.0.1" in sdp
    assert expected in sdp
    assert "a=rtcp:5003 IN IP4 127.0.0.1" in sdp


def test_h264_and_h265_sdp_parameter_sets_are_base64():
    h264 = make_contract(video_codec=4, audio_codec=None, sample_rate=0, channels=0)
    h265 = make_contract(video_codec=5, audio_codec=None, sample_rate=0, channels=0)
    ports = {"video": (5000, 5001)}

    h264_sdp = build_sdp(
        h264,
        ports,
        {"sps": h264.video_sps, "pps": h264.video_pps},
    )
    h265_sdp = build_sdp(
        h265,
        ports,
        {"vps": h265.vps, "sps": h265.video_sps, "pps": h265.video_pps},
    )

    h264_parameters = ",".join(
        [
            base64.b64encode(h264.video_sps).decode(),
            base64.b64encode(h264.video_pps).decode(),
        ]
    )
    assert (
        "a=fmtp:96 packetization-mode=1;"
        f"sprop-parameter-sets={h264_parameters}"
    ) in h264_sdp
    assert (
        "a=fmtp:98 "
        f"sprop-vps={base64.b64encode(h265.vps).decode()};"
        f"sprop-sps={base64.b64encode(h265.video_sps).decode()};"
        f"sprop-pps={base64.b64encode(h265.video_pps).decode()}"
    ) in h265_sdp


def test_fragmented_video_counters_track_each_rtp_packet():
    packetizer = RtpPacketizer(video_ssrc=1, audio_ssrc=2)

    packets = packetizer.packetize_video(
        4,
        b"\x00\x00\x00\x01\x65" + b"x" * 3000,
        pts=0,
    )

    assert packetizer.video_track.packet_count == len(packets)
    assert packetizer.video_track.octet_count == sum(
        len(packet.payload) for packet in packets
    )


def test_audio_packet_rejects_datagrams_over_1200_bytes():
    packetizer = RtpPacketizer(video_ssrc=1, audio_ssrc=2)

    with pytest.raises(ValueError, match="audio payload exceeds RTP datagram limit"):
        packetizer.packetize_audio(
            1032,
            b"x" * (MAX_RTP_DATAGRAM_SIZE - 11),
            pts=0,
            sample_rate=48000,
        )


def test_audio_packet_counters_track_payload_octets():
    packetizer = RtpPacketizer(video_ssrc=1, audio_ssrc=2)

    packetizer.packetize_audio(1032, b"opus-data", pts=0, sample_rate=48000)

    assert packetizer.audio_track.packet_count == 1
    assert packetizer.audio_track.octet_count == len(b"opus-data")
    assert MAX_RTP_DATAGRAM_SIZE == 1200
