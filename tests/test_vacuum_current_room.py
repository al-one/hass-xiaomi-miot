import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

from homeassistant.components.vacuum import VacuumActivity

from custom_components.xiaomi_miot.vacuum import MiotEntity, MiotVacuumEntity


async def test_update_current_room_from_cloud_map():
    entity = object.__new__(MiotVacuumEntity)
    entity.device = SimpleNamespace(
        cloud=SimpleNamespace(async_get_interim_file=AsyncMock(return_value=b'map')),
        info=SimpleNamespace(model='xiaomi.vacuum.d102gl'),
    )
    entity._prop_map_obj_name = SimpleNamespace(
        from_device=Mock(return_value='user/device/0')
    )
    entity._current_room_attrs = {}
    entity._current_room_updated_at = None
    entity._attr_activity = VacuumActivity.CLEANING
    entity._state_attrs = {}

    room = {'id': 3, 'name': 'Living Room', 'x': 244, 'y': -19, 'yaw': 7853}
    with (
        patch.object(
            MiotVacuumEntity, 'miot_did', new_callable=PropertyMock,
            return_value='1234567890',
        ),
        patch(
            'custom_components.xiaomi_miot.vacuum.decrypt_xiaomi_vacuum_map',
            return_value={'map': 'data'},
        ) as decrypt,
        patch(
            'custom_components.xiaomi_miot.vacuum.vacuum_room_from_map',
            return_value=room,
        ),
    ):
        await entity._async_update_current_room()

    entity.device.cloud.async_get_interim_file.assert_awaited_once_with(
        'user/device/0'
    )
    decrypt.assert_called_once_with(
        b'map', 'xiaomi.vacuum.d102gl', '1234567890'
    )
    assert entity._state_attrs == {
        'current_room': 'Living Room',
        'current_room_id': 3,
        'current_position': {'x': 244, 'y': -19, 'yaw': 7853},
    }



async def test_update_current_room_skips_incompatible_map_format():
    cloud = SimpleNamespace(async_get_interim_file=AsyncMock())
    entity = object.__new__(MiotVacuumEntity)
    entity.device = SimpleNamespace(
        cloud=cloud,
        info=SimpleNamespace(model='roborock.vacuum.s5'),
    )
    entity._prop_map_obj_name = SimpleNamespace(from_device=Mock())
    entity._current_room_attrs = {}
    entity._current_room_updated_at = None
    entity._attr_activity = VacuumActivity.CLEANING
    entity._state_attrs = {}

    await entity._async_update_current_room()

    entity._prop_map_obj_name.from_device.assert_not_called()
    cloud.async_get_interim_file.assert_not_awaited()



async def test_update_current_room_clears_location_when_not_cleaning():
    cloud = SimpleNamespace(async_get_interim_file=AsyncMock())
    entity = object.__new__(MiotVacuumEntity)
    entity.device = SimpleNamespace(
        cloud=cloud,
        info=SimpleNamespace(model='xiaomi.vacuum.d102gl'),
    )
    entity._prop_map_obj_name = SimpleNamespace(from_device=Mock())
    entity._attr_activity = VacuumActivity.DOCKED
    entity._state_attrs = {
        'current_room': 'Living Room',
        'current_room_id': 3,
        'current_position': {'x': 244, 'y': -19},
        'status': 'Charging',
    }

    await entity._async_update_current_room()

    assert entity._state_attrs == {'status': 'Charging'}
    entity._prop_map_obj_name.from_device.assert_not_called()
    cloud.async_get_interim_file.assert_not_awaited()



async def test_current_room_cache_survives_coordinator_attribute_replacement():
    entity = object.__new__(MiotVacuumEntity)
    entity.device = SimpleNamespace(
        cloud=SimpleNamespace(async_get_interim_file=AsyncMock()),
        info=SimpleNamespace(model='xiaomi.vacuum.d102gl'),
    )
    entity._prop_map_obj_name = Mock()
    entity._attr_activity = VacuumActivity.CLEANING
    entity._current_room_attrs = {'current_room': 'Kitchen', 'current_room_id': 3}
    entity._current_room_updated_at = 100
    entity._state_attrs = {'vacuum.status': 4}
    with patch('custom_components.xiaomi_miot.vacuum.monotonic', return_value=110):
        await entity._async_update_current_room()
    assert entity._state_attrs['current_room'] == 'Kitchen'
    entity.device.cloud.async_get_interim_file.assert_not_awaited()
    entity._attr_activity = VacuumActivity.DOCKED
    await entity._async_update_current_room()
    assert 'current_room' not in entity._state_attrs
    assert entity._current_room_attrs == {}
    assert entity._current_room_updated_at is None



async def test_coordinator_update_refreshes_activity_and_keeps_device_props_clean():
    entity = object.__new__(MiotVacuumEntity)
    props = {'vacuum.status': 2}
    entity._available = True
    entity._prop_status = Mock()
    entity._prop_status.from_device.return_value = 2
    entity._prop_status.list_search.side_effect = lambda *names: [2] if 'Charging' in names else []
    entity._current_room_lock = asyncio.Lock()
    entity._async_update_current_room = AsyncMock()
    entity.device = SimpleNamespace(props=props)

    async def update(_entity):
        _entity._state_attrs = props

    with patch.object(MiotEntity, 'async_update_from_device', update):
        result = await entity.async_update_from_device()
    assert entity.activity == VacuumActivity.DOCKED
    assert result == props
    assert result is not props
    entity._async_update_current_room.assert_awaited_once()
