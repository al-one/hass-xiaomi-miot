from unittest.mock import AsyncMock

import pytest
from homeassistant.components.climate.const import HVACAction, HVACMode

from custom_components.xiaomi_miot.climate import ClimateEntity
from custom_components.xiaomi_miot.core.converters import MiotClimateConv, MiotFanConv
from custom_components.xiaomi_miot.core.device import InfoConverter
from custom_components.xiaomi_miot.core.hass_entity import convert_unique_id


def parent_domains(device):
    return [
        converter.domain
        for converter in device.converters
        if isinstance(converter, (MiotClimateConv, MiotFanConv))
    ]


def test_make_device_adds_info_converter(make_device, load_miot_spec):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))

    assert device.converters[0] is InfoConverter
    assert device.find_converter("button.info") is InfoConverter


def test_absent_model_converters_keeps_globals_and_appends(make_device, load_miot_spec):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        customizes={
            "append_converters": [{
                "class": MiotFanConv,
                "services": ["thermostat"],
                "kwargs": {"attr": "appended_fan", "main_props": ["prop.2.9"]},
            }],
        },
    )

    parent_names = [converter.full_name for converter in device.converters]
    appended_index = parent_names.index("fan.appended_fan")
    global_indices = [
        index
        for index, converter in enumerate(device.converters)
        if isinstance(converter, (MiotClimateConv, MiotFanConv))
        and converter.full_name != "fan.appended_fan"
    ]
    assert global_indices
    assert max(global_indices) < appended_index
    assert "climate" in parent_domains(device)
    assert device.find_converter("fan.appended_fan") is not None


def test_empty_model_converters_skips_globals_but_keeps_appends(make_device, load_miot_spec):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        customizes={
            "converters": [],
            "append_converters": [{
                "class": MiotFanConv,
                "services": ["thermostat"],
                "kwargs": {"attr": "appended_fan", "main_props": ["prop.2.9"]},
            }],
        },
    )

    assert parent_domains(device) == ["fan"]
    assert device.find_converter("fan.appended_fan") is not None
    assert device.find_converter("button.info") is InfoConverter


def test_model_converters_replace_globals_and_keep_appends(make_device, load_miot_spec):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        customizes={
            "converters": [{
                "class": MiotClimateConv,
                "services": ["thermostat"],
                "kwargs": {"attr": "replacement", "main_props": ["prop.2.8"]},
            }],
            "append_converters": [{
                "class": MiotFanConv,
                "services": ["thermostat"],
                "kwargs": {"attr": "appended_fan", "main_props": ["prop.2.9"]},
            }],
        },
    )

    assert parent_domains(device) == ["climate", "fan"]
    assert device.find_converter("climate.replacement") is not None
    assert device.find_converter("fan.appended_fan") is not None


def test_info_omits_converter_config_but_lists_effective_names(make_device, load_miot_spec):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        customizes={
            "converters": [],
            "append_converters": [{
                "class": MiotFanConv,
                "services": ["thermostat"],
                "kwargs": {"attr": "appended_fan", "main_props": ["prop.2.9"]},
            }],
        },
    )
    payload = {}

    InfoConverter.decode(device, payload, None)

    assert "converters" not in payload["customizes"]
    assert "append_converters" not in payload["customizes"]
    assert payload["converters"] == [converter.full_name for converter in device.converters]
    assert "fan.appended_fan" in payload["converters"]


def service_converter(spec, **option):
    service = spec.get_service("thermostat")
    return MiotClimateConv(
        service=service,
        attr="floor_heating",
        main_props=["prop.2.8"],
        option=option,
    )


def test_unique_id_option_priority(load_miot_spec):
    spec = load_miot_spec("cnhdm.airrtc.wkq01.json")

    assert convert_unique_id(service_converter(spec)) == 2
    assert convert_unique_id(service_converter(spec, use_unique_attr=True)) == "floor_heating"
    assert convert_unique_id(service_converter(spec, unique_id="explicit-id")) == "explicit-id"
    assert convert_unique_id(service_converter(
        spec,
        unique_id="explicit-id",
        use_unique_attr=True,
    )) == "explicit-id"


def test_explicit_attrs_make_distinct_converter_full_names(load_miot_spec):
    spec = load_miot_spec("cnhdm.airrtc.wkq01.json")

    floor = service_converter(spec, use_unique_attr=True)
    fresh = MiotFanConv(
        service=spec.get_service("thermostat"),
        attr="fresh_air",
        main_props=["prop.2.9"],
        option={"use_unique_attr": True},
    )

    assert floor.full_name == "climate.floor_heating"
    assert fresh.full_name == "fan.fresh_air"


