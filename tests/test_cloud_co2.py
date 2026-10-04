"""Timestamped cloud CO2 observations, using the existing entity and coordinator."""
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import State
from homeassistant.setup import async_setup_component
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from custom_components.xiaomi_miot.core.utils import latest_cloud_property
from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException
from custom_components.xiaomi_miot.sensor import SensorEntity


def record(value=1218, timestamp=1000):
    return {'time': timestamp, 'value': json.dumps([value])}


@pytest.mark.parametrize('value', [None, True, '', '1218', 1218.5, 1218.0, float('nan'), float('inf'), -1, 399, 5001])
def test_invalid_values(value):
    assert latest_cloud_property([record(value)], 1000, [400, 5000, 100]) is None


@pytest.mark.parametrize('bad', [None, {}, [], {'time': 1000, 'value': ''},
                                     {'time': 1000, 'value': '[1, 2]'},
                                     {'time': 1000, 'value': '{}'},
                                     record(timestamp=True), record(timestamp='1000'),
                                     record(timestamp=1061), record(timestamp=0)])
def test_invalid_records(bad):
    assert latest_cloud_property([bad], 1000, [400, 5000, 100]) is None


def test_order_duplicates_conflicts_and_future_boundary():
    records = [record(1218, 1000), record(1177, 900), record(1218, 1000)]
    expected = {'value': 1218, 'timestamp': 1000}
    assert latest_cloud_property(records, 1000, [400, 5000, 100]) == expected
    assert latest_cloud_property(records[::-1], 1000, [400, 5000, 100]) == expected
    records.append(record(1200, 1000))
    assert latest_cloud_property(records, 1000, [400, 5000, 100]) == {'value': 1177, 'timestamp': 900}
    assert latest_cloud_property([record(timestamp=1060)], 1000, [400, 5000, 100])['timestamp'] == 1060


@pytest.fixture
def co2_device(make_device, load_miot_spec, freezer):
    freezer.move_to('2026-09-30T12:00:00+00:00')
    device = make_device(load_miot_spec('miaomiaoce.airm.co2.json'), model='miaomiaoce.airm.co2')
    device.available = True
    device.cloud = Mock()
    device.cloud.async_get_user_device_data = AsyncMock()
    return device


async def update(device, records=None, code=0):
    device.cloud.async_get_user_device_data.return_value = {'code': code, 'result': records or []}
    await device.update_miio_cloud_records()


def make_sensor(device):
    conv = next(c for c in device.converters if c.attr == 'environment.co2_density' and c.domain == 'sensor')
    return SensorEntity(device, conv)


async def test_update_decrease_and_request_contract(co2_device):
    device = co2_device
    sensor = make_sensor(device)
    timestamp = int(dt.now().timestamp())
    for value, offset in [(1218, -2), (1101, -1), (1101, 0)]:
        await update(device, [record(value, timestamp + offset)])
        assert sensor.native_value == value
        assert sensor.available
    call = device.cloud.async_get_user_device_data.call_args
    assert call.args == ('test-device', '3.1029', 'prop')
    assert call.kwargs == {'raw': True, 'limit': 5, 'time_start': timestamp - 86400 * 32}
    assert sensor.get_state()['source_timestamp'] == timestamp


async def test_duplicates_older_and_same_time_conflict(co2_device):
    device = co2_device
    now = int(dt.now().timestamp())
    await update(device, [record(timestamp=now)])
    device.dispatch = Mock()
    for records in ([record(timestamp=now)], [record(1101, now - 1)], [record(1101, now)]):
        await update(device, records)
    device.dispatch.assert_not_called()
    assert device.props['environment.co2_density'] == 1218


@pytest.mark.parametrize('response', [None, {}, {'code': 1, 'result': [record()]}, {'code': False, 'result': [record()]},
                                     {'code': 0, 'result': {}}, {'code': 0, 'result': []}])
async def test_failure_keeps_value_until_stale(co2_device, freezer, response):
    device = co2_device
    sensor = make_sensor(device)
    timestamp = int(dt.now().timestamp())
    await update(device, [record(timestamp=timestamp)])
    device.cloud.async_get_user_device_data.return_value = response
    freezer.tick(900)
    await device.update_miio_cloud_records()
    assert sensor.available
    freezer.tick(1)
    await device.update_miio_cloud_records()
    assert sensor.native_value == 1218
    assert not sensor.available
    assert device.available
    await update(device, [record(999, timestamp + 901)])
    assert sensor.available and sensor.native_value == 999


async def test_cloud_exception_and_invalid_latest_are_isolated(co2_device):
    device = co2_device
    sensor = make_sensor(device)
    timestamp = int(dt.now().timestamp())
    await update(device, [record(None, timestamp), record(1218, timestamp - 1)])
    device.cloud.async_get_user_device_data.side_effect = MiCloudException('offline')
    await device.update_miio_cloud_records()
    assert sensor.available and sensor.native_value == 1218


