import json
from pathlib import Path
from types import SimpleNamespace

from custom_components.xiaomi_miot.core.device import Device, DeviceInfo
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.utils import get_customize_via_model


FIXTURES = Path(__file__).parent / "fixtures"


def test_huoman_pf20i_exposes_feeder_controls():
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

    converter_names = {converter.full_name for converter in device.converters}

    assert {
        "sensor.pet_feeder.fault",
        "number.pet_feeder.feeding_measure",
        "button.pet_feeder.pet_food_out",
        "sensor.desiccant.desiccant_left_time",
        "button.desiccant.reset_desiccant_life",
    } <= converter_names


def test_huoman_pf20i_feeding_action_uses_selected_measure():
    assert get_customize_via_model(
        "huoman.feeder.pf20i:pet_food_out",
        "action_params",
    ) == '{{ attrs["feeding_measure-2-5"]|default(1) }}'
