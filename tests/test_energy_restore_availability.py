"""Energy restore availability with real HA stored states and platform updates."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import State
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.utils import local_zone, power_cost_period
from custom_components.xiaomi_miot.sensor import SensorEntity


@pytest.mark.parametrize('key', ['power_cost_today', 'power_cost_month'])
@pytest.mark.parametrize('online', [False, True])
@pytest.mark.parametrize('value', [0, 1.25])
async def test_current_period_restore_is_visible_before_new_cloud_read(hass, make_device, freezer, key, online, value):
    freezer.move_to('2026-11-14T12:00:00+00:00')
    spec = MiotSpec(hass, {'type': 'urn:miot-spec-v2:device:outlet:0000A002:test-energy:1', 'services': []})
    device = make_device(spec, model='test.energy', customizes={
        'sensor_attributes': key, 'unit_of_measurement': 'kWh',
        'device_class': 'energy', 'state_class': 'total_increasing', 'value_ratio': 0.01,
    })
    device.available = online
    entity = SensorEntity(device, device.find_converter(f'sensor.{key}'))
    now = datetime.now(local_zone(hass))
    mock_restore_cache_with_extra_data(hass, [(State(entity.entity_id, str(value), last_changed=now), {
        'native_value': value, 'native_unit_of_measurement': 'kWh',
        'power_cost_period': power_cost_period(entity.attr, now), 'raw_value': value * 100, 'value_ratio': 0.01,
    })])
    assert await async_setup_component(hass, 'sensor', {})
    component = hass.data['sensor']
    await component.async_add_entities([entity])
    try:
        assert entity.native_value == value
        assert device.props[key] == value * 100
        state = hass.states.get(entity.entity_id).state
        if online:
            assert float(state) == value
        else:
            assert state == 'unavailable'
        # A missing cloud observation must not erase the accepted restoration.
        device.cloud = SimpleNamespace(async_request_api=AsyncMock(return_value=None))
        assert await device.update_cloud_statistics([{
            'key': '11.1', 'day': 32, 'limit': 31,
            'template': 'micloud_statistics_power_cost',
        }]) == {}
        assert entity.native_value == value
        assert hass.states.get(entity.entity_id).state == state
        # Reachability may recover before this particular statistic is returned.
        device.available = True
        device.dispatch({})
        await hass.async_block_till_done()
        assert float(hass.states.get(entity.entity_id).state) == value
        device.available = False
        device.dispatch({})
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state == 'unavailable'
    finally:
        await component.async_remove_entity(entity.entity_id)


@pytest.mark.parametrize('key', ['power_cost_today', 'power_cost_month'])
@pytest.mark.parametrize('restore_kind', ['absent', 'previous_period', 'invalid_value', 'invalid_unit'])
async def test_unusable_restore_is_not_made_available(hass, make_device, freezer, key, restore_kind):
    freezer.move_to('2026-11-14T12:00:00+00:00')
    spec = MiotSpec(hass, {'type': 'urn:miot-spec-v2:device:outlet:0000A002:test-energy:1', 'services': []})
    device = make_device(spec, model='test.energy', customizes={
        'sensor_attributes': key, 'unit_of_measurement': 'kWh',
        'device_class': 'energy', 'state_class': 'total_increasing', 'value_ratio': 0.01,
    })
    entity = SensorEntity(device, device.find_converter(f'sensor.{key}'))
    now = datetime.now(local_zone(hass))
    restored_at = now - timedelta(days=32) if restore_kind == 'previous_period' else now
    extra = {
        'native_value': 'NaN' if restore_kind == 'invalid_value' else 1.25,
        'native_unit_of_measurement': 'invalid' if restore_kind == 'invalid_unit' else 'kWh',
        'power_cost_period': power_cost_period(entity.attr, restored_at),
    }
    cache = [] if restore_kind == 'absent' else [(State(
        entity.entity_id, '1.25', last_changed=restored_at,
    ), extra)]
    mock_restore_cache_with_extra_data(hass, cache)
    assert await async_setup_component(hass, 'sensor', {})
    component = hass.data['sensor']
    await component.async_add_entities([entity])
    try:
        device.dispatch({})
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state == 'unavailable'
        assert entity.native_value is None
        assert key not in device.props
        # A real observation still recovers the same entity after a bad restore.
        device.props[key] = 150
        device.dispatch(device.decode_attrs({key: 150}))
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state == '1.5'
    finally:
        await component.async_remove_entity(entity.entity_id)