@pytest.mark.parametrize('age,with_time,expected', [(0, True, '1218'), (900, True, '1218'),
                                                  (901, True, 'unavailable'), (0, False, 'unavailable')])
async def test_actual_platform_identity_restore_freshness_unload(hass, co2_device, freezer, age, with_time, expected):
    device = co2_device
    sensor = make_sensor(device)
    identity = (sensor.entity_id, sensor.unique_id)
    timestamp = int(dt.now().timestamp()) - age
    extra = {sensor.attr: 1218, 'native_unit_of_measurement': 'ppm'}
    if with_time:
        extra['source_timestamp'] = timestamp
    mock_restore_cache_with_extra_data(hass, [(State(sensor.entity_id, '1218'), extra)])
    assert await async_setup_component(hass, 'sensor', {})
    component = hass.data['sensor']
    await component.async_add_entities([sensor])
    await hass.async_block_till_done()
    state = hass.states.get(sensor.entity_id)
    assert state.state == expected
    assert state.attributes['unit_of_measurement'] == 'ppm'
    assert state.attributes['device_class'] == 'carbon_dioxide'
    assert state.attributes['state_class'] == 'measurement'
    freezer.tick(1)
    await update(device, [record(1101, int(dt.now().timestamp()))])
    await hass.async_block_till_done()
    assert hass.states.get(sensor.entity_id).state == '1101'
    assert (sensor.entity_id, sensor.unique_id) == identity
    freezer.tick(901)
    await update(device)
    await hass.async_block_till_done()
    assert hass.states.get(sensor.entity_id).state == 'unavailable'
    await component.async_remove_entity(sensor.entity_id)
    assert sensor.on_device_update not in device.listeners


async def test_poll_mapping_coordinator_interval_and_other_sensors(co2_device):
    device = co2_device
    mapping = device.spec.services_mapping(exclude_properties=device._exclude_miot_properties)
    assert 'environment.co2_density' not in mapping
    assert {'environment.temperature', 'environment.relative_humidity', 'battery_level'} <= mapping.keys()
    assert device.custom_config_integer('miio_cloud_records_interval') == 60
    temperature = SensorEntity(device, next(c for c in device.converters if c.attr == 'environment.temperature' and c.domain == 'sensor'))
    device.dispatch(device.decode_attrs({'environment.temperature': 24}))
    assert temperature.available and temperature.native_value == 24
    await update(device)
    assert device.available and temperature.available


async def test_unmapped_cloud_records_keep_existing_behavior(co2_device):
    device = co2_device
    device.cloud.async_get_user_device_data.return_value = [{'value': '[7]'}]
    assert await device.update_miio_cloud_records(['prop.other:1']) == {'prop.other': ['[7]']}
    assert 'raw' not in device.cloud.async_get_user_device_data.call_args.kwargs


async def test_initial_observation_wins_over_old_restore(hass, co2_device):
    device = co2_device
    sensor = make_sensor(device)
    timestamp = int(dt.now().timestamp())
    await update(device, [record(1101, timestamp)])
    sensor.async_get_last_extra_data = AsyncMock(return_value=None)
    await sensor._restore_cloud_property()
    assert sensor.native_value == 1101
    assert sensor.get_state()['source_timestamp'] == timestamp


async def test_record_coordinator_uses_existing_setup_and_unload(co2_device):
    device = co2_device
    from custom_components.xiaomi_miot.core.coordinator import DataCoordinator
    with patch.object(DataCoordinator, 'async_setup', new=AsyncMock()):
        await device.init_coordinators()
    records = [c for c in device.coordinators if c.update_method == device.update_miio_cloud_records]
    assert len(records) == 1
    assert records[0].update_interval.total_seconds() == 60
    for coordinator in device.coordinators:
        await coordinator.async_shutdown()


async def test_failure_does_not_interrupt_other_record_commands(co2_device):
    device = co2_device
    device.cloud.async_get_user_device_data.side_effect = [MiCloudException('offline'), [{'value': '[7]'}]]
    assert await device.update_miio_cloud_records(['prop.3.1029:5', 'prop.other:1']) == {'prop.other': ['[7]']}


def test_other_models_keep_standard_co2_polling(make_device, load_miot_spec):
    device = make_device(load_miot_spec('miaomiaoce.airm.co2.json'), model='test.other.air_monitor')
    assert 'environment.co2_density' in device.spec.services_mapping()
    assert device.miio_cloud_records == []
    sensor = make_sensor(device)
    assert sensor._cloud_record_max_age is None


async def test_device_recovery_republishes_fresh_duplicate(co2_device):
    device = co2_device
    sensor = make_sensor(device)
    records = [record(timestamp=int(dt.now().timestamp()))]
    await update(device, records)
    device.available = False
    await update(device, records)
    assert not sensor.available
    device.dispatch = Mock(wraps=device.dispatch)
    device.available = True
    await update(device, records)
    assert sensor.available
    device.dispatch.assert_called_once()
