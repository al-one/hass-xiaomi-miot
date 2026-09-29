"""Model-specific cloud energy and local property mapping for xiaomi.plug.04."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.util import dt as dt_util

from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.binary_sensor import BinarySensorEntity
from custom_components.xiaomi_miot.number import NumberEntity
from custom_components.xiaomi_miot.sensor import SensorEntity
from custom_components.xiaomi_miot.switch import SwitchEntity
from custom_components.xiaomi_miot.select import SelectEntity


MODEL = "xiaomi.plug.04"


def test_plug_04_uses_cloud_daily_energy_without_local_counter(make_device, hass):
    spec = MiotSpec(hass, {
        "type": "urn:miot-spec-v2:device:outlet:0000A002:xiaomi-04:1",
        "services": [
            {
                "iid": 2,
                "type": "urn:miot-spec-v2:service:switch:0000780C:xiaomi-04:1",
                "properties": [{
                    "iid": 1,
                    "type": "urn:miot-spec-v2:property:on:00000006:xiaomi-04:1",
                    "format": "bool",
                    "access": ["read", "write", "notify"],
                }],
            },
            {
                "iid": 11,
                "type": "urn:miot-spec-v2:service:power-consumption:0000780E:xiaomi-04:1",
                "properties": [
                    {
                        "iid": 1,
                        "type": "urn:miot-spec-v2:property:power-consumption:0000002F:xiaomi-04:1",
                        "format": "float",
                        "access": ["read", "notify"],
                        "unit": "kWh",
                    },
                    {
                        "iid": 2,
                        "type": "urn:miot-spec-v2:property:electric-power:00000066:xiaomi-04:1",
                        "format": "uint16",
                        "access": ["read", "notify"],
                        "unit": "watt",
                    },
                    {
                        "iid": 3,
                        "type": "urn:miot-spec-v2:property:power-consumption-accumulation-way:00000183:xiaomi-04:1",
                        "format": "bool",
                        "access": ["read", "notify"],
                    },
                ],
            },
            {
                "iid": 10,
                "type": "urn:miot-spec-v2:service:over-use-ele-alert:0000780E:xiaomi-04:1",
                "properties": [{
                    "iid": 3,
                    "type": "urn:xiaomi-spec:property:over-ele-month:00000003:xiaomi-04:1",
                    "description": "over-ele-month",
                    "format": "uint16",
                    "access": ["read", "write", "notify"],
                    "unit": "minutes",
                    "value-range": [20, 1800, 1],
                }],
            },
        ],
    })
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
    platform = SimpleNamespace(platform_name="xiaomi_miot", domain="sensor")
    power_sensor.platform = platform
    power_sensor.platform_data = platform
    assert power_sensor._name_internal(None, {
        "component.xiaomi_miot.entity.sensor.plug_04_real_time_power.name":
        "Real-Time Power",
    }) == "Real-Time Power"
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


async def test_all_named_plug_04_entities_use_spec_units_and_write_mapping(hass, make_device):
    # Compact snapshot of the public xiaomi-04:1:0000D032 specification.
    # No production state or credentials are needed for these entity checks.
    services = {
        2: 'switch', 3: 'indicator-light', 4: 'charging-protection',
        5: 'cycle-cycle', 8: 'quick-countdown', 9: 'max-power-limit',
        10: 'over-use-ele-alert', 11: 'power-consumption',
    }
    rows = [
        (2, 2, 'default-power-on-state', 'uint8', None, None),
        (3, 1, 'mode', 'bool', None, None),
        (3, 2, 'start-time', 'uint16', 'minutes', [0, 1440, 1]),
        (3, 3, 'end-time', 'uint16', 'minutes', [0, 1440, 1]),
        (4, 3, 'protection-time', 'uint16', 'minutes', [0, 1439, 1]),
        (4, 4, 'power-power', 'uint16', 'watt', [1, 600, 1]),
        (4, 5, 'protect-start-time', 'uint16', 'minutes', [0, 1439, 1]),
        (4, 6, 'protect-end-time', 'uint16', 'minutes', [0, 1439, 1]),
        (4, 7, 'period', 'bool', None, None),
        (4, 8, 'on-off', 'bool', None, None),
        (5, 1, 'status', 'bool', None, None),
        (8, 1, 'on-off', 'bool', None, None),
        (8, 2, 'duration', 'uint16', 'minutes', [0, 1439, 1]),
        (8, 4, 'delay-on', 'bool', None, None),
        (8, 5, 'delay-on-timer', 'uint16', 'minutes', [1, 1439, 1]),
        (8, 6, 'delay-off', 'bool', None, None),
        (8, 7, 'delay-off-timer', 'uint16', 'minutes', [1, 1439, 1]),
        (8, 8, 'delay-on-left-timer', 'uint16', 'minutes', [0, 1439, 1]),
        (8, 9, 'delay-off-left-timer', 'uint16', 'minutes', [0, 1439, 1]),
        (9, 4, 'power', 'uint16', 'watt', [100, 2500, 1]),
        (10, 1, 'on-off', 'bool', None, None),
        (10, 2, 'over-ele-day', 'uint16', 'kWh', [1, 60, 1]),
        (10, 3, 'over-ele-month', 'uint16', 'minutes', [20, 1800, 1]),
        (11, 2, 'electric-power', 'uint16', 'watt', [0, 10000, 1]),
        (11, 3, 'power-consumption-accumulation-way', 'bool', None, None),
    ]
    data = []
    for siid, name in services.items():
        props = []
        for sid, piid, prop_name, fmt, unit, limits in rows:
            if sid != siid:
                continue
            prop = {
                'iid': piid, 'type': f'urn:xiaomi-spec:property:{prop_name}:00000001:xiaomi-04:1',
                'format': fmt, 'access': ['read', 'notify'],
            }
            if siid != 11 and (siid, piid) not in ((8, 8), (8, 9)):
                prop['access'].append('write')
            if unit:
                prop['unit'] = unit
            if limits:
                prop['value-range'] = limits
            if (siid, piid) == (2, 2):
                prop['value-list'] = [{'value': v, 'description': n} for v, n in enumerate(('Default', 'Off', 'On'))]
            props.append(prop)
        data.append({'iid': siid, 'type': f'urn:xiaomi-spec:service:{name}:00007801:xiaomi-04:1', 'properties': props})
    device = make_device(MiotSpec(hass, {
        'type': 'urn:miot-spec-v2:device:outlet:0000A002:xiaomi-04:1:0000D032',
        'services': data,
    }), model=MODEL)
    device.async_set_properties = AsyncMock(return_value=[])
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
