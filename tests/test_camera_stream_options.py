from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.components.stream import const as stream_const

from custom_components.xiaomi_miot.camera import CameraEntity, MiotCameraEntity


ALARM_M3U8_URL = (
    'https://sg.business.smartcamera.api.io.mi.com/common/app/m3u8?signature=masked'
)


def _make_converter_camera(url, *, cloud=True):
    camera = CameraEntity.__new__(CameraEntity)
    camera.device = SimpleNamespace(cloud=object() if cloud else None)
    camera._attr_stream_source = url
    camera.stream_options = {}
    return camera


@pytest.mark.asyncio
async def test_cloud_alarm_hls_disables_extension_picky_when_core_supports_it(
    monkeypatch,
):
    """Use FFmpeg's relaxed extension parsing for Xiaomi alarm playlists only."""
    monkeypatch.setattr(
        stream_const, 'CONF_HLS_EXTENSION_PICKY', 'hls_extension_picky', raising=False
    )
    camera = _make_converter_camera(ALARM_M3U8_URL)

    assert await camera.stream_source() == ALARM_M3U8_URL
    assert camera.stream_options == {'hls_extension_picky': False}


@pytest.mark.asyncio
async def test_cloud_alarm_hls_keeps_older_core_schema_compatible(monkeypatch):
    """Do not pass a stream option before Core defines and validates it."""
    monkeypatch.delattr(stream_const, 'CONF_HLS_EXTENSION_PICKY', raising=False)
    camera = _make_converter_camera(ALARM_M3U8_URL)

    assert await camera.stream_source() == ALARM_M3U8_URL
    assert camera.stream_options == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('url', 'cloud'),
    [
        (ALARM_M3U8_URL, False),
        ('https://sg17.livestreaming.io.mi.com/playlist.m3u8', True),
        ('rtsp://192.0.2.10/live', True),
        ('https://example.invalid/common/app/m3u8?signature=masked', True),
    ],
)
async def test_non_alarm_camera_sources_keep_strict_stream_options(
    monkeypatch, url, cloud
):
    """Local, live, RTSP and non-Xiaomi sources do not get the HLS override."""
    monkeypatch.setattr(
        stream_const, 'CONF_HLS_EXTENSION_PICKY', 'hls_extension_picky', raising=False
    )
    camera = _make_converter_camera(url, cloud=cloud)

    assert await camera.stream_source() == url
    assert camera.stream_options == {}


@pytest.mark.asyncio
async def test_miot_rtsp_stream_path_does_not_get_alarm_hls_option(monkeypatch):
    """The separate MIoT camera stream path keeps its existing RTSP behavior."""
    monkeypatch.setattr(
        stream_const, 'CONF_HLS_EXTENSION_PICKY', 'hls_extension_picky', raising=False
    )
    camera = MiotCameraEntity.__new__(MiotCameraEntity)
    camera._motion_enable = False
    camera.stream_options = {}
    camera.async_get_stream_address = AsyncMock(return_value='rtsp://192.0.2.10/live')

    assert await camera.stream_source() == 'rtsp://192.0.2.10/live'
    assert camera.stream_options == {}
