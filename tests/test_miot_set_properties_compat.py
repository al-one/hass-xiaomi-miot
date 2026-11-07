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


@pytest.mark.parametrize("did", [{}, {"did": "test-device"}])
async def test_single_property_accepts_matching_echo(make_device, load_miot_spec, did):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))
    response = {**did, "siid": 2, "piid": 3, "value": False}
    device.async_set_properties = AsyncMock(return_value=[response])
    device.dispatch = Mock()
    result = await device.async_set_miot_property(2, 3, False)
    assert result.is_success
    device.dispatch.assert_called_once()
    assert "code" not in response


@pytest.mark.parametrize("response", [
    {"siid": 2, "piid": 3, "value": False, "error": "denied"},
    {"siid": 2, "piid": 3, "value": False, "code": -4002},
    {"siid": 2, "piid": 3, "value": True},
    {"did": "other-device", "siid": 2, "piid": 3, "value": False},
])
async def test_single_property_rejects_unmatched_echo(make_device, load_miot_spec, response):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))
    device.async_set_properties = AsyncMock(return_value=[response])
    device.dispatch = Mock()
    result = await device.async_set_miot_property(2, 3, False)
    assert not result.is_success
    device.dispatch.assert_not_called()


def test_write_echo_does_not_change_read_parsing():
    from custom_components.xiaomi_miot.core.miot_spec import MiotResults
    echo = {"siid": 2, "piid": 3, "value": False}
    result = MiotResults([echo])
    assert not result.first.is_success
    assert result.has_error is not None


def test_aggregate_success_remains_lenient(make_device, load_miot_spec):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))
    assert device.set_property_error([REQUEST, {**REQUEST, "piid": 4}], [{"code": 0}]) is None
