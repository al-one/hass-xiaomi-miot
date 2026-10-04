"""Model-specific cloud energy and local property mapping for xiaomi.plug.04.

The fixture is a readable-property subset of the public 0000D032 instance:
https://miot-spec.org/miot-spec-v2/instance?type=urn:miot-spec-v2:device:outlet:0000A002:xiaomi-04:1:0000D032
"""

import json
import logging
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.util import dt as dt_util
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.binary_sensor import BinarySensorEntity
from custom_components.xiaomi_miot.number import NumberEntity
from custom_components.xiaomi_miot.sensor import SensorEntity
from custom_components.xiaomi_miot.switch import SwitchEntity
from custom_components.xiaomi_miot.select import SelectEntity


MODEL = "xiaomi.plug.04"


async def test_plug_04_uses_cloud_daily_energy_without_local_counter(make_device, load_miot_spec, hass):
    spec = load_miot_spec("xiaomi.plug.04.json")
    device = make_device(spec, model=MODEL)

    assert device.custom_config("miot_local") is True
    assert device.custom_config("auto_cloud") is True
    mapping = device.miot_mapping()
    assert {"siid": 11, "piid": 1} not in mapping.values()
    assert {"siid": 11, "piid": 2} in mapping.values()
    assert any(
        converter.domain == "binary_sensor"
        and getattr(converter, "prop", None)
        and converter.prop.iid == 3
        and converter.prop.service.iid == 11
        for converter in device.converters
    )
    assert device.cloud_statistics_commands[0]["key"] == "11.1"
    assert device.cloud_statistics_commands[0]["type"] == "stat_day_v3"
    assert device.custom_config("sensor_attributes") == "power_cost_today,power_cost_month"
    assert DEVICE_CUSTOMIZES[f"{MODEL}:power_cost_today"]["value_ratio"] == 1
    assert DEVICE_CUSTOMIZES[f"{MODEL}:power_cost_month"]["value_ratio"] == 1
    monthly_limit = next(
        converter for converter in device.converters
        if converter.domain == "number"
        and converter.prop.service.iid == 10
        and converter.prop.iid == 3
    )
    monthly_number = NumberEntity(device, monthly_limit)
    assert monthly_number.native_unit_of_measurement == "kWh"
    assert monthly_number._attr_translation_key == (
        "plug_04_monthly_energy_alert_threshold"
    )
    assert not hasattr(monthly_number, "_attr_name")
    power = next(
        converter for converter in device.converters
        if converter.domain == "sensor"
        and getattr(converter, "prop", None)
        and converter.prop.service.iid == 11
        and converter.prop.iid == 2
    )
    power_sensor = SensorEntity(device, power)
    assert power_sensor._attr_translation_key == "plug_04_real_time_power"
    assert not hasattr(power_sensor, "_attr_name")
    accumulation = next(
        converter for converter in device.converters
        if converter.domain == "binary_sensor"
        and getattr(converter, "prop", None)
        and converter.prop.service.iid == 11
        and converter.prop.iid == 3
    )
    assert BinarySensorEntity(device, accumulation)._attr_translation_key == (
        "plug_04_energy_accumulation_mode"
    )

    device.local = SimpleNamespace()
    device.cloud = SimpleNamespace()
    config = {"username": "test-user", "conn_mode": "auto"}
    device.entry.get_config = lambda key=None, default=None: config.get(key, default)
    assert device.use_local is True
    assert device.auto_cloud is True
    platform = EntityPlatform(
        hass=hass, logger=logging.getLogger(__name__), domain='sensor',
        platform_name='xiaomi_miot',
        platform=SimpleNamespace(async_setup_platform=AsyncMock()),
        scan_interval=timedelta(seconds=30), entity_namespace=None,
    )
    try:
        await platform.async_setup({})
        await platform.async_add_entities([power_sensor])
        assert power_sensor.name == 'Real-Time Power'
    finally:
        await platform.async_reset()


async def test_plug_04_cloud_values_are_already_kwh(hass, make_device):
    today = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
    device = make_device(MiotSpec(hass, {
        "type": "urn:miot-spec-v2:device:outlet:0000A002:xiaomi-04:1",
        "services": [],
    }), model=MODEL)
    device.cloud = SimpleNamespace(async_request_api=AsyncMock(return_value={
        "code": 0, "result": [{"time": int(today.timestamp()), "value": "[0.35]"}],
    }))
    rendered = await device.update_cloud_statistics()
    assert rendered["power_cost_today"] == 0.35
    assert rendered["power_cost_month"] == 0.35
    api, params = device.cloud.async_request_api.await_args.args
    assert api == 'v2/user/statistics'
    assert params['key'] == '11.1'
    assert params['data_type'] == 'stat_day_v3'
    assert params['limit'] == 31


def test_plug_04_property_names_are_model_scoped_and_translated():
    keys = DEVICE_CUSTOMIZES[MODEL]["property_translation_keys"]
    assert len(set(keys.values())) == len(keys)

    domains = {
        "prop.2.2": "select",
        "prop.11.2": "sensor",
        "prop.11.3": "binary_sensor",
    }
    for domain in ("sensor", "switch", "number"):
        for prop in DEVICE_CUSTOMIZES[MODEL][f"{domain}_properties"].split(","):
            if prop.startswith("prop."):
                domains[prop] = domain
    assert set(keys) == set(domains)

    translations = Path("custom_components/xiaomi_miot/translations")
    for language in ("en", "zh-Hans"):
        content = json.loads((translations / f"{language}.json").read_text())
        names = [
            content["entity"][domains[prop]][key]["name"]
            for prop, key in keys.items()
        ]
        assert all(names)
        assert len(names) == len(set(names))


async def test_all_named_plug_04_entities_use_spec_units_and_write_mapping(hass, make_device, load_miot_spec):
    device = make_device(load_miot_spec("xiaomi.plug.04.json"), model=MODEL)
    async def write_properties(params):
        return [{**param, 'code': 0} for param in params]

    device.async_set_properties = AsyncMock(side_effect=write_properties)
    classes = {'sensor': SensorEntity, 'number': NumberEntity, 'switch': SwitchEntity,
               'select': SelectEntity, 'binary_sensor': BinarySensorEntity}
    checked = set()
    for converter in device.converters:
        prop = getattr(converter, 'prop', None)
        if converter.domain not in classes or not prop or prop.unique_prop not in DEVICE_CUSTOMIZES[MODEL]['property_translation_keys']:
            continue
        entity = classes[converter.domain](device, converter)
        checked.add(prop.unique_prop)
        assert entity.unique_id
        assert entity.entity_id.startswith(converter.domain + '.')
        assert entity._attr_translation_key == DEVICE_CUSTOMIZES[MODEL]['property_translation_keys'][prop.unique_prop]
        if converter.domain == 'number':
            assert entity.native_min_value == prop.range_min()
            assert entity.native_max_value == prop.range_max()
            assert entity.native_step == prop.range_step()
            assert entity.native_unit_of_measurement == ('kWh' if (prop.service.iid, prop.iid) == (10, 3) else prop.unit_of_measurement)
            value = entity.native_min_value
            await entity.async_set_native_value(value)
        elif converter.domain == 'switch':
            value = True
            await entity.async_turn_on()
        elif converter.domain == 'select':
            value = 1
            await entity.async_select_option(entity.options[1])
        else:
            continue
        params = device.async_set_properties.await_args.args[0]
        assert params == [{'did': device.did, 'siid': prop.service.iid, 'piid': prop.iid, 'value': value}]
    assert checked == set(DEVICE_CUSTOMIZES[MODEL]['property_translation_keys'])
