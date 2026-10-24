"""zhimi.heater.nb1: ``heater.mode`` (Fan not swing / Fan swing) as the climate swing mode."""

from unittest.mock import AsyncMock

from homeassistant.components.climate import SWING_OFF, SWING_ON

from custom_components.xiaomi_miot.climate import ClimateEntity
from custom_components.xiaomi_miot.core.converters import MiotClimateConv
from custom_components.xiaomi_miot.core.utils import get_customize_via_model

MODEL = "zhimi.heater.nb1"


def _climate(device):
    conv = next(c for c in device.converters if isinstance(c, MiotClimateConv))
    return ClimateEntity(device, conv)


def test_nb1_customize():
    cfg = get_customize_via_model(MODEL)
    assert cfg["swing_property"] == "heater.mode"
    assert cfg["climate_translation_key"] == "fan_heater"


def test_nb1_mode_is_swing_not_preset(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    entity = _climate(device)

    assert entity._attr_swing_modes == [SWING_ON, SWING_OFF]
    assert entity._swing_values == (1, 0)
    assert not getattr(entity, "_attr_preset_modes", None)
    assert entity._attr_translation_key == "fan_heater"


async def test_nb1_swing_reads_and_writes_enum_values(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    entity = _climate(device)
    attr = entity._conv_swing.attr

    entity.set_state({attr: 1})
    assert entity._attr_swing_mode == SWING_ON
    entity.set_state({attr: 0})
    assert entity._attr_swing_mode == SWING_OFF

    device.async_write = AsyncMock()
    await entity.async_set_swing_mode(SWING_ON)
    await entity.async_set_swing_mode(SWING_OFF)
    written = [call.args[0][entity._conv_swing.full_name] for call in device.async_write.call_args_list]
    # the converter takes value descriptions and encodes them to the raw 1 / 0
    assert written == ["Fan swing", "Fan not swing"]


def test_swing_values_do_not_assume_zero_is_off(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    prop = _climate(device)._conv_swing.prop

    prop.value_list = [{"value": 1, "description": "Off"}, {"value": 2, "description": "On"}]
    assert ClimateEntity.swing_values(prop) == (2, 1)
    prop.value_list = [{"value": 5, "description": "Swing"}, {"value": 7, "description": "Stop"}]
    assert ClimateEntity.swing_values(prop) == (5, 7)
    prop.value_list = [{"value": 3, "description": "Fixed"}]
    assert ClimateEntity.swing_values(prop) is None
