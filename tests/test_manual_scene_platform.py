"""Real HA Button platform and registry lifecycle, with synthetic transports."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.helpers import entity_registry as er, device_registry as dr
from homeassistant.config_entries import ConfigEntryState

import custom_components.xiaomi_miot as integration
from custom_components.xiaomi_miot import button as platform_module
from custom_components.xiaomi_miot.core.hass_entry import HassEntry
from custom_components.xiaomi_miot.core.xiaomi_cloud import CloudSid

DOMAIN = integration.DOMAIN
KEY = ('1', '11')


@pytest.fixture
async def scene_platform(hass):
    entries = []
    clouds = {}

    async def setup_cloud(hass, config):
        HassEntry.init(hass, config).clouds[CloudSid.XIAOMIIO] = clouds[config.entry_id]
        return True

    def prepare(*, cached=False, uid='1000', disabled=False):
        config = MockConfigEntry(domain=DOMAIN, data={
            'username': f'demo-{uid}', 'disable_manual_scenes': disabled,
        })
        config.add_to_hass(hass)
        cloud = SimpleNamespace(
            unique_id=f'{uid}-cn-xiaomiio', user_id=uid,
            async_get_manual_scene_homes=AsyncMock(return_value=[{
                'id': '1', 'uid': uid, 'name': 'Home',
            }]),
            async_get_manual_scene_home=AsyncMock(return_value=[{
                'scene_id': '11', 'scene_name': 'Sleep',
            }]),
            async_run_manual_scene=AsyncMock(return_value=True),
        )
        entry = HassEntry.init(hass, config)
        clouds[config.entry_id] = cloud
        entry.clouds[CloudSid.XIAOMIIO] = cloud
        manager = entry.get_manual_scenes()
        payload = {'account': cloud.unique_id, 'homes': [{
            'home_id': '1', 'owner_uid': uid, 'home_name': 'Home',
            'scenes': [{'scene_id': '11', 'scene_name': 'Sleep'}],
        }]} if cached else None
        manager._store = SimpleNamespace(async_load=AsyncMock(return_value=payload),
                                         async_save=AsyncMock())
        entries.append((config, manager))
        return config, manager, cloud

    with (
        patch.object(integration, 'SUPPORTED_DOMAINS', ['button']),
        patch('custom_components.xiaomi_miot.core.hass_entry.SUPPORTED_DOMAINS', ['button']),
        patch.object(integration, 'async_setup_xiaomi_cloud', setup_cloud),
        patch.object(platform_module, 'async_setup_config_entry', AsyncMock()),
    ):
        yield prepare
        for config, manager in entries:
            await hass.config_entries.async_unload(config.entry_id)
            await manager.async_close()
            HassEntry.ALL.pop(config.entry_id, None)


def scene_entities(hass):
    return [entity for entity in er.async_get(hass).entities.values()
            if entity.platform == DOMAIN and '-manual-scene-' in entity.unique_id]


async def ready(hass, config, manager):
    if config.state == ConfigEntryState.NOT_LOADED:
        assert await hass.config_entries.async_setup(config.entry_id)
    else:
        assert config.state == ConfigEntryState.LOADED
    if manager._task:
        await manager._task
    await hass.async_block_till_done()


async def refresh(hass, manager):
    manager.request_refresh()
    await manager._task
    await hass.async_block_till_done()


async def test_real_button_service_keeps_registered_id_and_user_overrides(hass, scene_platform):
    config, manager, cloud = scene_platform()
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        'button', DOMAIN, f'{cloud.unique_id}-manual-scene-1-11',
        config_entry=config, suggested_object_id='old_scene',
    )
    registry.async_update_entity(old.entity_id, new_entity_id='button.keep_this_id',
                                 name='User scene', icon='mdi:star')
    await ready(hass, config, manager)
    record = scene_entities(hass)[0]
    assert record.id == old.id and record.entity_id == 'button.keep_this_id'
    device = dr.async_get(hass).async_get(record.device_id)
    assert device.entry_type == dr.DeviceEntryType.SERVICE
    assert device.identifiers == {(DOMAIN, f'{cloud.unique_id}-manual-scenes')}
    state = hass.states.get(record.entity_id)
    assert state.attributes['icon'] == 'mdi:star'
    assert 'User scene' in state.attributes['friendly_name']
    await hass.services.async_call('button', 'press', {'entity_id': record.entity_id}, blocking=True)
    cloud.async_run_manual_scene.assert_awaited_once()
    cloud.async_get_manual_scene_home.return_value = [{'scene_id': '11', 'scene_name': 'Renamed'}]
    await refresh(hass, manager)
    updated = registry.async_get(record.entity_id)
    assert updated.id == old.id and updated.name == 'User scene' and updated.icon == 'mdi:star'
    assert updated.original_name == 'Home Renamed'
    assert hass.states.get(record.entity_id).attributes['icon'] == 'mdi:star'


async def test_cloud_discovery_is_background_and_cache_is_available_immediately(hass, scene_platform):
    config, manager, cloud = scene_platform(cached=True)
    entered, release = asyncio.Event(), asyncio.Event()

    async def homes():
        entered.set()
        await release.wait()
        return [{'id': '1', 'uid': '1000', 'name': 'Home'}]

    cloud.async_get_manual_scene_homes.side_effect = homes
    assert await hass.config_entries.async_setup(config.entry_id)
    await entered.wait()
    await hass.async_block_till_done()
    assert len(scene_entities(hass)) == 1
    assert hass.states.get(scene_entities(hass)[0].entity_id) is not None
    release.set()
    await manager._task


async def test_confirmed_empty_removes_active_buttons_without_deleting_registry(hass, scene_platform):
    config, manager, cloud = scene_platform()
    await ready(hass, config, manager)
    entity = scene_entities(hass)[0]
    cloud.async_get_manual_scene_home.return_value = []
    await refresh(hass, manager)
    assert hass.data['button'].get_entity(entity.entity_id) is None
    assert er.async_get(hass).async_get(entity.entity_id).id == entity.id
    cloud.async_get_manual_scene_home.return_value = [{'scene_id': '11', 'scene_name': 'Back'}]
    await refresh(hass, manager)
    assert len(scene_entities(hass)) == 1
    assert scene_entities(hass)[0].id == entity.id
    assert hass.states.get(entity.entity_id) is not None
    await hass.config_entries.async_unload(config.entry_id)
    assert manager._closed and manager._timer is None and manager._task is None
    assert hass.data['button'].get_entity(entity.entity_id) is None


@pytest.mark.parametrize('hook', ['async_added_to_hass', 'async_prepare_to_add_to_hass'])
async def test_metadata_deleted_during_real_entity_addition_leaves_no_orphan(hass, scene_platform, hook):
    if not hasattr(platform_module.ManualSceneButton, hook):
        pytest.skip('This Home Assistant version has no entity preparation hook')
    config, manager, cloud = scene_platform()
    adding, release = asyncio.Event(), asyncio.Event()
    original = getattr(platform_module.ManualSceneButton, hook)

    async def delayed(entity):
        adding.set()
        await release.wait()
        await original(entity)

    with patch.object(platform_module.ManualSceneButton, hook, delayed):
        setup = asyncio.create_task(hass.config_entries.async_setup(config.entry_id))
        await adding.wait()
        cloud.async_get_manual_scene_home.return_value = []
        manager.request_refresh()
        await manager._task
        release.set()
        assert await setup
        await hass.async_block_till_done()
    assert manager.scenes == {}
    assert not [entity for entity in hass.data['button'].entities
                if isinstance(entity, platform_module.ManualSceneButton)]


async def test_real_reload_and_option_toggle_keep_entity_identity(hass, scene_platform):
    config, manager, cloud = scene_platform()
    await ready(hass, config, manager)
    registry = er.async_get(hass)
    record = scene_entities(hass)[0]
    registry.async_update_entity(record.entity_id, name='Keep name', icon='mdi:star')
    hass.config_entries.async_update_entry(config, options={'disable_manual_scenes': True})
    await hass.async_block_till_done()
    assert manager._closed and manager._task is None and manager._timer is None
    assert hass.data['button'].get_entity(record.entity_id) is None
    assert registry.async_get(record.entity_id).id == record.id

    hass.config_entries.async_update_entry(config, options={'disable_manual_scenes': False})
    await hass.async_block_till_done()
    new_manager = HassEntry.ALL[config.entry_id].get_manual_scenes()
    assert new_manager is not manager
    await ready(hass, config, new_manager)
    new_record = scene_entities(hass)[0]
    assert new_record.id == record.id and new_record.entity_id == record.entity_id
    assert new_record.name == 'Keep name' and new_record.icon == 'mdi:star'
    assert hass.data['button'].get_entity(record.entity_id) is not None


async def test_new_entity_ids_disambiguate_accounts_and_keep_home_information(hass, scene_platform):
    first = scene_platform(uid='1000')
    second = scene_platform(uid='2000')
    await ready(hass, first[0], first[1])
    await ready(hass, second[0], second[1])
    entities = scene_entities(hass)
    assert len(entities) == 2 and len({entity.entity_id for entity in entities}) == 2
    assert all('manual_controls_home_11' in entity.entity_id for entity in entities)
    assert len({entity.device_id for entity in entities}) == 2


async def test_disabled_option_does_not_create_manual_scene_entities(hass, scene_platform):
    config, manager, cloud = scene_platform(cached=True, disabled=True)
    await ready(hass, config, manager)
    assert scene_entities(hass) == []
    cloud.async_get_manual_scene_homes.assert_not_awaited()
    manager._store.async_load.assert_not_awaited()


async def test_scene_service_is_not_a_physical_device_deletion(hass, scene_platform):
    config, manager, cloud = scene_platform()
    await ready(hass, config, manager)
    record = scene_entities(hass)[0]
    registry = dr.async_get(hass)
    device = registry.async_get(record.device_id)
    assert await integration.async_remove_config_entry_device(hass, config, device) is False
    registry.async_update_device(device.id, name_by_user='delete')
    await hass.async_block_till_done()
    assert registry.async_get(device.id) is not None
    assert hass.data['button'].get_entity(record.entity_id) is not None
