"""Live view via the go2rtc xiaomi source for cameras with a p2p-stream service."""

import asyncio
import logging
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from homeassistant.components.camera import CameraEntityFeature
from homeassistant.components.camera.webrtc import DATA_WEBRTC_PROVIDERS
from micloud.micloudexception import MiCloudException

from custom_components.xiaomi_miot.camera import CameraEntity
from custom_components.xiaomi_miot.core.converters import MiotCameraConv

MODEL = "test.camera.p2p"
HOST = "192.168.1.10"
CLIP_SOURCE = "-i https://processor.smartcamera.api.io.mi.com/clip.m3u8"
MISS_VENDOR = {
    "code": 0,
    "result": {
        "vendor": {"vendor": 4, "vendor_params": {"expires": 4102444800}},
        "public_key": "devpub",
        "sign": "devsign",
    },
}


class FakeCloud:
    def __init__(self, responses, delay=0, error=None):
        self.responses = responses
        self.delay = delay
        self.error = error
        self.calls = []

    async def async_request_api(self, api, data, debug=True, **kwargs):
        self.calls.append((api, data, debug))
        if self.error:
            raise self.error
        await asyncio.sleep(self.delay)
        return self.responses.get(api)

    def count(self, api):
        return sum(1 for c in self.calls if c[0] == api)


class FakeProvider:
    def __init__(self, schemes):
        self.schemes = schemes

    def async_is_supported(self, url):
        return url.partition(":")[0] in self.schemes


@pytest.fixture
def make_camera(hass, make_device, load_miot_spec):
    def _make(cloud, *, schemes=("xiaomi",), customizes=None, model=MODEL):
        device = make_device(load_miot_spec(f"{MODEL}.json"), model=model, customizes=customizes)
        device.cloud = cloud
        device.info.data["localip"] = HOST
        hass.data[DATA_WEBRTC_PROVIDERS] = {FakeProvider(schemes)}
        conv = next(c for c in device.converters if isinstance(c, MiotCameraConv))
        camera = CameraEntity(device, conv)
        camera._attr_stream_source = CLIP_SOURCE
        return camera

    return _make


def _query(url):
    parts = urlsplit(url)
    assert parts.scheme == "xiaomi"
    assert parts.hostname == HOST
    return {k: v[0] for k, v in parse_qs(parts.query).items()}


async def test_miss_vendor_source(make_camera):
    cloud = FakeCloud({"v2/device/miss_get_vendor": MISS_VENDOR})
    camera = make_camera(cloud)
    assert camera.supported_features & CameraEntityFeature.STREAM

    query = _query(await camera.stream_source())
    sent = cloud.calls[0][1]
    assert query["did"] == "test-device"
    assert query["model"] == MODEL
    assert query["vendor"] == "cs2"
    assert query["client_public"] == sent["app_pubkey"]
    assert len(query["client_private"]) == 64
    assert query["device_public"] == "devpub"
    assert query["sign"] == "devsign"
    assert "password" not in query


async def test_legacy_devicepass_source(make_camera):
    cloud = FakeCloud({
        "v2/device/miss_get_vendor": {"code": 0, "result": {}},
        "device/devicepass": {"code": 0, "result": {"p2p_id": "UID123", "password": "secret"}},
    })
    query = _query(await make_camera(cloud).stream_source())
    assert query["uid"] == "UID123"
    assert query["password"] == "secret"
    assert "client_private" not in query


async def test_url_is_cached(make_camera):
    cloud = FakeCloud({"v2/device/miss_get_vendor": MISS_VENDOR})
    camera = make_camera(cloud)
    first = await camera.stream_source()
    assert await camera.stream_source() == first
    assert cloud.count("v2/device/miss_get_vendor") == 1


async def test_concurrent_callers_share_one_url(make_camera):
    cloud = FakeCloud({"v2/device/miss_get_vendor": MISS_VENDOR}, delay=0.05)
    camera = make_camera(cloud)
    urls = await asyncio.gather(*[camera.stream_source() for _ in range(3)])
    assert len(set(urls)) == 1
    assert cloud.count("v2/device/miss_get_vendor") == 1


@pytest.mark.parametrize("responses", [
    {"v2/device/miss_get_vendor": {"code": 0, "result": {**MISS_VENDOR["result"], "sign": None}}},
    {"v2/device/miss_get_vendor": {"code": 0, "result": {**MISS_VENDOR["result"], "public_key": ""}}},
    {"v2/device/miss_get_vendor": {"code": 0, "result": {**MISS_VENDOR["result"], "vendor": {"vendor": None}}}},
    {"v2/device/miss_get_vendor": None, "device/devicepass": None},
    {"v2/device/miss_get_vendor": {"code": 0, "result": {}}, "device/devicepass": {"code": -2, "message": "offline"}},
    {"v2/device/miss_get_vendor": {"code": 0, "result": {}}, "device/devicepass": {"code": 0, "result": {"p2p_id": "UID123"}}},
])
async def test_malformed_response_falls_back(make_camera, responses):
    camera = make_camera(FakeCloud(responses))
    assert await camera.stream_source() == CLIP_SOURCE
    assert camera._p2p_stream_url is None