def test_fixed_name_and_attr_based_entity_id(make_device, load_miot_spec):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        customizes={"converters": [{
            "class": MiotClimateConv,
            "services": ["thermostat"],
            "kwargs": {
                "attr": "floor_heating",
                "main_props": ["prop.2.8"],
                "option": {
                    "name": "Floor Heating",
                    "use_unique_attr": True,
                },
            },
        }]},
    )
    entity = ClimateEntity(device, device.find_converter("climate.floor_heating"))

    assert entity.unique_id == f"{device.unique_id}-floor_heating"
    assert entity.entity_id.endswith("_floor_heating")
    assert entity._attr_name == "Floor Heating"
    assert entity._attr_translation_key is None


def test_service_entity_defaults_remain_unchanged(make_device, load_miot_spec):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        customizes={"converters": [{
            "class": MiotClimateConv,
            "services": ["thermostat"],
            "kwargs": {"main_props": ["prop.2.1"]},
        }]},
    )
    converter = next(c for c in device.converters if isinstance(c, MiotClimateConv))
    entity = ClimateEntity(device, converter)

    assert entity.unique_id == f"{device.unique_id}-2"
    assert "thermostat" in entity.entity_id
    assert entity._attr_translation_key == "thermostat"


def make_climate(make_device, spec, converters, option=None):
    device = make_device(
        spec,
        customizes={"converters": [{
            "class": MiotClimateConv,
            "services": ["thermostat"],
            "kwargs": {
                "attr": "test_climate",
                "main_props": ["prop.2.8"],
                "option": option or {},
            },
            "converters": converters,
        }]},
    )
    entity = ClimateEntity(device, device.find_converter("climate.test_climate"))
    device.async_write = AsyncMock()
    return entity


def assert_fixed_heat(entity, is_on):
    assert entity._attr_is_on is is_on
    assert entity.hvac_mode == (HVACMode.HEAT if is_on else HVACMode.OFF)
    assert entity.hvac_action == (HVACAction.HEATING if is_on else HVACAction.OFF)


def test_fixed_power_hvac_mode_is_deterministic(make_device, load_miot_spec):
    entity = make_climate(
        make_device,
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        [{"props": ["prop.2.10"]}, {"props": ["prop.2.8"]}],
        {"hvac_mode": "heat"},
    )

    assert set(entity.hvac_modes) == {HVACMode.OFF, HVACMode.HEAT}
    for value in [True, True, False, False, True]:
        entity.set_state({entity._conv_power.full_name: value})
        assert_fixed_heat(entity, value)
        assert entity._attr_preset_mode is None


def test_fixed_mode_preserves_power_state_on_partial_payload(make_device, load_miot_spec):
    entity = make_climate(
        make_device,
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        [{"props": ["prop.2.10"]}, {"props": ["prop.2.8"]}],
        {"hvac_mode": "heat"},
    )

    entity.set_state({entity._conv_power.full_name: True})
    entity.set_state({entity._conv_target_temp.full_name: 31})
    assert_fixed_heat(entity, True)
    assert entity.target_temperature == 31

    entity.set_state({entity._conv_power.full_name: False})
    entity.set_state({entity._conv_target_temp.full_name: 18})
    assert_fixed_heat(entity, False)
    assert entity.target_temperature == 18

    entity.set_state({
        entity._conv_power.full_name: True,
        entity._conv_target_temp.full_name: 26,
    })
    assert_fixed_heat(entity, True)
    assert entity.target_temperature == 26


def test_real_mode_converter_ignores_fixed_hvac_option(make_device, load_miot_spec):
    entity = make_climate(
        make_device,
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        [{"props": ["prop.2.3"]}, {"props": ["prop.2.1"], "desc": True}],
        {"hvac_mode": "heat"},
    )

    assert set(entity.hvac_modes) == {HVACMode.OFF, HVACMode.AUTO, HVACMode.COOL, HVACMode.HEAT}
    entity.set_state({entity._conv_mode.full_name: "Cool", entity._conv_power.full_name: True})
    assert entity.hvac_mode == HVACMode.COOL
    assert entity.hvac_action == HVACAction.COOLING


@pytest.mark.asyncio
async def test_real_mode_converter_writes_real_mode_property(make_device, load_miot_spec):
    entity = make_climate(
        make_device,
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        [{"props": ["prop.2.3"]}, {"props": ["prop.2.1"], "desc": True}],
        {"hvac_mode": "heat"},
    )
    entity._attr_is_on = True

    await entity.async_set_hvac_mode(HVACMode.COOL)

    entity.device.async_write.assert_awaited_once_with({entity._conv_mode.full_name: "Cool"})


def test_power_only_climate_without_option_keeps_auto(make_device, load_miot_spec):
    entity = make_climate(
        make_device,
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        [{"props": ["prop.2.10"]}],
    )

    assert set(entity.hvac_modes) == {HVACMode.OFF, HVACMode.AUTO}
    entity.set_state({entity._conv_power.full_name: True})
    assert entity.hvac_mode == HVACMode.AUTO
