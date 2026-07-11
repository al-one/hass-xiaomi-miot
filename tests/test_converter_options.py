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
