"""RTP packetization, RTCP sender reports, and SDP for MISS+CS2.

This module owns the per-bridge RTP/RTCP byte stream. Each bridge gets
its own random SSRCs, independent RTP sequence spaces, and a shared
normalized media-time origin that is scaled into the appropriate clock
for each track. SDP carries the loopback endpoint and the per-track
codec parameters negotiated by the session layer.
"""

from __future__ import annotations

import base64
import secrets
import struct
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping

from . import MediaContract


MAX_RTP_DATAGRAM_SIZE: int = 1200

_VIDEO_PAYLOAD_TYPE: dict[int, int] = {4: 96, 5: 98}

_AUDIO_PAYLOAD_TYPE: dict[int, int] = {
    (1027, 8000): 8,
    (1027, 16000): 97,
    (1032, 48000): 111,
}

_AUDIO_RTPMAP: dict[tuple[int, int], str] = {
    (1027, 8000): "PCMA/8000/1",
    (1027, 16000): "PCMA/16000/1",
    (1032, 48000): "opus/48000/2",
}

_VIDEO_CLOCK_RATE: int = 90000


def payload_mapping(audio_codec: int, sample_rate: int) -> tuple[int, str]:
    """Return the (RTP payload type, a=rtpmap body) for an audio codec."""

    key = (audio_codec, sample_rate)
    if key not in _AUDIO_PAYLOAD_TYPE:
        raise ValueError(f"unsupported audio codec={audio_codec}@{sample_rate}")
    return _AUDIO_PAYLOAD_TYPE[key], _AUDIO_RTPMAP[key]


@dataclass(frozen=True, slots=True)
class RtpPacket:
    payload: bytes
    marker: bool
    sequence: int
    timestamp: int
    ssrc: int
    payload_type: int = field(repr=False)

    def to_bytes(self) -> bytes:
        byte0 = 0x80
        byte1 = (0x80 if self.marker else 0) | (self.payload_type & 0x7F)
        header = struct.pack(
            ">BBHII",
            byte0,
            byte1,
            self.sequence & 0xFFFF,
            self.timestamp & 0xFFFFFFFF,
            self.ssrc & 0xFFFFFFFF,
        )
        return header + self.payload


@dataclass
class RtpTrack:
    payload_type: int
    clock_rate: int
    ssrc: int
    sequence: int = 0
    timestamp_base: int = 0
    last_emitted_timestamp: int = 0
    last_emitted_wallclock: float | None = None
    packet_count: int = 0
    octet_count: int = 0

    def record_packet(
        self,
        *,
        payload_octets: int,
        timestamp: int,
        packet_count: int = 1,
        emitted_at: float | None = None,
    ) -> None:
        self.packet_count += packet_count
        self.octet_count += payload_octets
        self.last_emitted_timestamp = timestamp
        self.last_emitted_wallclock = emitted_at


