import asyncio
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from custom_components.xiaomi_miot.number import NumberEntity
from custom_components.xiaomi_miot.core.device import Device, DeviceInfo
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.utils import get_customize_via_model


FIXTURES = Path(__file__).parent / "fixtures"


def make_huoman_device():
    hass = SimpleNamespace(
        config=SimpleNamespace(language="zh"),
        data=defaultdict(dict),
    )
    with (FIXTURES / "huoman.feeder.pf20i.json").open(encoding="utf-8") as file:
        spec = MiotSpec(hass, json.load(file))

    entry = SimpleNamespace(
        hass=hass,
        cloud=None,
        id="test-entry",
        adders={},
        get_config=lambda key=None, default=None: default,
    )
    device = Device(
        DeviceInfo({
            "did": "test-device",
            "mac": "aa:bb:cc:dd:ee:ff",
            "name": "Test Feeder",
            "model": "huoman.feeder.pf20i",
            "urn": spec.type,
        }),
        entry,
    )
    device.spec = spec
    device.init_converters()
    return device


def test_huoman_pf20i_exposes_feeder_controls():
    converter_names = {converter.full_name for converter in make_huoman_device().converters}

    assert {
        "sensor.pet_feeder.fault",
        "number.feeding_measure",
        "button.pet_feeder.pet_food_out",
        "sensor.desiccant.desiccant_left_time",
        "button.desiccant.reset_desiccant_life",
    } <= converter_names


def test_huoman_pf20i_uses_switch_for_night_mode():
    converter_names = {converter.full_name for converter in make_huoman_device().converters}

    assert "switch.indicator_light.on" in converter_names
    assert "light.indicator_light.on" not in converter_names
    assert get_customize_via_model(
        "huoman.feeder.pf20i:indicator_light.on",
        "name",
    ) == "夜间模式"


def test_huoman_pf20i_uses_local_number_for_feeding_measure():
    converter = make_huoman_device().find_converter("number.feeding_measure")

    assert converter.action.name == "pet_food_out"
    assert converter.option["action_value_only"] is True
    assert converter.option["default"] == 1
    assert converter.option["unique_id"] == "pet_feeder-2.feeding_measure-5"
    assert converter.prop.range_min() == 1
    assert converter.prop.range_max() == 20


def test_huoman_pf20i_feeding_action_uses_selected_measure():
    device = make_huoman_device()

    assert "pet_feeder.feeding_measure" not in device.miot_mapping()
    assert get_customize_via_model(
        "huoman.feeder.pf20i:pet_food_out",
        "action_params",
    ) == '{{ attrs["number.feeding_measure"]|default(1) }}'


def test_huoman_pf20i_feeding_measure_is_local_only():
    device = make_huoman_device()
    converter = device.find_converter("number.feeding_measure")
    entity = NumberEntity(device, converter)
    entity.async_write_ha_state = lambda: None

    assert entity.entity_id.endswith("feeding_measure")
    assert entity.unique_id.endswith("pet_feeder-2.feeding_measure-5")

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("本地出粮份数不应写入设备")

    device.async_write = fail_if_called
    asyncio.run(entity.async_set_native_value(7))

    assert entity.native_value == 7
    assert device.props["number.feeding_measure"] == 7
