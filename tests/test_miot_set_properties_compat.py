from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.xiaomi_miot.core.converters import MiotPropConv
from custom_components.xiaomi_miot.core.miot_spec import MiotResult
from custom_components.xiaomi_miot.select import SelectEntity


REQUEST = {"did": "test-device", "siid": 2, "piid": 3, "value": 0}
SUCCESS_RESPONSE = {"did": "test-device", "siid": 2, "piid": 3, "value": 0, "code": 0}


def test_set_property_error_accepts_standard_success(make_device, load_miot_spec):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))

    err = device.set_property_error([REQUEST], [SUCCESS_RESPONSE])

    assert err is None


@pytest.mark.parametrize("value", [0, 1])
@pytest.mark.parametrize("did", [{}, {"did": "test-device"}])
def test_set_property_error_accepts_matching_no_code_ack(make_device, load_miot_spec, value, did):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))
    request = {**REQUEST, "value": value}
    response = {**did, "siid": 2, "piid": 3, "value": value}

    err = device.set_property_error([request], [response])

    assert err is None


@pytest.mark.parametrize("shorter", [False, True])
def test_set_property_error_accepts_mixed_batch_success(make_device, load_miot_spec, shorter):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))
    requests = [
        {"did": "test-device", "siid": 2, "piid": 3, "value": 0},
        {"did": "test-device", "siid": 2, "piid": 5, "value": 25},
    ]
    responses = [
        {"did": "test-device", "siid": 2, "piid": 3, "value": 0, "code": 0},
        {"did": "test-device", "siid": 2, "piid": 5, "value": 25},
    ]

    err = device.set_property_error(requests, responses[1:] if shorter else responses[::-1])

    assert err is None


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        ({"did": "test-device", "siid": 9, "piid": 3, "value": 0}, None),
        ({"did": "test-device", "siid": 2, "piid": 9, "value": 0}, None),
        ({"did": "other-device", "siid": 2, "piid": 3, "value": 0}, None),
        ({"did": "test-device", "siid": 2, "piid": 3, "value": 1}, None),
        ({"did": "test-device", "siid": 2, "piid": 3}, None),
        ({"did": "test-device", "siid": 2, "piid": 3, "value": 0, "code": -4002}, -4002),
        ({"did": "test-device", "siid": 2, "piid": 3, "value": 0, "code": None}, None),
    ],
)
def test_set_property_error_rejects_invalid_or_failing_ack(
    make_device,
    load_miot_spec,
    response,
    expected_code,
):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))

    err = device.set_property_error([REQUEST], [response])

    assert isinstance(err, MiotResult)
    assert err.code == expected_code


@pytest.mark.parametrize("result", [[], [{}]])
@pytest.mark.asyncio
async def test_async_write_rejects_empty_or_malformed_response(
    make_device,
    load_miot_spec,
    result,
):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))
    attr = device.spec.get_service("thermostat").get_property("on").full_name
    device.async_set_properties = AsyncMock(return_value=result)
    device.dispatch = Mock()

    ret = await device.async_write({attr: True})

    assert ret == result
    device.dispatch.assert_not_called()


@pytest.mark.parametrize("result", [["ok"], [None]])
@pytest.mark.asyncio
async def test_async_write_dispatches_payload_for_non_dict_response(
    make_device,
    load_miot_spec,
    result,
):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))
    attr = device.spec.get_service("thermostat").get_property("on").full_name
    device.async_set_properties = AsyncMock(return_value=result)
    device.dispatch = Mock()
    payload = {attr: True}

    ret = await device.async_write(payload)

    assert ret == result
    device.dispatch.assert_called_once_with(payload)


@pytest.mark.asyncio
async def test_async_write_dispatches_payload_for_matching_no_code_select_ack(
    make_device,
    load_miot_spec,
):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))
    prop = device.spec.get_service("thermostat").get_property("mode")
    conv = MiotPropConv("mode", domain="select", prop=prop)
    device.add_converter(conv)
    entity = SelectEntity(device, conv)
    device.async_set_properties = AsyncMock(
        return_value=[{"did": device.did, "siid": 2, "piid": 1, "value": 0}]
    )

    await entity.async_select_option("Cool")

    assert entity.current_option == "Cool"
