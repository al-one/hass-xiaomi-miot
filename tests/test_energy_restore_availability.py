"""Restore visibility with a real stored state and extra data, without cloud access."""
import pytest
from datetime import datetime
from homeassistant.core import State
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.utils import local_zone, power_cost_period
from custom_components.xiaomi_miot.sensor import SensorEntity


@pytest.mark.parametrize('key', ['power_cost_today', 'power_cost_month'])
@pytest.mark.parametrize('online', [False, True])
@pytest.mark.parametrize('value', [0, 1.25])
async def test_current_period_restore_is_visible_before_new_cloud_read(hass, make_device, key, online, value):
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
    finally:
        await component.async_remove_entity(entity.entity_id)
