"""Light colour temperature limits when the spec has no value range."""
import pytest
from homeassistant.components.light import DEFAULT_MAX_KELVIN, DEFAULT_MIN_KELVIN

from custom_components.xiaomi_miot.core.converters import MiotColorTempConv
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.light import LightEntity

URN = "urn:miot-spec-v2:device:light:0000A001:test-ct:1"


def _light(hass, make_device, unit, value_range=None):
    color_temp = {
        "iid": 3,
        "type": "urn:miot-spec-v2:property:color-temperature:0000000F:test-ct:1",
        "description": "Color Temperature",
        "format": "uint32",
        "access": ["read", "write", "notify"],
        "unit": unit,
    }
    if value_range is not None:
        color_temp["value-range"] = value_range
    spec = MiotSpec(hass, {
        "type": URN,
        "description": "Light",
        "services": [{
            "iid": 2,
            "type": "urn:miot-spec-v2:service:light:00007802:test-ct:1",
            "description": "Light",
            "properties": [
                {
                    "iid": 1,
                    "type": "urn:miot-spec-v2:property:on:00000006:test-ct:1",
                    "description": "Switch Status",
                    "format": "bool",
                    "access": ["read", "write", "notify"],
                },
                color_temp,
            ],
        }],
    })
    device = make_device(spec, model="test.light.ct", customizes={})
    conv = next(c for c in device.converters if c.domain == "light")
    return device, LightEntity(device, conv)


@pytest.mark.parametrize(("unit", "limits"), [
    ("kelvin", (DEFAULT_MIN_KELVIN, DEFAULT_MAX_KELVIN)),
    # the percentage scale can only represent 2500..6500 kelvin
    ("percentage", (2500, 6500)),
])
def test_missing_value_range_falls_back_to_default_limits(hass, make_device, unit, limits):
    _, entity = _light(hass, make_device, unit)

    # HA 2026.11 uses the _attr_ values as they are, without a fallback for None
    assert (entity._attr_min_color_temp_kelvin, entity._attr_max_color_temp_kelvin) == limits
    assert isinstance(entity._attr_min_color_temp_kelvin, int)
    assert isinstance(entity._attr_max_color_temp_kelvin, int)


@pytest.mark.parametrize(("unit", "value_range", "limits"), [
    ("kelvin", [2700, 6500, 1], (2700, 6500)),
    ("percentage", [1, 100, 1], (2500, 6460)),
])
def test_declared_value_range_is_used(hass, make_device, unit, value_range, limits):
    _, entity = _light(hass, make_device, unit, value_range)

    assert (entity._attr_min_color_temp_kelvin, entity._attr_max_color_temp_kelvin) == limits


@pytest.mark.parametrize(("unit", "value_range", "value", "encoded"), [
    ("kelvin", [2700, 6500, 1], 2000, 2700),
    ("percentage", [1, 100, 1], 2000, 100),
])
def test_encode_clamps_to_declared_value_range(hass, make_device, unit, value_range, value, encoded):
    device, _ = _light(hass, make_device, unit, value_range)
    conv = next(c for c in device.converters if isinstance(c, MiotColorTempConv))
    payload = {}

    conv.encode(device, payload, value)

    assert payload["params"][0]["value"] == encoded


@pytest.mark.parametrize(("value", "encoded"), [(2000, 100), (6535, 0)])
def test_encode_without_percentage_range_stays_in_scale(hass, make_device, value, encoded):
    device, _ = _light(hass, make_device, "percentage")
    conv = next(c for c in device.converters if isinstance(c, MiotColorTempConv))
    payload = {}

    conv.encode(device, payload, value)

    assert payload["params"][0]["value"] == encoded


def test_encode_without_value_range_does_not_clamp(hass, make_device):
    device, _ = _light(hass, make_device, "kelvin")
    conv = next(c for c in device.converters if isinstance(c, MiotColorTempConv))
    payload = {}

    conv.encode(device, payload, 4000)

    assert payload["method"] == "set_properties"
    assert payload["params"][0]["siid"] == 2
    assert payload["params"][0]["piid"] == 3
    assert payload["params"][0]["value"] == 4000
