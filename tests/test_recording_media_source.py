"""Contract tests for authenticated Xiaomi alarm recording playback."""

from __future__ import annotations

import asyncio
import base64
import subprocess
from datetime import UTC, datetime
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
from custom_components.xiaomi_miot.camera import ARCHIVE_EVENT, SERVICE_TO_METHOD, BaseCameraEntity

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


class _EventCloud:
    default_server = "cn"

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get_api_by_host(self, host, path):
        return f"https://{host}/{path}"

    async def async_request_api(self, api, data, method="GET", crypt=False):
        self.calls.append(data)
        return {"data": {"thirdPartPlayUnits": self.pages.pop(0) if self.pages else []}}


def _event_entity(cloud):
    return SimpleNamespace(
        device=SimpleNamespace(cloud=cloud, did="42"),
        model="madv.cateye.mowl3g",
    )


class _EventCamera:
    entity_id = CAMERA_ID
    name = "Front door"
    is_cloud_alarm_recording = True
    _attr_stream_source = f"{HOST}/common/app/m3u8"
    _attr_extra_state_attributes: dict = {}

    def __init__(self, urls):
        self.urls = urls

    async def async_alarm_event_url(self, file_id):
        return self.urls.get(file_id)


@pytest.mark.asyncio
async def test_event_list_pages_full_history_with_raw_fields():
    cloud = _EventCloud(
        [
            [
                {"fileId": "a", "createTime": 3000, "videoStoreId": 1, "imgStoreId": 2, "isAlarm": True},
                {"fileId": "b", "createTime": 2000, "videoStoreId": 3, "imgStoreId": 4, "isAlarm": False},
            ],
            [{"fileId": "c", "createTime": 1500, "videoStoreId": 5, "imgStoreId": 6}],
        ]
    )
    events = await BaseCameraEntity.get_alarm_events(
        _event_entity(cloud), 0, 5000, True, page_size=2
    )
    assert [event["fileId"] for event in events] == ["a", "b", "c"]
    assert events[0]["createTime"] == 3000
    assert events[0]["imgStoreId"] == 2
    assert [call["limit"] for call in cloud.calls] == [2, 2]
    assert cloud.calls[1]["endTime"] == 1999
    assert all(call["beginTime"] == 0 and call["doorBell"] is True for call in cloud.calls)


@pytest.mark.asyncio
async def test_event_list_never_requests_more_than_fifty():
    cloud = _EventCloud([[]])
    assert await BaseCameraEntity.get_alarm_events(
        _event_entity(cloud), 0, 5000, False, page_size=500
    ) == []
    assert cloud.calls[0]["limit"] == 50


@pytest.mark.asyncio
async def test_alarm_event_url_lists_history_once_for_unknown_file():
    entity = SimpleNamespace(_alarm_events=None, listed=0)

    async def list_events():
        entity.listed += 1
        entity._alarm_events = {"a": {"fileId": "a", "isAlarm": True}}

    entity.async_list_alarm_events = list_events
    entity.get_alarm_m3u8_url = lambda file_id, is_alarm=False, **kwargs: f"m3u8:{file_id}:{is_alarm}"
    assert await BaseCameraEntity.async_alarm_event_url(entity, "a") == "m3u8:a:True"
    assert entity.listed == 1
    assert await BaseCameraEntity.async_alarm_event_url(entity, "a") == "m3u8:a:True"
    assert entity.listed == 1
    assert await BaseCameraEntity.async_alarm_event_url(entity, "zz") is None
    assert entity.listed == 2


@pytest.mark.asyncio
async def test_per_event_resolve_keeps_each_clip_addressable(
    hass, hass_client, hass_client_no_auth, monkeypatch, tmp_path, media
):
    playlist_url, objects, requested = media
    other_url = playlist_url.replace("fixture", "fixture2")
    objects[other_url] = objects[playlist_url]
    camera = _EventCamera({"a": playlist_url, "b": other_url})
    hass.data.setdefault(DOMAIN, {})["entities"] = {CAMERA_ID: camera}
    hass.data[DATA_FFMPEG] = SimpleNamespace(binary="ffmpeg")
    monkeypatch.setattr(
        hass.config, "path", lambda *parts: str(tmp_path.joinpath(*parts))
    )
    assert await async_setup_component(hass, "http", {})
    source = await async_get_media_source(hass)

    item_a = MediaSourceItem(hass, DOMAIN, f"{CAMERA_ID}/a", None)
    item_b = MediaSourceItem(hass, DOMAIN, f"{CAMERA_ID}/b", None)
    play_a = await source.async_resolve_media(item_a)
    play_b = await source.async_resolve_media(item_b)
    assert play_a.url != play_b.url
    assert await source.async_resolve_media(item_a) == play_a
    assert requested.count(playlist_url) == 1
    assert requested.count(other_url) == 1
    path_a = source.store.by_event[f"{CAMERA_ID}/a"].path
    path_b = source.store.by_event[f"{CAMERA_ID}/b"].path
    assert path_a != path_b
    assert path_a.exists() and path_b.exists()

    client = await hass_client()
    anon = await hass_client_no_auth()
    assert (await anon.get(play_a.url)).status == 401
    assert (await client.get(play_a.url)).status == 200
    assert (await client.get(play_b.url)).status == 200

    camera.urls.pop("b")
    with pytest.raises(Unresolvable):
        await source.async_resolve_media(
            MediaSourceItem(hass, DOMAIN, f"{CAMERA_ID}/missing", None)
        )


