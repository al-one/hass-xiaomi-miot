import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.xiaomi_miot import DOMAIN
from custom_components.xiaomi_miot.button import (
    ManualSceneButton,
    _manual_scene_button_names,
)
from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException, MiotCloud


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


async def test_get_manual_scenes_skips_failed_home():
    cloud = MiotCloud.__new__(MiotCloud)
    cloud.user_id = '1000'
    cloud.async_get_homerooms = AsyncMock(return_value=[
        {'id': '1', 'uid': '1000', 'name': 'Unavailable home'},
        {'id': '2', 'uid': '1000', 'name': 'Available home'},
    ])
    cloud._async_request_manual_scene_api = AsyncMock(side_effect=[
        MiCloudException('request failed'),
        [{'scene_id': '22', 'scene_name': 'Work'}],
    ])

    scenes = await cloud.async_get_manual_scenes()

    assert scenes == [{
        'scene_id': '22',
        'scene_name': 'Work',
        'home_id': '2',
        'home_name': 'Available home',
        'owner_uid': '1000',
    }]


async def test_manual_scene_api_requires_zero_code():
    cloud = MiotCloud.__new__(MiotCloud)
    cloud.is_token_expired = lambda result: False
    cloud.async_request_api = AsyncMock(return_value={'code': 0, 'result': []})

    assert await cloud._async_request_manual_scene_api('method', {}) == []

    cloud.async_request_api.return_value = {'code': 1, 'result': True}
    with pytest.raises(MiCloudException):
        await cloud._async_request_manual_scene_api('method', {})


@pytest.mark.parametrize('authorized', [True, False])
async def test_manual_scene_auth_refresh_retries_only_a_rejected_request(authorized):
    cloud = MiotCloud.__new__(MiotCloud)
    cloud.async_check_auth = AsyncMock(return_value=authorized)
    cloud.async_request_api = AsyncMock(side_effect=[
        {'code': 3}, {'code': 0, 'result': True},
    ])
    if authorized:
        assert await cloud._async_request_manual_scene_api('NewRunScene', {}) is True
    else:
        with pytest.raises(MiCloudException):
            await cloud._async_request_manual_scene_api('NewRunScene', {})
    cloud.async_check_auth.assert_awaited_once_with(notify=True)
    assert cloud.async_request_api.await_count == 1 + int(authorized)


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


def test_manual_scene_button_names_disambiguate_homes():
    scenes = [
        {'scene_id': '11', 'scene_name': 'Sleep', 'home_id': '1', 'home_name': ''},
        {'scene_id': '22', 'scene_name': 'Sleep', 'home_id': '2', 'home_name': ''},
        {'scene_id': '33', 'scene_name': 'Work', 'home_id': '3', 'home_name': 'Home'},
        {'scene_id': '44', 'scene_name': 'Work', 'home_id': '4', 'home_name': 'Home'},
        {'scene_id': '55', 'scene_name': 'Away', 'home_id': '5', 'home_name': 'Family'},
    ]

    assert _manual_scene_button_names(scenes) == [
        '1 Sleep',
        '2 Sleep',
        'Home Work 3-33',
        'Home Work 4-44',
        'Family Away',
    ]


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


async def test_manual_scene_button_reports_cloud_error():
    cloud = SimpleNamespace(
        unique_id='1000-cn-xiaomiio',
        async_run_manual_scene=AsyncMock(
            side_effect=MiCloudException('request failed')
        ),
    )
    button = ManualSceneButton(cloud, {
        'owner_uid': '1000',
        'scene_id': '11',
        'scene_name': 'Sleep',
        'home_id': '1',
        'home_name': 'Home',
    }, 'Sleep')

    with pytest.raises(HomeAssistantError, match='Sleep'):
        await button.async_press()


@pytest.mark.parametrize('response', [None, [], ['bad'], 'bad', {'code': 0}, {'code': -1}])
async def test_manual_scene_api_rejects_malformed_responses(response):
    cloud = MiotCloud.__new__(MiotCloud)
    cloud.is_token_expired = lambda result: False
    cloud.async_request_api = AsyncMock(return_value=response)
    with pytest.raises(MiCloudException):
        await cloud._async_request_manual_scene_api('method', {})


async def test_scene_discovery_refetches_and_skips_malformed_entries():
    cloud = MiotCloud.__new__(MiotCloud)
    cloud.user_id = '1000'
    cloud.async_get_homerooms = AsyncMock(return_value=[None, {'id': '1'}])
    cloud._async_request_manual_scene_api = AsyncMock(side_effect=[
        [None, {'scene_id': 'bad', 'scene_name': []}, {'scene_id': '11', 'scene_name': 'Sleep'}],
        [{'scene_id': '22', 'scene_name': 'Work'}],
    ])
    assert [scene['scene_id'] for scene in await cloud.async_get_manual_scenes()] == ['11']
    assert [scene['scene_id'] for scene in await cloud.async_get_manual_scenes()] == ['22']
    assert cloud._async_request_manual_scene_api.await_count == 2