class RtpPacketizer:
    """Per-bridge RTP packetizer with independent SSRCs and sequence spaces."""

    def __init__(
        self,
        *,
        video_ssrc: int,
        audio_ssrc: int,
        video_sequence: int = 0,
        audio_sequence: int = 0,
        video_timestamp: int = 0,
        audio_timestamp: int = 0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self.video_track = RtpTrack(
            payload_type=_VIDEO_PAYLOAD_TYPE[4],
            clock_rate=_VIDEO_CLOCK_RATE,
            ssrc=video_ssrc,
            sequence=video_sequence,
            timestamp_base=video_timestamp,
            last_emitted_timestamp=video_timestamp,
        )
        self.audio_track = RtpTrack(
            payload_type=payload_mapping(1027, 8000)[0],
            clock_rate=8000,
            ssrc=audio_ssrc,
            sequence=audio_sequence,
            timestamp_base=audio_timestamp,
            last_emitted_timestamp=audio_timestamp,
        )
        self._media_pts_origin: int | None = None

    @property
    def video_ssrc(self) -> int:
        return self.video_track.ssrc

    @property
    def audio_ssrc(self) -> int:
        return self.audio_track.ssrc

    @property
    def video_sequence(self) -> int:
        return self.video_track.sequence

    @property
    def audio_sequence(self) -> int:
        return self.audio_track.sequence

    @property
    def video_timestamp(self) -> int:
        return self.video_track.last_emitted_timestamp

    @property
    def audio_timestamp(self) -> int:
        return self.audio_track.last_emitted_timestamp

    def packetize_video(
        self,
        codec_id: int,
        access_unit: bytes,
        pts: int,
    ) -> list[RtpPacket]:
        if codec_id not in _VIDEO_PAYLOAD_TYPE:
            raise ValueError(f"unsupported video codec {codec_id}")
        payload_type = _VIDEO_PAYLOAD_TYPE[codec_id]
        clock_timestamp = self._timestamp_for(self.video_track, pts)
        nal_units = split_annex_b(access_unit)
        if not nal_units:
            return []
        if codec_id == 4:
            packets = self._packetize_h264(nal_units, clock_timestamp, payload_type)
        else:
            packets = self._packetize_h265(nal_units, clock_timestamp, payload_type)
        if packets:
            self.video_track.record_packet(
                payload_octets=sum(len(p.payload) for p in packets),
                timestamp=clock_timestamp,
                packet_count=len(packets),
                emitted_at=self._clock(),
            )
        return packets

    def _packetize_h264(
        self,
        nal_units: list[bytes],
        timestamp: int,
        payload_type: int,
    ) -> list[RtpPacket]:
        packets: list[RtpPacket] = []
        single_unit_budget = MAX_RTP_DATAGRAM_SIZE - 12
        marker_on_last = False
        for nal in nal_units:
            if len(nal) <= single_unit_budget:
                packets.append(
                    self._make_packet(
                        nal,
                        timestamp=timestamp,
                        payload_type=payload_type,
                        marker=marker_on_last and nal == nal_units[-1],
                    )
                )
                continue
            packets.extend(
                self._fragment_h264(nal, timestamp, payload_type)
            )
        if packets:
            packets[-1] = replace_marker(packets[-1], marker=True)
        return packets

    def _packetize_h265(
        self,
        nal_units: list[bytes],
        timestamp: int,
        payload_type: int,
    ) -> list[RtpPacket]:
        packets: list[RtpPacket] = []
        single_unit_budget = MAX_RTP_DATAGRAM_SIZE - 12
        marker_on_last = False
        for nal in nal_units:
            header_len = 2 if len(nal) >= 2 else len(nal)
            body_len = len(nal) - header_len
            if len(nal) <= single_unit_budget:
                packets.append(
                    self._make_packet(
                        nal,
                        timestamp=timestamp,
                        payload_type=payload_type,
                        marker=marker_on_last and nal == nal_units[-1],
                    )
                )
                continue
            packets.extend(
                self._fragment_h265(nal, timestamp, payload_type)
            )
        if packets:
            packets[-1] = replace_marker(packets[-1], marker=True)
        return packets

    def _fragment_h264(
        self,
        nal: bytes,
        timestamp: int,
        payload_type: int,
    ) -> list[RtpPacket]:
        nal_type = nal[0] & 0x1F
        indicator = bytes([(nal[0] & 0xE0) | 28])
        body_budget = MAX_RTP_DATAGRAM_SIZE - 12 - 2
        fragments: list[RtpPacket] = []
        offset = 1
        first = True
        while offset < len(nal):
            chunk = nal[offset : offset + body_budget]
            fu_header = bytes([(nal_type & 0x1F) | (0x80 if first else 0)])
            if offset + body_budget >= len(nal):
                fu_header = bytes([(nal_type & 0x1F) | 0x40])
            fragments.append(
                self._make_packet(
                    indicator + fu_header + chunk,
                    timestamp=timestamp,
                    payload_type=payload_type,
                    marker=False,
                )
            )
            offset += body_budget
            first = False
        return fragments

    def _fragment_h265(
        self,
        nal: bytes,
        timestamp: int,
        payload_type: int,
    ) -> list[RtpPacket]:
        nal_type = (nal[0] >> 1) & 0x3F
        indicator = bytes([(nal[0] & 0x81) | (49 << 1), nal[1]])
        body_budget = MAX_RTP_DATAGRAM_SIZE - 12 - 3
        fragments: list[RtpPacket] = []
        offset = 2
        first = True
        while offset < len(nal):
            chunk = nal[offset : offset + body_budget]
            fu_header = bytes(
                [(nal_type & 0x3F) | (0x80 if first else 0)]
            )
            if offset + body_budget >= len(nal):
                fu_header = bytes([(nal_type & 0x3F) | 0x40])
            fragments.append(
                self._make_packet(
                    indicator + fu_header + chunk,
                    timestamp=timestamp,
                    payload_type=payload_type,
                    marker=False,
                )
            )
            offset += body_budget
            first = False
        return fragments

    def _make_packet(
        self,
        payload: bytes,
        *,
        timestamp: int,
        payload_type: int,
        marker: bool,
    ) -> RtpPacket:
        seq = self.video_track.sequence
        self.video_track.sequence = (seq + 1) & 0xFFFF
        return RtpPacket(
            payload=payload,
            marker=marker,
            sequence=seq,
            timestamp=timestamp,
            ssrc=self.video_track.ssrc,
            payload_type=payload_type,
        )

    def _timestamp_for(self, track: RtpTrack, pts: int) -> int:
        if self._media_pts_origin is None:
            self._media_pts_origin = pts
        elapsed = pts - self._media_pts_origin
        return track.timestamp_base + int(elapsed * track.clock_rate / 32000)

    def packetize_audio(
        self,
        audio_codec: int,
        body: bytes,
        *,
        pts: int,
        sample_rate: int,
    ) -> RtpPacket:
        payload_type, _ = payload_mapping(audio_codec, sample_rate)
        if len(body) + 12 > MAX_RTP_DATAGRAM_SIZE:
            raise ValueError("audio payload exceeds RTP datagram limit")
        self.audio_track.clock_rate = sample_rate
        clock_timestamp = self._timestamp_for(self.audio_track, pts)
        packet = RtpPacket(
            payload=body,
            marker=False,
            sequence=self.audio_track.sequence,
            timestamp=clock_timestamp,
            ssrc=self.audio_track.ssrc,
            payload_type=payload_type,
        )
        self.audio_track.sequence = (self.audio_track.sequence + 1) & 0xFFFF
        self.audio_track.payload_type = payload_type
        self.audio_track.record_packet(
            payload_octets=len(body),
            timestamp=clock_timestamp,
            emitted_at=self._clock(),
        )
        return packet


class RtcpSender:
    """Per-bridge RTCP sender report scheduler."""

    def __init__(self, *, cname: str) -> None:
        self._cname = cname
        self._last_sent_at: dict[int, float] = {}

    def maybe_report(
        self,
        track: RtpTrack,
        *,
        now: float,
        ntp_seconds: float,
    ):
        last_sent_at = self._last_sent_at.get(track.ssrc)
        if track.packet_count == 0:
            return None
        if last_sent_at is None or now - last_sent_at >= 5.0:
            self._last_sent_at[track.ssrc] = now
            return self._build_report(track, now=now, ntp_seconds=ntp_seconds)
        return None

    def _build_report(self, track: RtpTrack, *, now: float, ntp_seconds: float) -> bytes:
        ntp_fraction = int((ntp_seconds - int(ntp_seconds)) * (1 << 32))
        ntp_seconds_int = int(ntp_seconds) & 0xFFFFFFFF
        rtp_timestamp = track.last_emitted_timestamp
        if track.last_emitted_wallclock is not None:
            rtp_timestamp += max(0, int(
                (now - track.last_emitted_wallclock) * track.clock_rate
            ))
        report = struct.pack(
            ">BBHIIIIII",
            0x80,
            200,
            6,
            track.ssrc & 0xFFFFFFFF,
            ntp_seconds_int,
            ntp_fraction & 0xFFFFFFFF,
            rtp_timestamp & 0xFFFFFFFF,
            track.packet_count & 0xFFFFFFFF,
            track.octet_count & 0xFFFFFFFF,
        )
        cname = self._cname.encode("utf-8")
        chunk = struct.pack(">IBB", track.ssrc & 0xFFFFFFFF, 1, len(cname)) + cname + b"\x00"
        chunk += b"\x00" * (-len(chunk) % 4)
        sdes = struct.pack(">BBH", 0x81, 202, len(chunk) // 4) + chunk
        return report + sdes


def split_annex_b(body: bytes) -> list[bytes]:
    units: list[bytes] = []
    start = 0
    i = 0
    while i + 2 < len(body):
        if body[i] == 0 and body[i + 1] == 0:
            if body[i + 2] == 1:
                units.append(body[start:i])
                start = i + 3
                i += 3
                continue
            if (
                body[i + 2] == 0
                and i + 3 < len(body)
                and body[i + 3] == 1
            ):
                units.append(body[start:i])
                start = i + 4
                i += 4
                continue
        i += 1
    units.append(body[start:])
    return [u for u in units if u]


def packetize_video(codec_id: int, access_unit: bytes) -> list[RtpPacket]:
    """Standalone video packetization used by tests."""

    packetizer = RtpPacketizer(
        video_ssrc=secrets.randbits(32),
        audio_ssrc=secrets.randbits(32),
    )
    return packetizer.packetize_video(codec_id, access_unit, pts=0)


def pts_to_video_timestamp(pts: int, _origin: int) -> int:
    return pts


def pts_to_audio_timestamp(pts: int, sample_rate: int) -> int:
    return int(pts * sample_rate / _VIDEO_CLOCK_RATE)


def replace_marker(packet: RtpPacket, *, marker: bool) -> RtpPacket:
    return RtpPacket(
        payload=packet.payload,
        marker=marker,
        sequence=packet.sequence,
        timestamp=packet.timestamp,
        ssrc=packet.ssrc,
        payload_type=packet.payload_type,
    )


def build_sdp(
    contract: MediaContract,
    ports: Mapping[str, tuple[int, int]],
    parameter_sets: Mapping[str, bytes | None],
) -> str:
    """Render the SDP for one contract and per-track ports."""

    lines = [
        "v=0",
        "o=- 0 0 IN IP4 127.0.0.1",
        "s=miss",
        "c=IN IP4 127.0.0.1",
        "t=0 0",
    ]
    if contract.video_codec in _VIDEO_PAYLOAD_TYPE:
        rtp_port, rtcp_port = ports["video"]
        lines.append(f"m=video {rtp_port} RTP/AVP {_VIDEO_PAYLOAD_TYPE[contract.video_codec]}")
        lines.append(f"a=rtcp:{rtcp_port} IN IP4 127.0.0.1")
        if contract.video_codec == 4:
            lines.append(
                f"a=rtpmap:{_VIDEO_PAYLOAD_TYPE[4]} H264/{_VIDEO_CLOCK_RATE}"
            )
            sps_b64 = base64.b64encode(parameter_sets.get("sps") or contract.video_sps).decode()
            pps_b64 = base64.b64encode(parameter_sets.get("pps") or contract.video_pps).decode()
            lines.append(
                "a=fmtp:96 packetization-mode=1;"
                f"sprop-parameter-sets={sps_b64},{pps_b64}"
            )
        else:
            lines.append(
                f"a=rtpmap:{_VIDEO_PAYLOAD_TYPE[5]} H265/{_VIDEO_CLOCK_RATE}"
            )
            vps_b64 = base64.b64encode(parameter_sets.get("vps") or contract.vps or b"").decode()
            sps_b64 = base64.b64encode(parameter_sets.get("sps") or contract.video_sps).decode()
            pps_b64 = base64.b64encode(parameter_sets.get("pps") or contract.video_pps).decode()
            lines.append(
                "a=fmtp:98 "
                f"sprop-vps={vps_b64};sprop-sps={sps_b64};"
                f"sprop-pps={pps_b64}"
            )
    if contract.audio_codec is not None and contract.sample_rate:
        rtp_port, rtcp_port = ports["audio"]
        payload_type, rtpmap = payload_mapping(
            contract.audio_codec, contract.sample_rate
        )
        lines.append(f"m=audio {rtp_port} RTP/AVP {payload_type}")
        lines.append(f"a=rtcp:{rtcp_port} IN IP4 127.0.0.1")
        lines.append(f"a=rtpmap:{payload_type} {rtpmap}")
        if contract.audio_codec == 1032:
            lines.append("a=fmtp:111 stereo=1;sprop-stereo=1")
    return "\r\n".join(lines) + "\r\n"


__all__ = [
    "MAX_RTP_DATAGRAM_SIZE",
    "RtcpSender",
    "RtpPacket",
    "RtpPacketizer",
    "RtpTrack",
    "build_sdp",
    "packetize_video",
    "payload_mapping",
]