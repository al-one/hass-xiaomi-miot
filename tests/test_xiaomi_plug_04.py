"""Model-specific cloud energy and local property mapping for xiaomi.plug.04."""

import json
from pathlib import Path
from types import SimpleNamespace

from homeassistant.util import dt as dt_util

from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.templates import template
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.binary_sensor import BinarySensorEntity
from custom_components.xiaomi_miot.number import NumberEntity
from custom_components.xiaomi_miot.sensor import SensorEntity


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
    assert device.use_local is True
    assert device.auto_cloud is True


def test_plug_04_cloud_values_are_already_kwh(hass):
    today = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
    rendered = template("micloud_statistics_power_cost", hass).async_render({
        "result": [{"time": int(today.timestamp()), "value": "[0.35]"}],
    })
    assert rendered["power_cost_today"] == 0.35
    assert rendered["power_cost_month"] == 0.35


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