@pytest.mark.parametrize("error", [
    MiCloudException("login failed"),
    requests.exceptions.ConnectionError("unreachable"),
    OSError("network down"),
])
async def test_cloud_error_falls_back(make_camera, error):
    camera = make_camera(FakeCloud({}, error=error))
    assert await camera.stream_source() == CLIP_SOURCE


async def test_no_xiaomi_provider_falls_back(make_camera):
    camera = make_camera(FakeCloud({"v2/device/miss_get_vendor": MISS_VENDOR}), schemes=("rtsp",))
    assert await camera.stream_source() == CLIP_SOURCE


async def test_opt_out(make_camera):
    cloud = FakeCloud({"v2/device/miss_get_vendor": MISS_VENDOR})
    camera = make_camera(cloud, customizes={"use_p2p_stream": False})
    assert not camera.supported_features & CameraEntityFeature.STREAM
    assert await camera.stream_source() == CLIP_SOURCE
    assert cloud.calls == []


class FakeImageProvider:
    def __init__(self, delay=0, error=None):
        self.delay = delay
        self.error = error
        self.calls = 0

    async def async_get_image(self, camera, width=None, height=None):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return f"jpeg-{self.calls}".encode()


@pytest.fixture
def image_camera(make_camera, monkeypatch):
    monkeypatch.setattr("custom_components.xiaomi_miot.camera.P2P_IMAGE_TIMEOUT", 0.05)
    monkeypatch.setattr("custom_components.xiaomi_miot.camera.P2P_IMAGE_INTERVAL", 0)

    def _make(provider):
        camera = make_camera(FakeCloud({"v2/device/miss_get_vendor": MISS_VENDOR}))
        camera._webrtc_provider = provider
        return camera

    return _make


async def test_concurrent_snapshots_share_one_request(image_camera):
    provider = FakeImageProvider(delay=0.01)
    camera = image_camera(provider)
    images = await asyncio.gather(*[camera.async_camera_image() for _ in range(3)])
    assert images == [b"jpeg-1"] * 3
    assert provider.calls == 1


async def test_slow_snapshot_refreshes_the_next_one(image_camera):
    provider = FakeImageProvider(delay=0.1)
    camera = image_camera(provider)
    assert await camera.async_camera_image() is None
    await camera._p2p_image_task
    # the timed out request finished in the background, the next caller gets its frame
    assert await camera.async_camera_image() == b"jpeg-1"
    await camera._p2p_image_task
    assert await camera.async_camera_image() == b"jpeg-2"
    await camera._p2p_image_task


async def test_snapshot_size_is_not_shared(image_camera):
    provider = FakeImageProvider(delay=0.01)
    camera = image_camera(provider)
    await asyncio.gather(camera.async_camera_image(), camera.async_camera_image(width=640))
    assert provider.calls == 2


async def test_snapshots_are_throttled(image_camera, monkeypatch):
    monkeypatch.setattr("custom_components.xiaomi_miot.camera.P2P_IMAGE_INTERVAL", 60)
    provider = FakeImageProvider()
    camera = image_camera(provider)
    assert await camera.async_camera_image() == b"jpeg-1"
    assert await camera.async_camera_image() == b"jpeg-1"
    assert provider.calls == 1
    camera._p2p_image_time -= 61
    assert await camera.async_camera_image() == b"jpeg-2"


async def test_failed_snapshot_falls_back(image_camera):
    camera = image_camera(FakeImageProvider(error=RuntimeError("no frame")))
    assert await camera.async_camera_image() is None
    camera._last_image = b"previous"
    assert await camera.async_camera_image() == b"previous"


@pytest.mark.parametrize("responses", [
    {"v2/device/miss_get_vendor": MISS_VENDOR},
    {
        "v2/device/miss_get_vendor": {"code": 0, "result": {}},
        "device/devicepass": {"code": 0, "result": {"p2p_id": "UID123", "password": "secret"}},
    },
])
async def test_keys_are_not_logged(make_camera, caplog, responses):
    caplog.set_level(logging.DEBUG)
    cloud = FakeCloud(responses)
    query = _query(await make_camera(cloud).stream_source())
    for key in ("client_private", "sign", "password"):
        if key in query:
            assert query[key] not in caplog.text
    assert all(debug is False for api, _, debug in cloud.calls)
