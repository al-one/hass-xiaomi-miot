"""Doorbell live wake: sleepy cateye doorbells wake via wakeup_host, then stream."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.xiaomi_miot.camera import CameraEntity
from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud


def _make_camera(*, live_url=None, stream_source='https://example.invalid/clip.m3u8',
                 did='1037929737', model='madv.cateye.mowl3g', wake=None):
    camera = CameraEntity.__new__(CameraEntity)
    camera.device = SimpleNamespace(
        cloud=SimpleNamespace() if wake is None else SimpleNamespace(),
        did=did,
    )
    camera.model = model
    camera._attr_stream_source = stream_source
    camera._supported_features = type(camera._supported_features or 0)(0) \
        if hasattr(camera, '_supported_features') else 0
    camera._wake_mock = wake
    camera.custom_config = lambda key=None, default=None: \
        live_url if key == 'live_stream_url' else default
    if wake is not None:
        camera.device.cloud = SimpleNamespace(async_wake_sleepy_device=wake)
    else:
        camera.device.cloud = None
    # bind wake helper to use mock cloud
    async def _wake():
        cloud = camera.device.cloud
        fn = getattr(cloud, 'async_wake_sleepy_device', None)
        if not fn:
            return False
        try:
            return await fn(camera.device.did, camera.model) or False
        except Exception:
            return False
    camera.async_wake_device_for_live = _wake
    return camera


@pytest.mark.asyncio
async def test_live_url_wakes_then_streams():
    wake = AsyncMock(return_value=True)
    camera = _make_camera(live_url='rtsp://192.0.2.10/doorbell', wake=wake)
    assert await camera.stream_source() == 'rtsp://192.0.2.10/doorbell'
    wake.assert_awaited_once_with('1037929737', 'madv.cateye.mowl3g')


@pytest.mark.asyncio
async def test_no_live_url_keeps_recording_source():
    camera = _make_camera(live_url=None)
    camera.custom_config = lambda key=None, default=None: default
    assert await camera.stream_source() == 'https://example.invalid/clip.m3u8'


@pytest.mark.asyncio
async def test_wake_failure_still_returns_live_url():
    wake = AsyncMock(return_value=False)
    camera = _make_camera(live_url='rtsp://192.0.2.10/doorbell', wake=wake)
    assert await camera.stream_source() == 'rtsp://192.0.2.10/doorbell'
    wake.assert_awaited_once()


@pytest.mark.asyncio
async def test_cloud_wake_tries_host_first_for_cateye():
    cloud = MiotCloud.__new__(MiotCloud)
    calls = []

    async def fake_api(api, data, **kwargs):
        calls.append((api, data))
        if data.get('method') == 'wakeup_host':
            return {'code': 0, 'result': ['ok']}
        return {'code': -3, 'message': 'timeout'}

    cloud.async_request_api = fake_api
    assert await MiotCloud.async_wake_sleepy_device(
        cloud, '1037929737', 'madv.cateye.mowl3g') is True
    assert calls[0][1]['method'] == 'wakeup_host'
    assert calls[0][0] == 'home/rpc/1037929737'


@pytest.mark.asyncio
async def test_cloud_wake_falls_back_to_legacy():
    cloud = MiotCloud.__new__(MiotCloud)
    calls = []

    async def fake_api(api, data, **kwargs):
        calls.append(data.get('method'))
        if data.get('method') == 'wakeup_host':
            return {'code': -3, 'message': 'timeout'}
        return {'code': 0, 'result': ['ok']}

    cloud.async_request_api = fake_api
    assert await MiotCloud.async_wake_sleepy_device(
        cloud, '1037929737', 'madv.cateye.mowl3g') is True
    assert calls == ['wakeup_host', 'wakeup']


@pytest.mark.asyncio
async def test_cloud_wake_returns_false_when_all_fail():
    cloud = MiotCloud.__new__(MiotCloud)

    async def fake_api(api, data, **kwargs):
        return {'code': -3, 'message': 'timeout'}

    cloud.async_request_api = fake_api
    assert await MiotCloud.async_wake_sleepy_device(
        cloud, '1037929737', 'madv.cateye.mowl3g') is False

def _make_device_level_camera(entity_url=None, device_url=None):
    from unittest.mock import patch
    from homeassistant.components.camera import CameraEntityFeature
    camera = CameraEntity.__new__(CameraEntity)
    camera.device = SimpleNamespace(
        cloud=None,
        did='1037929737',
        custom_config=lambda key=None, default=None: (
            device_url if key == 'live_stream_url' else default),
    )
    camera.model = 'madv.cateye.mowl3g'
    camera._attr_stream_source = 'https://example.invalid/clip.m3u8'
    camera._supported_features = CameraEntityFeature(0)
    parent = patch(
        'custom_components.xiaomi_miot.core.hass_entity.BasicEntity'
        '.custom_config',
        lambda self, key=None, default=None: (
            entity_url if key == 'live_stream_url' else default),
    )
    parent.start()
    camera._parent_patch = parent
    return camera


@pytest.mark.asyncio
async def test_device_level_live_url_used_when_entity_empty():
    from homeassistant.components.camera import CameraEntityFeature
    camera = _make_device_level_camera(
        entity_url=None, device_url='rtsp://192.0.2.10/doorbell')
    try:
        assert await camera.stream_source() == 'rtsp://192.0.2.10/doorbell'
        assert camera.supported_features & CameraEntityFeature.STREAM
    finally:
        camera._parent_patch.stop()


@pytest.mark.asyncio
async def test_entity_level_live_url_wins_over_device():
    camera = _make_device_level_camera(
        entity_url='rtsp://192.0.2.20/entity',
        device_url='rtsp://192.0.2.10/doorbell')
    try:
        assert await camera.stream_source() == 'rtsp://192.0.2.20/entity'
    finally:
        camera._parent_patch.stop()
