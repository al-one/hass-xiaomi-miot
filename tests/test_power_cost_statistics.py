"""Native-unit restoration and the device's raw cloud baseline."""

from datetime import datetime, timedelta
from types import SimpleNamespace, MethodType
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import State
from homeassistant.helpers.restore_state import RestoredExtraData

from custom_components.xiaomi_miot.core.converters import BaseConv
from custom_components.xiaomi_miot.core.device import Device
from custom_components.xiaomi_miot.core.hass_entity import XEntity
from custom_components.xiaomi_miot.core.utils import local_zone, power_cost_period
from custom_components.xiaomi_miot.sensor import SensorEntity


def make_sensor(hass, key, ratio):
    sensor = SensorEntity.__new__(SensorEntity)
    sensor.hass = hass
    sensor.conv = BaseConv(key, 'sensor')
    sensor.attr = sensor.conv.full_name
    sensor._attr_native_unit_of_measurement = 'kWh'
    sensor._attr_native_value = None
    sensor.custom_value_ratio = ratio
    sensor.async_on_remove = Mock()
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
