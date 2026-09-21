from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.vacuum import VacuumActivity, VacuumEntityFeature

from custom_components.xiaomi_miot.vacuum import (
    MiotVacuumEntity,
    MiotEntity,
    Segment,
    _parse_room_information,
    _room_clean_config,
    _room_sweep_payload,
)


@pytest.mark.parametrize('has_rooms', [True, False])
def test_room_cleaning_feature_requires_ha_and_device_support(has_rooms):
    service = Mock()
    service.get_property.side_effect = lambda *names: (
        Mock() if has_rooms and 'room_information' in names else None
    )
    service.get_action.side_effect = lambda *names: (
        Mock() if has_rooms and names[0] in (
            'get_room_configs', 'start_vacuum_room_sweep'
        ) else None
    )
    service.spec.get_services.return_value = []
    service.spec.get_service.return_value = None
    service.generate_entity_id.return_value = 'vacuum.test'

    def init(entity, *args, **kwargs):
        entity._supported_features = 0

    with patch.object(MiotEntity, '__init__', init):
        entity = MiotVacuumEntity({}, service)

    clean_area = getattr(VacuumEntityFeature, 'CLEAN_AREA', 0)
    assert bool(entity._supported_features & clean_area) == (
        has_rooms and Segment is not None
    )
    service.generate_entity_id.assert_called_once_with(entity, domain='vacuum')


@pytest.mark.skipif(Segment is None, reason='HA does not support vacuum segments')
def test_parse_room_information():
    result = _parse_room_information(
        '{"rooms":[{"id":3,"name":"Living Room"},{"id":16,"name":"Office"}],"map_uid":10}'
    )

    assert result == [
        Segment(id='3', name='Living Room'),
        Segment(id='16', name='Office'),
    ]


def test_parse_room_information_rejects_invalid_values():
    assert _parse_room_information('') == []
    assert _parse_room_information('{"rooms":null}') == []
    assert _parse_room_information('not-json') == []


def test_room_sweep_payload():
    assert _room_sweep_payload(['3', '16']) == '3,16'


def test_room_clean_config():
    assert _room_clean_config(['3', '16']) == (
        '{"rooms":[3,16],"clean_mode":1,"is_ai_cleaning":false}'
    )


@pytest.fixture
def vacuum():
    entity = object.__new__(MiotVacuumEntity)
    entity._act_start_room_sweep = Mock()
    entity._act_start_room_sweep.in_params.side_effect = lambda values: values
    entity._act_set_room_clean_configs = Mock()
    entity._act_set_room_clean_configs.in_params.side_effect = lambda values: values
    entity.async_call_action = AsyncMock(return_value=SimpleNamespace(is_success=True))
    return entity


async def test_clean_segments_configures_before_start(vacuum):
    await vacuum.async_clean_segments(['3', '16'])
    calls = vacuum.async_call_action.await_args_list
    assert len(calls) == 2
    assert calls[0].args == (
        vacuum._act_set_room_clean_configs,
        ['{"rooms":[3,16],"clean_mode":1,"is_ai_cleaning":false}'],
    )
    assert calls[1].args == (vacuum._act_start_room_sweep, ['3,16'])
    assert all(call.kwargs == {'force_params': True} for call in calls)


async def test_clean_segments_without_config_action(vacuum):
    vacuum._act_set_room_clean_configs = None
    await vacuum.async_clean_segments(['3'])
    vacuum.async_call_action.assert_awaited_once_with(
        vacuum._act_start_room_sweep, ['3'], force_params=True
    )


async def test_clean_segments_empty_selection(vacuum):
    await vacuum.async_clean_segments([])
    vacuum.async_call_action.assert_not_awaited()


async def test_clean_segments_config_failure_does_not_start(vacuum):
    vacuum.async_call_action.return_value = SimpleNamespace(is_success=False)
    with pytest.raises(HomeAssistantError, match='configure'):
        await vacuum.async_clean_segments(['3'])
    assert vacuum.async_call_action.await_count == 1
    assert vacuum.async_call_action.await_args.args[0] is vacuum._act_set_room_clean_configs


async def test_clean_segments_reports_start_failure(vacuum):
    vacuum.async_call_action.side_effect = [
        SimpleNamespace(is_success=True), SimpleNamespace(is_success=False)
    ]
    with pytest.raises(HomeAssistantError, match='start'):
        await vacuum.async_clean_segments(['3'])


@pytest.mark.skipif(Segment is None, reason='HA does not support vacuum segments')
async def test_get_segments_refreshes_rooms(vacuum):
    vacuum._prop_room_information = SimpleNamespace(
        service=SimpleNamespace(iid=2), iid=10, full_name='vacuum.room_information'
    )
    vacuum._act_get_room_configs = Mock()
    vacuum._act_get_room_configs.in_properties.return_value = []
    vacuum._state_attrs = {}
    vacuum.device = SimpleNamespace(async_get_properties=AsyncMock(return_value={
        'vacuum.room_information': '{"rooms":[{"id":3,"name":"Kitchen"}]}'
    }))
    assert await vacuum.async_get_segments() == [Segment(id='3', name='Kitchen')]
    vacuum.async_call_action.assert_awaited_once_with(
        vacuum._act_get_room_configs, [], force_params=True
    )
    vacuum.device.async_get_properties.assert_awaited_once_with(
        [{'siid': 2, 'piid': 10}], update_entity=True, throw=True
    )
    assert vacuum._state_attrs['room_mapping'] == [['3', '3', 'Kitchen']]


@pytest.mark.skipif(Segment is None, reason='HA does not support vacuum segments')
async def test_get_segments_reports_refresh_failure(vacuum):
    vacuum._prop_room_information = Mock()
    vacuum._act_get_room_configs = Mock()
    vacuum._act_get_room_configs.in_properties.return_value = []
    vacuum.async_call_action.return_value = SimpleNamespace(is_success=False)
    with pytest.raises(HomeAssistantError, match='refresh'):
        await vacuum.async_get_segments()


async def test_update_current_room_from_cloud_map():
    entity = object.__new__(MiotVacuumEntity)
    entity.device = SimpleNamespace(
        cloud=SimpleNamespace(async_get_interim_file=AsyncMock(return_value=b'map')),
        info=SimpleNamespace(model='xiaomi.vacuum.d102gl'),
    )
    entity._prop_map_obj_name = SimpleNamespace(
        from_device=Mock(return_value='user/device/0')
    )
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
