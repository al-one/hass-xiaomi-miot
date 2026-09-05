from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.xiaomi_miot import DOMAIN
from custom_components.xiaomi_miot.button import ManualSceneButton
from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud


async def test_get_manual_scenes_from_all_homes():
    cloud = MiotCloud.__new__(MiotCloud)
    cloud.user_id = '1000'
    cloud.async_get_homerooms = AsyncMock(return_value=[
        {'id': '1', 'uid': '1000', 'name': 'Home'},
        {'id': '2', 'uid': '2000', 'name': 'Shared home'},
    ])
    cloud._async_request_manual_scene_api = AsyncMock(side_effect=[
        [{'scene_id': 11, 'scene_name': 'Sleep'}],
        [{'scene_id': '22', 'scene_name': 'Work', 'room_id': '3'}],
    ])

    scenes = await cloud.async_get_manual_scenes()

    assert scenes == [
        {
            'scene_id': '11',
            'scene_name': 'Sleep',
            'home_id': '1',
            'home_name': 'Home',
            'owner_uid': '1000',
        },
        {
            'scene_id': '22',
            'scene_name': 'Work',
            'room_id': '3',
            'home_id': '2',
            'home_name': 'Shared home',
            'owner_uid': '2000',
        },
    ]


async def test_run_manual_scene_uses_scene_owner_and_scope():
    cloud = MiotCloud.__new__(MiotCloud)
    cloud._async_request_manual_scene_api = AsyncMock(return_value=True)

    result = await cloud.async_run_manual_scene({
        'owner_uid': '1000',
        'scene_id': '11',
        'home_id': '1',
        'room_id': '3',
    })

    assert result is True
    cloud._async_request_manual_scene_api.assert_awaited_once_with(
        'NewRunScene',
        {
            'owner_uid': '1000',
            'scene_id': '11',
            'scene_type': 2,
            'home_id': '1',
            'room_id': '3',
        },
    )


async def test_manual_scene_buttons_share_one_device():
    cloud = SimpleNamespace(
        unique_id='1000-cn-xiaomiio',
        async_run_manual_scene=AsyncMock(return_value=True),
    )
    first = ManualSceneButton(cloud, {
        'owner_uid': '1000',
        'scene_id': '11',
        'scene_name': 'Sleep',
        'home_id': '1',
        'home_name': 'Home',
    }, 'Sleep')
    second = ManualSceneButton(cloud, {
        'owner_uid': '1000',
        'scene_id': '22',
        'scene_name': 'Work',
        'home_id': '1',
        'home_name': 'Home',
    }, 'Work')

    assert first.device_info['identifiers'] == second.device_info['identifiers']
    assert first.device_info['identifiers'] == {
        (DOMAIN, '1000-cn-xiaomiio-manual-scenes')
    }

    await first.async_press()
    cloud.async_run_manual_scene.assert_awaited_once_with(first.scene)


async def test_manual_scene_button_reports_failed_execution():
    cloud = SimpleNamespace(
        unique_id='1000-cn-xiaomiio',
        async_run_manual_scene=AsyncMock(return_value=False),
    )
    button = ManualSceneButton(cloud, {
        'owner_uid': '1000',
        'scene_id': '11',
        'scene_name': 'Sleep',
        'home_id': '1',
        'home_name': 'Home',
    }, 'Sleep')

    with pytest.raises(HomeAssistantError):
        await button.async_press()
