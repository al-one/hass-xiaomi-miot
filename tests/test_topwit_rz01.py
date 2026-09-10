"""Regression coverage for the Topwit rz01 malformed temperature reply."""

from types import SimpleNamespace

from custom_components.xiaomi_miot.core.device import Device
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.miot_spec import MiotResults


def normalize(model, results):
    return Device.normalize_miot_results(SimpleNamespace(model=model), results)


def test_rz01_temperature_code_is_normalized_to_a_standard_value():
    results = normalize('topwit.bhf_light.rz01', [
        {'siid': 4, 'piid': 5, 'code': 25},
    ])

    assert results == [{'siid': 4, 'piid': 5, 'code': 0, 'value': 25}]
    attrs = MiotResults(results, {
        'ptc_bath_heater.temperature': {'siid': 4, 'piid': 5},
    }).to_attributes()
    assert attrs == {'ptc_bath_heater.temperature': 25}


def test_rz01_only_normalizes_the_verified_temperature_property():
    results = normalize('topwit.bhf_light.rz01', [
        {'siid': 4, 'piid': 6, 'code': 25},
        {'siid': 4, 'piid': 5, 'code': 125},
        {'siid': 4, 'piid': 5, 'code': -4004},
        {'siid': 4, 'piid': 5, 'code': 25, 'value': 99},
    ])

    assert results == [
        {'siid': 4, 'piid': 6, 'code': 25},
        {'siid': 4, 'piid': 5, 'code': 125},
        {'siid': 4, 'piid': 5, 'code': -4004},
        {'siid': 4, 'piid': 5, 'code': 25, 'value': 99},
    ]


def test_other_models_keep_their_error_response_unchanged():
    result = {'siid': 4, 'piid': 5, 'code': 25}

    assert normalize('other.bath_heater', [result]) == [result]


def test_rz01_customization_removes_workaround_and_adds_read_only_child_lock():
    customize = DEVICE_CUSTOMIZES['topwit.bhf_light.rz01']

    assert 'sensor_attributes' not in customize
    assert customize['switch_properties'] == 'heating,blow,ventilation'
    assert customize['number_properties'] == 'ventilation_cnt_down'
    assert customize['binary_sensor_properties'] == 'child_lock'
