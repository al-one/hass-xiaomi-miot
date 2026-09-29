"""Model-specific cloud energy and local property mapping for xiaomi.plug.04."""

from types import SimpleNamespace

from homeassistant.util import dt as dt_util

from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.templates import template
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES


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
