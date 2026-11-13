"""Account scene cache and recovery tests, without cloud or device access."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.xiaomi_miot.core.manual_scenes import ManualScenes
from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException

HOME = {'id': '1', 'uid': '1000', 'name': 'Home'}
RECORD = {'scene_id': '11', 'scene_name': 'Sleep'}
KEY = ('1', '11')


@pytest.fixture
async def managers(hass):
    created = []

    def make(config=None, cached=None):
        settings = config or {}
        cloud = SimpleNamespace(
            unique_id='1000-cn-xiaomiio', user_id='1000',
            async_get_manual_scene_homes=AsyncMock(return_value=[dict(HOME)]),
            async_get_manual_scene_home=AsyncMock(return_value=[dict(RECORD)]),
            async_run_manual_scene=AsyncMock(return_value=True),
        )
        entry = SimpleNamespace(
            id=f'scene-entry-{len(created)}', hass=hass, cloud=cloud,
            get_config=lambda key, default=None: settings.get(key, default),
        )
        manager = ManualScenes(entry)
        manager._store = SimpleNamespace(
            async_load=AsyncMock(return_value=cached), async_save=AsyncMock(),
        )
        created.append(manager)
        return manager, cloud

    yield make
    for manager in created:
        await manager.async_close()


async def refresh(manager):
    manager.request_refresh()
    await manager._task


def cache(records=None, account='1000-cn-xiaomiio', owner='1000'):
    return {'account': account, 'homes': [{
        'home_id': '1', 'owner_uid': owner, 'home_name': 'Cached home',
        'scenes': records if records is not None else [dict(RECORD)],
    }]}


async def test_cached_setup_does_not_wait_for_the_cloud(managers):
    manager, cloud = managers(cached=cache())
    await manager.async_start()
    assert manager.get_scene(KEY)['scene_name'] == 'Sleep'
    assert manager.name(KEY) == 'Cached home Sleep'
    cloud.async_get_manual_scene_homes.assert_not_awaited()
    await manager._task
    assert manager.name(KEY) == 'Home Sleep'
    assert manager.route(KEY) == 'cloud'


@pytest.mark.parametrize('cached', [None, [], {}, cache(account='other'),
                                    cache(records=[{'scene_id': True, 'scene_name': 'Bad'}])])
async def test_invalid_cache_does_not_create_a_scene(managers, cached):
    manager, cloud = managers(cached=cached)
    await manager.async_start()
    assert not manager.scenes
    await manager._task
    assert set(manager.scenes) == {KEY}


async def test_disabled_entry_does_not_load_discover_or_execute(managers):
    manager, cloud = managers({'disable_manual_scenes': True}, cache())
    await manager.async_start()
    manager.request_refresh()
    assert not manager.scenes and manager._task is None
    manager._store.async_load.assert_not_awaited()
    cloud.async_get_manual_scene_homes.assert_not_awaited()
    with pytest.raises(HomeAssistantError):
        await manager.async_run(KEY)


async def test_failed_home_keeps_memory_but_confirmed_empty_removes(managers):
    manager, cloud = managers()
    await manager.async_start()
    await manager._task
    manager._store.async_save.side_effect = OSError('synthetic storage failure')
    manager._store.async_load.return_value = cache()
    cloud.async_get_manual_scene_home.side_effect = MiCloudException('temporary')
    await refresh(manager)
    assert KEY in manager.scenes
    cloud.async_get_manual_scene_home.side_effect = None
    cloud.async_get_manual_scene_home.return_value = []
    await refresh(manager)
    assert manager.scenes == {}
    cloud.async_get_manual_scene_home.side_effect = MiCloudException('temporary')
    await refresh(manager)
    assert manager.scenes == {}  # Old disk metadata cannot revive the empty home.
    assert manager._store.async_load.await_count == 1


async def test_bad_record_does_not_turn_a_home_into_a_partial_snapshot(managers):
    manager, cloud = managers()
    await manager.async_start()
    await manager._task
    cloud.async_get_manual_scene_home.return_value = [
        {'scene_id': '12', 'scene_name': 'New'}, {'scene_id': True, 'scene_name': 'Bad'},
    ]
    await refresh(manager)
    assert set(manager.scenes) == {KEY}


async def test_home_snapshot_failure_keeps_memory_and_owner_change_cannot(managers):
    manager, cloud = managers()
    await manager.async_start()
    await manager._task
    cloud.async_get_manual_scene_homes.side_effect = MiCloudException('temporary')
    await refresh(manager)
    assert KEY in manager.scenes
    cloud.async_get_manual_scene_homes.side_effect = None
    cloud.async_get_manual_scene_homes.return_value = [{**HOME, 'uid': '2000'}]
    cloud.async_get_manual_scene_home.side_effect = MiCloudException('temporary')
    await refresh(manager)
    assert manager.scenes == {}


async def test_healthy_home_updates_independently_from_a_failed_home(managers):
    manager, cloud = managers()
    cloud.async_get_manual_scene_homes.return_value = [HOME, {**HOME, 'id': '2'}]
    await manager.async_start()
    await manager._task
    cloud.async_get_manual_scene_home.side_effect = [
        MiCloudException('temporary'), [{'scene_id': '12', 'scene_name': 'New'}],
    ]
    await refresh(manager)
    assert set(manager.scenes) == {KEY, ('2', '12')}


@pytest.mark.parametrize('mode,values,expected', [
    ('include', ['1'], {KEY}), ('include', [1], {KEY}), ('include', [], set()),
    ('exclude', ['1'], set()), ('exclude', [], {KEY}),
])
async def test_entry_home_filter_is_not_a_device_model_filter(managers, mode, values, expected):
    manager, cloud = managers({'filter_home_id': mode, 'home_id_list': values,
                               'filter_model': 'include', 'model_list': []})
    await manager.async_start()
    await manager._task
    assert set(manager.scenes) == expected
    assert cloud.async_get_manual_scene_home.await_count == bool(expected)


async def test_pending_recovery_burst_produces_only_one_follow_up(managers):
    manager, cloud = managers()
    entered, release = asyncio.Event(), asyncio.Event()
    followed_up = asyncio.Event()
    calls = 0

    async def homes():
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
            return [HOME]
        followed_up.set()
        raise MiCloudException('follow-up failed')

    cloud.async_get_manual_scene_homes.side_effect = homes
    await manager.async_start()
    first = manager._task
    await entered.wait()
    for _ in range(20):
        manager.request_refresh()
    release.set()
    await first
    await followed_up.wait()
    assert calls == 2
    assert manager._task is None and manager._timer is not None


async def test_passive_cloud_recovery_notifies_once_and_activation_reads_no_lists(managers):
    manager, cloud = managers()
    await manager.async_start()
    await manager._task
    manager.cloud_status(False)
    assert manager.route(KEY) is None
    with pytest.raises(HomeAssistantError):
        await manager.async_run(KEY)
    with patch.object(manager, 'request_refresh') as request:
        manager.cloud_status(True)
        manager.cloud_status(True)
        request.assert_called_once_with()
    homes_count = cloud.async_get_manual_scene_homes.await_count
    lists_count = cloud.async_get_manual_scene_home.await_count
    await manager.async_run(KEY)
    assert cloud.async_get_manual_scene_homes.await_count == homes_count
    assert cloud.async_get_manual_scene_home.await_count == lists_count
    cloud.async_run_manual_scene.assert_awaited_once()


async def test_unload_cancels_read_and_never_saves_or_reschedules(managers):
    manager, cloud = managers()
    entered = asyncio.Event()

    async def homes():
        entered.set()
        await asyncio.Event().wait()

    cloud.async_get_manual_scene_homes.side_effect = homes
    await manager.async_start()
    await entered.wait()
    task = manager._task
    manager.request_refresh()
    await manager.async_close()
    manager.cloud_status(True)
    manager.request_refresh()
    assert task.cancelled()
    assert manager._task is None and manager._timer is None and not manager._pending
    manager._store.async_save.assert_not_awaited()


async def test_unload_cancels_execution_without_resending(managers):
    manager, cloud = managers()
    await manager.async_start()
    await manager._task
    entered = asyncio.Event()

    async def execute(scene):
        entered.set()
        await asyncio.Event().wait()

    cloud.async_run_manual_scene.side_effect = execute
    task = asyncio.create_task(manager.async_run(KEY))
    await entered.wait()
    with pytest.raises(HomeAssistantError) as exc:
        await manager.async_run(KEY)
    assert exc.value.translation_key == 'scene_busy'
    await manager.async_close()
    assert task.cancelled() and not manager._executions
    assert cloud.async_run_manual_scene.await_count == 1


@pytest.mark.parametrize('result', [False, None])
async def test_failed_execution_is_not_retried(managers, result):
    manager, cloud = managers()
    await manager.async_start()
    await manager._task
    cloud.async_run_manual_scene.return_value = result
    with pytest.raises(HomeAssistantError):
        await manager.async_run(KEY)
    assert cloud.async_run_manual_scene.await_count == 1 and not manager._executions


async def test_owner_is_revoked_before_waiting_for_the_new_home_list(managers):
    manager, cloud = managers()
    await manager.async_start()
    await manager._task
    cloud.async_get_manual_scene_homes.return_value = [{**HOME, 'uid': '2000'}]
    entered, release = asyncio.Event(), asyncio.Event()

    async def records(home):
        entered.set()
        await release.wait()
        return [dict(RECORD)]

    cloud.async_get_manual_scene_home.side_effect = records
    manager.request_refresh()
    task = manager._task
    try:
        await entered.wait()
        assert manager.route(KEY) is None and manager.scenes == {}
        with pytest.raises(HomeAssistantError):
            await manager.async_run(KEY)
        cloud.async_run_manual_scene.assert_not_awaited()
    finally:
        release.set()
        await task
    assert manager.get_scene(KEY)['owner_uid'] == '2000'


async def test_account_change_cannot_reuse_an_existing_snapshot(managers):
    manager, cloud = managers()
    await manager.async_start()
    await manager._task
    cloud.unique_id = '2000-cn-xiaomiio'
    assert manager.route(KEY) is None
    manager.request_refresh()
    assert manager._task is None
    with pytest.raises(HomeAssistantError):
        await manager.async_run(KEY)


async def test_conflicting_cached_home_is_not_chosen_by_order(managers):
    payload = cache()
    payload['homes'].append({**payload['homes'][0], 'owner_uid': '2000'})
    manager, cloud = managers(cached=payload)
    await manager.async_start()
    assert not manager.scenes
    await manager._task
    assert manager.get_scene(KEY)['owner_uid'] == '1000'


async def test_stop_event_closes_owned_tasks_and_timer(managers):
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP
    manager, cloud = managers()
    await manager.async_start()
    await manager._task
    manager.hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await manager.hass.async_block_till_done()
    assert manager._closed and manager._timer is None
    assert manager._unsub_stop is None
