"""Connection-mode boundaries, independent of individual model enablement."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.xiaomi_miot.core.device import Device, DeviceInfo
from custom_components.xiaomi_miot.core.utils import DeviceException


MODEL = "test.device.model"
MAPPING = {"switch.on": {"siid": 2, "piid": 1}}
RESULT = [{"did": "test-device", "siid": 2, "piid": 1, "code": 0, "value": True}]


def make_mode_device(hass, mode):
    config = {"username": "test-user", "conn_mode": mode}
    entry = SimpleNamespace(
        hass=hass, id="test-entry", cloud=SimpleNamespace(user_id="test-user"),
        get_config=lambda key=None, default=None: config.get(key, default),
    )
    device = Device(DeviceInfo({
        "did": "test-device", "model": MODEL, "name": "Protection switch",
        "mac": "aa:bb:cc:dd:ee:ff", "pid": 0,
    }), entry)
    device.local = SimpleNamespace(
        get_max_properties=lambda mapping: 6,
        async_get_properties_for_mapping=AsyncMock(return_value=RESULT),
        async_send=AsyncMock(return_value={"code": 0}),
    )
    device.cloud = SimpleNamespace(
        user_id="test-user",
        async_get_properties_for_mapping=AsyncMock(return_value=RESULT),
        async_set_props=AsyncMock(return_value=RESULT),
        async_do_action=AsyncMock(return_value={"code": 0}),
    )
    device.custom_config_bool = lambda key, default=None: key in ("miot_local", "auto_cloud")
    device.decode = lambda value: {}
    device.dispatch = lambda value, **kwargs: None
    return device


@pytest.mark.parametrize("mode,local", [("auto", True), ("local", True), ("cloud", False)])
async def test_periodic_read_respects_mode(hass, mode, local):
    device = make_mode_device(hass, mode)
    await device.update_miot_status(mapping=MAPPING, max_properties=6)
    assert device.local.async_get_properties_for_mapping.await_count == int(local)
    assert device.cloud.async_get_properties_for_mapping.await_count == int(not local)


async def test_local_read_failure_never_uses_cloud_even_with_explicit_fallback(hass):
    device = make_mode_device(hass, "local")
    device._local_fails = 2
    device.local.async_get_properties_for_mapping.side_effect = DeviceException("offline")
    await device.update_miot_status(mapping=MAPPING, auto_cloud=True, max_properties=6)
    device.cloud.async_get_properties_for_mapping.assert_not_awaited()


async def test_auto_read_failure_falls_back_to_cloud(hass):
    device = make_mode_device(hass, "auto")
    device.local.async_get_properties_for_mapping.side_effect = DeviceException("offline")
    await device.update_miot_status(mapping=MAPPING, max_properties=6)
    device.cloud.async_get_properties_for_mapping.assert_awaited_once()


async def test_local_manual_read_retries_local_after_failure(hass):
    device = make_mode_device(hass, "local")
    device._local_state = False
    device.spec = SimpleNamespace()
    await device.async_get_properties(MAPPING, update_entity=False)
    device.local.async_get_properties_for_mapping.assert_awaited_once()
    device.cloud.async_get_properties_for_mapping.assert_not_awaited()


async def test_local_write_ignores_cloud_override_and_does_not_retry(hass):
    device = make_mode_device(hass, "local")
    device.custom_config_bool = lambda key, default=None: key == "miot_cloud_write"
    device._local_state = False
    device.local.async_send.side_effect = DeviceException("result unknown")
    with pytest.raises(DeviceException):
        await device.async_set_properties([
            {"did": "test-device", "siid": 2, "piid": 1, "value": False},
        ])
    device.cloud.async_set_props.assert_not_awaited()
    assert device.local.async_send.await_count == 1


async def test_local_action_ignores_cloud_override(hass):
    device = make_mode_device(hass, "local")
    device.custom_config_bool = lambda key, default=None: key == "miot_cloud_action"
    device._local_state = False
    await device.async_call_action(2, 1, cloud=True, force_params=True)
    device.local.async_send.assert_awaited_once()
    device.cloud.async_do_action.assert_not_awaited()


@pytest.mark.parametrize("mode,local", [("auto", True), ("local", True), ("cloud", False)])
async def test_write_and_action_respect_mode_before_first_poll(hass, mode, local):
    device = make_mode_device(hass, mode)
    device.custom_config_bool = lambda key, default=None: key in ("miot_local", "auto_cloud")
    await device.async_set_properties([
        {"did": "test-device", "siid": 2, "piid": 1, "value": False},
    ])
    # Before the first local sample, lack of a state is not a local failure.
    await device.async_call_action(2, 1, force_params=True)
    assert device.local.async_send.await_count == 2 * int(local)
    assert device.cloud.async_set_props.await_count == int(not local)
    assert device.cloud.async_do_action.await_count == int(not local)
