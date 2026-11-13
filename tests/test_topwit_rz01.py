"""Regression coverage for the Topwit rz01 malformed temperature reply."""

from types import SimpleNamespace

from custom_components.xiaomi_miot.core.device import Device
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.miot_spec import MiotResults


def normalize(keys, results):
    device = SimpleNamespace(custom_config_list=lambda key: keys)
    return Device.normalize_miot_results(device, results)


def test_declared_temperature_code_is_normalized_to_a_standard_value():
    results = normalize(['4.5'], [
        {'siid': 4, 'piid': 5, 'code': 25},
    ])

    assert results == [{'siid': 4, 'piid': 5, 'code': 0, 'value': 25}]
    attrs = MiotResults(results, {
        'ptc_bath_heater.temperature': {'siid': 4, 'piid': 5},
    }).to_attributes()
    assert attrs == {'ptc_bath_heater.temperature': 25}


def test_recode_only_applies_to_declared_properties():
    results = normalize(['4.5'], [
        {'siid': 4, 'piid': 6, 'code': 25},
        {'siid': 4, 'piid': 5, 'code': 25, 'value': 99},
    ])

    assert results == [
        {'siid': 4, 'piid': 6, 'code': 25},
        {'siid': 4, 'piid': 5, 'code': 25, 'value': 99},
    ]


def test_undeclared_recode_keeps_the_response_unchanged():
    result = {'siid': 4, 'piid': 5, 'code': 25}

    assert normalize(None, [result]) == [result]


def test_rz01_customization_removes_workaround_and_adds_read_only_child_lock():
    customize = DEVICE_CUSTOMIZES['topwit.bhf_light.rz01']

    assert 'sensor_attributes' not in customize
    assert customize['switch_properties'] == 'heating,blow,ventilation'
    assert customize['number_properties'] == 'ventilation_cnt_down'
    assert customize['binary_sensor_properties'] == 'child_lock'
    assert customize['miot_result_recode'] == ['4.5']
