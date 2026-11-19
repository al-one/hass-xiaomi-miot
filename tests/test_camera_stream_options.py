from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


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
async def test_alarm_recording_is_not_opened_as_a_live_camera_stream():
    camera = _make_converter_camera(ALARM_M3U8_URL)
    camera.entity_id = 'camera.doorbell'
    assert camera.is_cloud_alarm_recording
    assert await camera.stream_source() is None
    assert camera.recording_media_source == 'media-source://xiaomi_miot/camera.doorbell'


def test_alarm_event_exposes_media_source_and_keeps_snapshot(monkeypatch):
    camera = _make_converter_camera(None)
    camera.entity_id = 'camera.doorbell'
    camera._last_motion_time = None
    camera._attr_extra_state_attributes = {}
    monkeypatch.setattr(camera, 'get_alarm_image_address', lambda *args: 'snapshot')
    monkeypatch.setattr(camera, 'get_alarm_m3u8_url', lambda *args: ALARM_M3U8_URL)
    camera.update_motion_video({
        'motion_video_time': '2026-10-14 15:00:00',
        'motion_video_type': 'motion',
        'motion_video_latest': {'fileId': 'recording-1', 'imgStoreId': 'image-1'},
    })
    assert camera._attr_camera_image == 'snapshot'
    assert camera._attr_extra_state_attributes['motion_video_media_source'] == (
        'media-source://xiaomi_miot/camera.doorbell'
    )
    assert camera._attr_extra_state_attributes['motion_video_time'] == '2026-10-14 15:00:00'


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
async def test_non_alarm_camera_sources_keep_live_streams(url, cloud):
    """Local, live, RTSP and non-Xiaomi sources keep their stream source."""
    camera = _make_converter_camera(url, cloud=cloud)

    assert await camera.stream_source() == url
    assert camera.recording_media_source is None
    assert camera.stream_options == {}


@pytest.mark.asyncio
async def test_miot_rtsp_stream_path_keeps_live_rtsp():
    """The separate MIoT camera stream path keeps its existing RTSP behavior."""
    camera = MiotCameraEntity.__new__(MiotCameraEntity)
    camera._motion_enable = False
    camera.stream_options = {}
    camera.async_get_stream_address = AsyncMock(return_value='rtsp://192.0.2.10/live')

    assert await camera.stream_source() == 'rtsp://192.0.2.10/live'
    assert camera.stream_options == {}
