"""Native-unit restoration and the device's raw cloud baseline."""

from datetime import datetime, timedelta
from types import SimpleNamespace, MethodType
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import State
from homeassistant.helpers.restore_state import RestoredExtraData

from custom_components.xiaomi_miot.core.converters import BaseConv
from custom_components.xiaomi_miot.core.device import Device, DeviceInfo
from custom_components.xiaomi_miot.core.hass_entity import XEntity
from custom_components.xiaomi_miot.core.utils import local_zone, power_cost_period, parse_power_cost_records
from custom_components.xiaomi_miot.core.templates import template
from homeassistant.util import dt as dt_util
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.sensor import SensorEntity


@pytest.fixture(autouse=True)
def fixed_energy_time(freezer):
    """Keep relative day/month records independent of the execution date."""
    freezer.move_to('2026-09-29T12:00:00+00:00')


def make_sensor(hass, key, ratio):
    sensor = SensorEntity.__new__(SensorEntity)
    sensor.hass = hass
    sensor.conv = BaseConv(key, 'sensor')
    sensor.attr = sensor.conv.full_name
    sensor._attr_native_unit_of_measurement = 'kWh'
    sensor._attr_native_value = None
    sensor.custom_value_ratio = ratio
    # The entity is deliberately not added to a real platform in this unit
    # test; execute its registered cleanup to avoid leaking the midnight timer.
    sensor.async_on_remove = Mock(side_effect=lambda remove: remove())
    device = SimpleNamespace(props={}, data={}, log=Mock())
    device._filter_power_cost_statistics = MethodType(Device._filter_power_cost_statistics, device)
    sensor.device = device
    return sensor


@pytest.mark.parametrize('key', ['power_cost_today', 'power_cost_month_2'])
@pytest.mark.parametrize('ratio', [0, 0.01, 0.001])
@pytest.mark.parametrize('extra_kind', ['none', 'legacy', 'native'])
async def test_restore_display_wh_as_native_kwh_and_raw_baseline(hass, key, ratio, extra_kind):
    sensor = make_sensor(hass, key, ratio)
    now = datetime.now(local_zone(hass))
    period = power_cost_period(sensor.attr, now)
    extra = None
    if extra_kind == 'legacy':
        extra = RestoredExtraData({sensor.attr: 17.5})
    elif extra_kind == 'native':
        extra = RestoredExtraData({
            'native_value': 17.5, 'native_unit_of_measurement': 'kWh',
            'power_cost_period': period,
        })
    sensor.async_get_last_extra_data = AsyncMock(return_value=extra)
    sensor.async_get_last_state = AsyncMock(return_value=State(
        'sensor.test_energy', '17500', {'unit_of_measurement': 'Wh'},
        last_changed=now,
    ))
    with patch.object(XEntity, 'async_added_to_hass', new=AsyncMock()):
        await sensor.async_added_to_hass()
    assert sensor.native_value == pytest.approx(17.5)
    assert sensor.device.props[key] == pytest.approx(17.5 / (ratio or 1))
    assert sensor.device._filter_power_cost_statistics({key: 0}, now) == {}
    assert sensor.get_state()['native_unit_of_measurement'] == 'kWh'
    assert sensor.attr not in sensor.get_state()


async def test_restore_previous_day_does_not_block_new_day(hass):
    sensor = make_sensor(hass, 'power_cost_today', 0.01)
    now = datetime.now(local_zone(hass))
    sensor.async_get_last_extra_data = AsyncMock(return_value=None)
    sensor.async_get_last_state = AsyncMock(return_value=State(
        'sensor.test_energy', '17.5', {'unit_of_measurement': 'kWh'},
        last_changed=now - timedelta(days=1),
    ))
    with patch.object(XEntity, 'async_added_to_hass', new=AsyncMock()):
        await sensor.async_added_to_hass()
    assert sensor.native_value is None
    assert sensor.device._filter_power_cost_statistics({'power_cost_today': 15}, now) == {'power_cost_today': 15}