@pytest.mark.parametrize('response', [
    {'code': False, 'result': True}, {'code': 0.0, 'result': True},
    {'code': 0, 'error': {'code': -1}, 'result': True},
])
async def test_manual_scene_api_rejects_ambiguous_success_envelopes(response):
    cloud = MiotCloud.__new__(MiotCloud)
    cloud.is_token_expired = lambda result: False
    cloud.async_request_api = AsyncMock(return_value=response)
    with pytest.raises(MiCloudException):
        await cloud._async_request_manual_scene_api('NewRunScene', {})
    assert cloud.async_request_api.await_count == 1


@pytest.mark.parametrize('result', ['true', 1, {'unexpected': True}, [True], None])
async def test_manual_scene_execution_requires_boolean_result(result):
    cloud = MiotCloud.__new__(MiotCloud)
    cloud._async_request_manual_scene_api = AsyncMock(return_value=result)
    with pytest.raises(MiCloudException):
        await cloud.async_run_manual_scene({'owner_uid': '1000', 'scene_id': '11'})
    assert cloud._async_request_manual_scene_api.await_count == 1


@pytest.mark.parametrize('field,value', [
    ('scene_id', True), ('scene_id', ''), ('scene_id', {}),
    ('owner_uid', False), ('home_id', []), ('room_id', True),
])
async def test_manual_scene_invalid_execution_identity_is_not_sent(field, value):
    cloud = MiotCloud.__new__(MiotCloud)
    cloud._async_request_manual_scene_api = AsyncMock(return_value=True)
    scene = {'owner_uid': '1000', 'scene_id': '11', field: value}
    with pytest.raises(MiCloudException):
        await cloud.async_run_manual_scene(scene)
    cloud._async_request_manual_scene_api.assert_not_awaited()


async def test_manual_scene_discovery_rejects_conflicting_scope_and_duplicate_ids():
    cloud = MiotCloud.__new__(MiotCloud)
    cloud.user_id = '1000'
    cloud.async_get_homerooms = AsyncMock(return_value=[{'id': '1'}])
    cloud._async_request_manual_scene_api = AsyncMock(return_value=[
        {'scene_id': True, 'scene_name': 'Invalid'},
        {'scene_id': '11', 'scene_name': 'Wrong home', 'home_id': '2'},
        {'scene_id': '12', 'scene_name': 'Wrong owner', 'owner_uid': '2000'},
        {'scene_id': '13', 'scene_name': 'One'},
        {'scene_id': '13', 'scene_name': 'Different'},
        {'scene_id': '14', 'scene_name': 'Valid'},
        {'scene_id': '14', 'scene_name': 'Valid'},
    ])
    assert [s['scene_id'] for s in await cloud.async_get_manual_scenes()] == ['14']


async def test_manual_scene_rejects_overlap_and_releases_guard_after_cancellation():
    cloud = MiotCloud.__new__(MiotCloud)
    entered = asyncio.Event()

    async def execute(*args):
        entered.set()
        await asyncio.Event().wait()

    cloud._async_request_manual_scene_api = AsyncMock(side_effect=execute)
    scene = {'owner_uid': '1000', 'home_id': '1', 'scene_id': '11'}
    first = asyncio.create_task(cloud.async_run_manual_scene(scene))
    await entered.wait()
    try:
        with pytest.raises(MiCloudException, match='already running'):
            await cloud.async_run_manual_scene(dict(scene))
        assert cloud._async_request_manual_scene_api.await_count == 1
    finally:
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
    assert not cloud._manual_scene_in_flight
    cloud._async_request_manual_scene_api = AsyncMock(return_value=True)
    assert await cloud.async_run_manual_scene(scene) is True


async def test_different_manual_scenes_do_not_share_an_execution_lock():
    cloud = MiotCloud.__new__(MiotCloud)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def execute(*args):
        entered.set()
        await release.wait()
        return True

    cloud._async_request_manual_scene_api = AsyncMock(side_effect=execute)
    tasks = []
    try:
        for scene_id in ('11', '12'):
            tasks.append(asyncio.create_task(cloud.async_run_manual_scene({
                'owner_uid': '1000', 'home_id': '1', 'scene_id': scene_id,
            })))
        await entered.wait()
        await asyncio.sleep(0)
        assert cloud._async_request_manual_scene_api.await_count == 2
    finally:
        release.set()
        await asyncio.gather(*tasks)
    assert not cloud._manual_scene_in_flight
