from custom_components.xiaomi_miot.core.converters import MiotClimateConv, MiotFanConv
from custom_components.xiaomi_miot.core.device import InfoConverter


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