@pytest.mark.parametrize('value', [None, '', 'bad', float('nan'), float('inf'), -1, True])
def test_invalid_cloud_statistics_never_replace_old_value(value):
    device = SimpleNamespace(props={'power_cost_today': 17.5}, data={}, log=Mock())
    now = datetime.now().astimezone()
    assert Device._filter_power_cost_statistics(device, {'power_cost_today': value, 'unrelated': 1}, now) == {'unrelated': 1}
    assert device.props['power_cost_today'] == 17.5


def test_independent_periods_accept_only_matching_resets():
    now = datetime.now().astimezone()
    device = SimpleNamespace(
        props={'power_cost_today': 17.5, 'power_cost_today_2': 5, 'power_cost_month': 320},
        data={'_power_cost_periods': {
            'power_cost_today': now.strftime('%Y-%m-%d'),
            'power_cost_today_2': (now - timedelta(days=1)).strftime('%Y-%m-%d'),
            'power_cost_month': now.strftime('%Y-%m'),
        }}, log=Mock(),
    )
    attrs = {'power_cost_today': 16.8, 'power_cost_today_2': 0.15, 'power_cost_month': 319}
    assert Device._filter_power_cost_statistics(device, attrs, now) == {'power_cost_today_2': 0.15}
    assert attrs['power_cost_today'] == 16.8


def cloud_device(hass, responses):
    entry = SimpleNamespace(hass=hass, id='test-entry', cloud=None,
                            get_config=lambda key=None, default=None: default)
    device = Device(DeviceInfo({'did': 'test-device', 'model': 'test.plug',
                                'mac': 'aa:bb:cc:dd:ee:ff'}), entry)
    device.cloud = SimpleNamespace(async_request_api=AsyncMock(side_effect=responses))
    device.dispatch = Mock()
    return device


def energy_command(key):
    return {'key': key, 'template': 'micloud_statistics_power_cost'}


def daily_record(value, days=0):
    now = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return {'time': int((now + timedelta(days=days)).timestamp()), 'value': value}


def test_record_parser_preserves_dates_and_does_not_mutate_response():
    records = [{'time': 123, 'value': 'bad'}, None, {'time': 456, 'value': '[0]'}]
    assert parse_power_cost_records(records) == [
        {'time': 123, 'value': []}, {}, {'time': 456, 'value': [0]},
    ]
    assert records[0]['value'] == 'bad'
    assert records[2]['value'] == '[0]'


@pytest.mark.parametrize('response', [None, {}, [], {'code': 1, 'result': []},
                                     {'code': -1, 'result': []}, {'result': {}}, {'result': []}])
async def test_bad_or_empty_responses_keep_existing_values(hass, response):
    device = cloud_device(hass, [response])
    device.props.update(power_cost_today=17.5, power_cost_month=320)
    device.available = False
    assert await device.update_cloud_statistics([energy_command('3.1')]) == {}
    assert device.props == {'power_cost_today': 17.5, 'power_cost_month': 320}
    assert device.available is False
    device.dispatch.assert_not_called()


@pytest.mark.parametrize('value', ['not-json', '', '[]', '[null]', '[true]',
                                  '["bad"]', '[NaN]', '[Infinity]', '[-1]', '{}'])
def test_bad_record_does_not_invalidate_other_daily_value(hass, value):
    result = template('micloud_statistics_power_cost', hass).async_render({
        'result': parse_power_cost_records([daily_record(value), daily_record('[1.2]')]),
    })
    assert result == {'power_cost_today': 1.2, 'power_cost_month': None}


async def test_failed_first_command_keeps_second_command_suffix(hass):
    device = cloud_device(hass, [TimeoutError(), {'code': 0, 'result': [daily_record('[2]')]}])
    attrs = await device.update_cloud_statistics([energy_command('3.1'), energy_command('11.1')])
    assert attrs == {'power_cost_today_2': 2, 'power_cost_month_2': 2}
    assert device.props == attrs
    assert device.cloud.async_request_api.await_count == 2


def test_missing_today_is_not_zero_and_future_day_is_excluded(hass):
    result = template('micloud_statistics_power_cost', hass).async_render({
        'result': parse_power_cost_records([daily_record('[4]', -1), daily_record('[999]', 1)]),
    })
    assert result['power_cost_today'] is None
    assert result['power_cost_month'] == 4


