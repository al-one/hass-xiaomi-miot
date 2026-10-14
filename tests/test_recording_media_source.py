"""Contract tests for authenticated Xiaomi alarm recording playback."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from homeassistant.components.media_source import MediaSourceItem, Unresolvable
from homeassistant.components.ffmpeg import DATA_FFMPEG
from homeassistant.setup import async_setup_component

from custom_components.xiaomi_miot import DOMAIN
from custom_components.xiaomi_miot.core import recording
from custom_components.xiaomi_miot.media_source import async_get_media_source

CAMERA_ID = "camera.doorbell"
HOST = "https://cam.io.mi.com"
KEY = bytes(range(16))


class _Response:
    def __init__(self, body: bytes, status: int = 200, headers=None):
        self.body = body
        self.status_code = status
        self.headers = headers or {"Content-Length": str(len(body))}

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        pass


def _clip(path: Path, frequency: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=128x96:rate=8:duration=1",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=8000:duration=1",
            "-c:v",
            "mpeg4",
            "-q:v",
            "5",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            "-y",
            str(path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _encrypt(data: bytes, iv: bytes) -> bytes:
    padder = padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    encryptor = Cipher(algorithms.AES(KEY), modes.CBC(iv)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _playlist(url: str, segments: list[tuple[str, bytes]]) -> dict[str, bytes]:
    objects = {f"{HOST}/key": KEY}
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-MEDIA-SEQUENCE:7"]
    for index, (name, data) in enumerate(segments):
        iv = (7 + index).to_bytes(16, "big")
        lines.extend(
            [
                f'#EXT-X-KEY:METHOD=AES-128,URI="{HOST}/key",IV=0x{iv.hex()}',
                "#EXTINF:1.0,",
                name,
            ]
        )
        objects[f"{HOST}/alarm/{name}"] = _encrypt(data, iv)
    lines.append("#EXT-X-ENDLIST")
    objects[url] = "\n".join(lines).encode()
    return objects


@pytest.fixture
def media(monkeypatch, tmp_path):
    """Build two independent encrypted MP4s and a private mocked origin."""
    source_a = tmp_path / "source-a.mp4"
    source_b = tmp_path / "source-b.mp4"
    _clip(source_a, 440)
    _clip(source_b, 660)
    playlist_url = f"{HOST}/alarm/playlist.m3u8?signature=fixture"
    objects = _playlist(
        playlist_url,
        [
            ("segment-0.mp4", source_a.read_bytes()),
            ("segment-1.mp4", source_b.read_bytes()),
        ],
    )
    requested = []

    def get(url, **kwargs):
        requested.append(url)
        return _Response(objects[url])

    monkeypatch.setattr(recording.requests, "get", get)
    return playlist_url, objects, requested


def _probe(path: Path, entries: str) -> list[str]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            entries,
            "-of",
            "csv=p=0",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().split(",")


def test_encrypted_playlist_remux_keeps_all_frames_and_audio(tmp_path, media):
    playlist_url, _, _ = media
    output = tmp_path / "recording.mp4"
    recording.download_and_remux_recording(playlist_url, output, "ffmpeg")

    assert _probe(output, "stream=codec_name,nb_read_frames") == ["h264", "16"]
    streams = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "stream=codec_type,nb_read_frames",
            "-of",
            "csv=p=0",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert streams == ["video,16", "audio,18"]
    assert output.stat().st_mode & 0o777 == 0o600


def test_rejects_external_playlist_and_untrusted_redirect(monkeypatch, tmp_path, media):
    with pytest.raises(recording.RecordingError):
        recording.download_and_remux_recording(
            "https://example.invalid/playlist.m3u8", tmp_path / "x.mp4", "ffmpeg"
        )

    playlist_url, _, requested = media

    def redirect(url, **kwargs):
        requested.append(url)
        return _Response(
            b"", status=302, headers={"Location": "https://example.invalid/x"}
        )

    monkeypatch.setattr(recording.requests, "get", redirect)
    with pytest.raises(recording.RecordingError):
        recording.download_and_remux_recording(
            playlist_url, tmp_path / "redirect.mp4", "ffmpeg"
        )
    assert all("example.invalid" not in url for url in requested)


@pytest.mark.asyncio
async def test_browse_resolve_authenticated_range_and_identity_refresh(
    hass, hass_client, hass_client_no_auth, monkeypatch, tmp_path, media
):
    playlist_url, objects, requested = media
    camera = SimpleNamespace(
        entity_id=CAMERA_ID,
        name="Front door",
        is_cloud_alarm_recording=True,
        _attr_stream_source=playlist_url,
        _attr_extra_state_attributes={"motion_video_time": "2026-10-14 15:00:00"},
    )
    hass.data.setdefault(DOMAIN, {})["entities"] = {CAMERA_ID: camera}
    hass.data[DATA_FFMPEG] = SimpleNamespace(binary="ffmpeg")
    monkeypatch.setattr(
        hass.config, "path", lambda *parts: str(tmp_path.joinpath(*parts))
    )
    assert await async_setup_component(hass, "http", {})
    source = await async_get_media_source(hass)

    root = await source.async_browse_media(MediaSourceItem(hass, DOMAIN, None, None))
    assert [child.identifier for child in root.children] == [CAMERA_ID]
    assert "Front door" in root.children[0].title
    item = MediaSourceItem(hass, DOMAIN, CAMERA_ID, None)
    play, coalesced_play = await asyncio.gather(
        source.async_resolve_media(item),
        source.async_resolve_media(item),
    )
    assert coalesced_play == play
    assert play.mime_type == "video/mp4"
    first_request_count = len(requested)
    assert await source.async_resolve_media(item) == play
    assert len(requested) == first_request_count
    client = await hass_client()
    anon = await hass_client_no_auth()
    assert (await anon.get(play.url)).status == 401
    full = await client.get(play.url)
    assert full.status == 200
    assert full.headers["Content-Type"].startswith("video/mp4")
    assert (await full.read())[4:8] == b"ftyp"
    partial = await client.get(play.url, headers={"Range": "bytes=0-31"})
    assert partial.status == 206
    assert partial.headers["Content-Range"].startswith("bytes 0-31/")
    assert len(await partial.read()) == 32

    old_path = source.store.by_camera[CAMERA_ID].path
    old_id = source.store.by_camera[CAMERA_ID].opaque_id
    old_url = camera._attr_stream_source
    new_url = old_url.replace("fixture", "fixture2")
    camera._attr_stream_source = new_url
    objects[new_url] = objects[old_url]
    refresh = await source.async_resolve_media(item)
    assert refresh.url != play.url
    assert (await client.get(play.url)).status == 404
    assert source.store.by_camera[CAMERA_ID].opaque_id != old_id
    assert old_path == source.store.by_camera[CAMERA_ID].path
    assert requested.count(old_url) == 1
    assert requested.count(new_url) == 1


@pytest.mark.asyncio
async def test_changed_identity_network_failure_removes_old_clip(
    hass, monkeypatch, tmp_path, media
):
    playlist_url, _, _ = media
    camera = SimpleNamespace(
        entity_id=CAMERA_ID,
        name="Front door",
        is_cloud_alarm_recording=True,
        _attr_stream_source=playlist_url,
        _attr_extra_state_attributes={"motion_video_time": "t1"},
    )
    hass.data.setdefault(DOMAIN, {})["entities"] = {CAMERA_ID: camera}
    hass.data[DATA_FFMPEG] = SimpleNamespace(binary="ffmpeg")
    monkeypatch.setattr(
        hass.config, "path", lambda *parts: str(tmp_path.joinpath(*parts))
    )
    assert await async_setup_component(hass, "http", {})
    source = await async_get_media_source(hass)
    item = MediaSourceItem(hass, DOMAIN, CAMERA_ID, None)
    old_play = await source.async_resolve_media(item)
    old_path = source.store.by_camera[CAMERA_ID].path

    camera._attr_extra_state_attributes["motion_video_time"] = "t2"

    def failed_get(url, **kwargs):
        raise OSError("private fixture URL must not escape")

    monkeypatch.setattr(recording.requests, "get", failed_get)
    with pytest.raises(Unresolvable, match="Unable to load"):
        await source.async_resolve_media(item)
    assert not old_path.exists()
    assert old_play.url.rsplit("/", 1)[-1].split(".")[0] not in source.store.by_id
