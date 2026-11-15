from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.const import CONF_USERNAME

from custom_components.xiaomi_miot.core.const import CONF_CONN_MODE
from custom_components.xiaomi_miot.core.device import MiotDevice
from custom_components.xiaomi_miot.core.utils import DeviceException

MAPPING = {"prop.2.8": {"siid": 2, "piid": 8}}
OFFLINE = None  # miio.send returns None when the device doesn't answer on LAN
ONLINE = {"result": {"life": 1}}


def make_local(*responses):
    """A real MiotDevice with only miio.send mocked, so the genuine
    async_info()/handle_response() path raises utils.DeviceException."""
    miio = Mock()
    miio.addr = ("1.2.3.4", 54321)
    miio.send = AsyncMock(side_effect=list(responses))
    return MiotDevice(None, miio)


def make_cloud_device(make_device, load_miot_spec, *lan_responses):
    """A device on a cloud account in auto mode, so update_miot_status
    honours use_cloud/auto_cloud instead of routing everything to local."""
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))
    config = {CONF_USERNAME: "user", CONF_CONN_MODE: "auto"}
    device.entry.get_config = lambda key=None, default=None: config.get(key, default)
    device.cloud = AsyncMock()
    device.cloud.async_get_properties_for_mapping = AsyncMock(return_value=[])
    device.local = make_local(*lan_responses)
    return device


async def poll(device, check_lan=True):
    return await device.update_miot_status(mapping=MAPPING, use_cloud=True, check_lan=check_lan)


@pytest.mark.asyncio
async def test_failed_lan_check_does_not_raise(make_device, load_miot_spec):
    """Regression: an unreachable device made async_info() raise out of
    update_miot_status, failing the coordinator update instead of marking
    the device unavailable."""
    device = make_cloud_device(make_device, load_miot_spec, OFFLINE)

    assert await poll(device) is not None
    assert device._lan_check_fails == 1


@pytest.mark.asyncio
async def test_device_unavailable_after_three_failed_lan_checks(make_device, load_miot_spec):
    device = make_cloud_device(make_device, load_miot_spec, OFFLINE, OFFLINE, OFFLINE)

    await poll(device)
    await poll(device)
    assert device.available is True

    await poll(device)
    assert device._lan_check_fails == 3
    assert device.available is False


@pytest.mark.asyncio
async def test_passing_lan_check_resets_failures(make_device, load_miot_spec):
    device = make_cloud_device(make_device, load_miot_spec, OFFLINE, OFFLINE, OFFLINE, ONLINE, OFFLINE)

    for _ in range(3):
        await poll(device)
    assert device.available is False

    await poll(device)
    assert device._lan_check_fails == 0
    assert device.available is True

    await poll(device)
    assert device.available is True


@pytest.mark.asyncio
async def test_disabling_check_lan_clears_failures(make_device, load_miot_spec):
    device = make_cloud_device(make_device, load_miot_spec, OFFLINE, OFFLINE, OFFLINE)

    for _ in range(3):
        await poll(device)
    assert device.available is False

    await poll(device, check_lan=False)
    assert device.available is True


@pytest.mark.asyncio
async def test_local_success_resets_lan_check_failures(make_device, load_miot_spec):
    """With auto_cloud a failed local poll falls back to the cloud branch,
    so a later local success must clear the LAN failures from the outage."""
    device = make_cloud_device(make_device, load_miot_spec, *[OFFLINE] * 4)
    device.local.async_get_properties_for_mapping = AsyncMock(side_effect=[
        *[DeviceException("offline")] * 3, [], DeviceException("blip"),
    ])

    async def poll_auto():
        await device.update_miot_status(
            mapping=MAPPING, use_local=True, auto_cloud=True, check_lan=True, max_properties=5,
        )

    for _ in range(3):
        await poll_auto()
    assert device._lan_check_fails == 3
    assert device.available is False

    await poll_auto()
    assert device._lan_check_fails == 0
    assert device.available is True

    await poll_auto()
    assert device.available is True