@pytest.mark.parametrize('key', ['power_cost_today', 'power_cost_month'])
@pytest.mark.parametrize('new_value', [0, 0.15, 1.2])
def test_period_change_accepts_nonzero_first_sample(key, new_value):
    now = datetime.now().astimezone()
    device = SimpleNamespace(props={key: 450}, data={'_power_cost_periods': {key: 'previous'}}, log=Mock())
    assert Device._filter_power_cost_statistics(device, {key: new_value}, now) == {key: new_value}


@pytest.mark.parametrize('zone', ['Asia/Shanghai', 'America/New_York'])
@pytest.mark.parametrize('instant', ['2026-01-01T00:00:00', '2028-02-29T12:00:00', '2026-03-08T03:05:00', '2026-11-01T01:30:00'])
def test_daily_template_uses_local_calendar_boundaries(hass, freezer, zone, instant):
    from zoneinfo import ZoneInfo
    original_zone = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(ZoneInfo(zone))
    now = datetime.fromisoformat(instant).replace(tzinfo=ZoneInfo(zone))
    freezer.move_to(now)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        result = template('micloud_statistics_power_cost', hass).async_render({
            'result': parse_power_cost_records([{'time': int(midnight.timestamp()), 'value': '[0]'}]),
        })
        assert result == {'power_cost_today': 0, 'power_cost_month': 0}
    finally:
        dt_util.set_default_time_zone(original_zone)


@pytest.mark.parametrize('key', ['power_cost_today', 'power_cost_month'])
@pytest.mark.parametrize('legacy', [True, False])
async def test_actual_platform_restore_update_and_unload(hass, make_device, freezer, key, legacy):
    freezer.move_to(datetime(2026, 9, 29, 23, 59, tzinfo=local_zone(hass)))
    spec = MiotSpec(hass, {
        'type': 'urn:miot-spec-v2:device:outlet:0000A002:test-energy:1',
        'services': [],
    })
    device = make_device(spec, model='test.energy', customizes={
        'unit_of_measurement': 'kWh', 'device_class': 'energy',
        'state_class': 'total_increasing', 'value_ratio': 0.01,
        'sensor_attributes': key,
    })
    device.available = True
    sensor = SensorEntity(device, device.find_converter(f'sensor.{key}'))
    now = datetime.now(local_zone(hass))
    extra = {sensor.attr: 17.5} if legacy else {
        'native_value': 17.5, 'native_unit_of_measurement': 'kWh',
        'power_cost_period': power_cost_period(sensor.attr, now),
    }
    mock_restore_cache_with_extra_data(hass, [(State(
        sensor.entity_id, '17500', {'unit_of_measurement': 'Wh'}, last_changed=now,
    ), extra)])
    assert await async_setup_component(hass, 'sensor', {})
    component = hass.data['sensor']
    await component.async_add_entities([sensor])
    await hass.async_block_till_done()
    assert sensor.native_value == 17.5
    assert device.props[key] == 1750
    assert device._filter_power_cost_statistics({key: 0}, now) == {}
    attrs = device._filter_power_cost_statistics({key: 1780}, now)
    device.props.update(attrs)
    device.dispatch(device.decode_attrs(attrs))
    await hass.async_block_till_done()
    assert sensor.native_value == 17.8
    # An ordinary midnight resets only the day; month-end resets both.
    for instant in (datetime(2026, 9, 30), datetime(2026, 10, 1)):
        freezer.move_to(instant.replace(tzinfo=local_zone(hass)))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        expected = 17.8 if key == 'power_cost_month' and instant.month == 9 else 0
        assert sensor.native_value == expected
        assert device.props[key] == pytest.approx(expected / 0.01)
        assert device.data['_power_cost_periods'][key] == power_cost_period(sensor.attr, dt_util.now())
    await component.async_remove_entity(sensor.entity_id)
    await hass.async_block_till_done()
    # HA retains a registry placeholder; the active entity and listener are gone.
    assert hass.states.get(sensor.entity_id).state == 'unavailable'
    assert sensor not in component.entities
    assert sensor.on_device_update not in device.listeners
    period = device.data['_power_cost_periods'][key]
    freezer.move_to(datetime(2026, 11, 1, tzinfo=local_zone(hass)))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert device.data['_power_cost_periods'][key] == period
