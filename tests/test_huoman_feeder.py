import json
from pathlib import Path
from types import SimpleNamespace

from custom_components.xiaomi_miot.core.device import Device, DeviceInfo
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.utils import get_customize_via_model


FIXTURES = Path(__file__).parent / "fixtures"


def make_huoman_device():
    hass = SimpleNamespace(config=SimpleNamespace(language="zh"))
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


def test_huoman_pf20i_feeding_measure_is_polled_despite_empty_access():
    mapping = make_huoman_device().miot_mapping()

    assert mapping["pet_feeder.feeding_measure"] == {"siid": 2, "piid": 5}


def test_huoman_pf20i_decodes_feeding_measure_value():
    payload = make_huoman_device().decode([{"siid": 2, "piid": 5, "code": 0, "value": 7}])

    assert payload["number.feeding_measure"] == 7


def test_huoman_pf20i_feeding_action_uses_selected_measure():
    assert get_customize_via_model(
        "huoman.feeder.pf20i:pet_food_out",
        "action_params",
    ) == '{{ attrs["pet_feeder.feeding_measure"]|default(1) }}'