def test_archive_name_is_utc_type_and_file_id():
    created = int(datetime(2026, 10, 16, 9, 19, 16, tzinfo=UTC).timestamp() * 1000)
    assert recording.archive_name(created, "Bell:Pass", "590510936741910273") == (
        "20261016T091916Z_Bell-Pass_590510936741910273"
    )
    with pytest.raises(recording.RecordingError):
        recording.archive_name("bad", "Bell", "1")


def test_thumbnail_decrypts_jpeg_and_is_archived_once(monkeypatch, tmp_path):
    jpeg = b"\xff\xd8\xff" + b"thumbnail"
    iv = bytes(range(16, 32))
    url = f"{HOST}/alarm/img.jpg?signature=fixture"
    requested = []

    def get(u, **kwargs):
        requested.append(u)
        return _Response(_encrypt(jpeg, iv))

    monkeypatch.setattr(recording.requests, "get", get)
    out = tmp_path / "thumb.jpg"
    recording.download_thumbnail(url, KEY, iv, out)
    assert out.read_bytes() == jpeg
    assert out.stat().st_mode & 0o777 == 0o600
    recording.download_thumbnail(url, KEY, iv, out)
    assert requested == [url]


def test_thumbnail_rejects_non_jpeg(monkeypatch, tmp_path):
    iv = bytes(range(16, 32))
    monkeypatch.setattr(
        recording.requests, "get", lambda u, **kwargs: _Response(_encrypt(b"plain", iv))
    )
    out = tmp_path / "bad.jpg"
    with pytest.raises(recording.RecordingError):
        recording.download_thumbnail(f"{HOST}/alarm/img.jpg?x=1", KEY, iv, out)
    assert not out.exists()


@pytest.mark.asyncio
async def test_archive_service_is_idempotent_and_fires_event(hass, tmp_path, media):
    playlist_url, objects, requested = media
    created = int(datetime(2026, 10, 16, 9, 19, 16, tzinfo=UTC).timestamp() * 1000)
    iv = bytes(range(16, 32))
    img_url = f"{HOST}/alarm/img.jpg?signature=fixture"
    objects[img_url] = _encrypt(b"\xff\xd8\xff" + b"thumb", iv)
    hass.data[DATA_FFMPEG] = SimpleNamespace(binary="ffmpeg")
    seen = []
    hass.bus.async_listen(ARCHIVE_EVENT, lambda event: seen.append(event.data))

    class _Cam:
        hass = None
        is_doorbell = True
        device = SimpleNamespace(
            cloud=SimpleNamespace(ssecurity=base64.b64encode(KEY).decode())
        )
        _segment_iv_hex = iv.hex()

        async def get_alarm_events(self, begin=0, ended=None, doorbell=False, page_size=50):
            return [
                {
                    "fileId": "590510936741910273",
                    "createTime": created,
                    "duration": 20.51,
                    "eventType": "Bell:Pass",
                    "isAlarm": True,
                    "imgStoreId": "CAMERA_IMG_fixture",
                }
            ]

        def get_alarm_m3u8_url(self, file_id, is_alarm=False, videoCodec="H265"):
            return playlist_url

        def get_alarm_image_address(self, file_id, store_id, crypto=False):
            return img_url

    cam = _Cam()
    cam.hass = hass
    first = await BaseCameraEntity.async_archive_alarm_events(cam, 0, None, str(tmp_path))
    await hass.async_block_till_done()
    stem = "20261016T091916Z_Bell-Pass_590510936741910273"
    clip = tmp_path / f"{stem}.mp4"
    assert [item["path"] for item in first] == [str(clip)]
    assert clip.is_file()
    assert (tmp_path / f"{stem}.jpg").is_file()
    assert float(_probe(clip, "format=duration")[0]) > 0
    assert first[0]["start"] == "2026-10-16T09:19:16+00:00"
    assert first[0]["end"] == "2026-10-16T09:19:36.510000+00:00"
    assert first[0]["type"] == "Bell:Pass"
    assert first[0]["fileId"] == "590510936741910273"
    assert seen == first
    playlist_hits = requested.count(playlist_url)
    assert playlist_hits == 1

    second = await BaseCameraEntity.async_archive_alarm_events(cam, 0, None, str(tmp_path))
    assert second == []
    assert requested.count(playlist_url) == playlist_hits


def test_archive_service_schema_defaults():
    schema = SERVICE_TO_METHOD["archive_alarm_events"]["schema"]
    data = schema({"entity_id": CAMERA_ID})
    assert data["begin"] == 0
    assert "ended" not in data
    assert "archive_dir" not in data
