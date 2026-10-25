from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.xiaomi_miot.climate import ClimateEntity
from custom_components.xiaomi_miot.core.converters import MiotClimateConv
from custom_components.xiaomi_miot.core.device import MiotDevice
from custom_components.xiaomi_miot.core.utils import DeviceException


def make_local(response):
    """A real MiotDevice with only the network layer (miio.send) mocked.

    This drives the genuine async_info()/handle_response() path so the LAN
    check raises the same utils.DeviceException the production code catches —
    rather than asserting against an arbitrary exception type.
    """
    miio = Mock()
    miio.addr = ("1.2.3.4", 54321)
    miio.send = AsyncMock(return_value=response)
    return MiotDevice(None, miio)


def make_entity(make_device, spec):
    """A plain (non-InfoConv) entity registered as a device update listener."""
    device = make_device(
        spec,
        customizes={"converters": [{
            "class": MiotClimateConv,
            "services": ["thermostat"],
            "kwargs": {"attr": "test_climate", "main_props": ["prop.2.8"]},
        }]},
    )
    entity = ClimateEntity(device, device.find_converter("climate.test_climate"))
    entity.added = True
    entity._async_write_ha_state = Mock()
    return device, entity


MAPPING = {"prop.2.8": {"siid": 2, "piid": 8}}
OFFLINE = None  # miio.send returns None when the device doesn't answer on LAN
ONLINE = {"result": {"life": 1}}


def make_cloud_device(make_device, load_miot_spec, *lan_responses):
    device, _ = make_entity(make_device, load_miot_spec("cnhdm.airrtc.wkq01.json"))
    device.cloud = AsyncMock()
    device.cloud.async_get_properties_for_mapping = AsyncMock(return_value=[])
    device.local = make_local(response=None)
    device.local.miio.send = AsyncMock(side_effect=list(lan_responses))
    return device


async def poll(device):
    return await device.update_miot_status(mapping=MAPPING, use_cloud=True, check_lan=True)


@pytest.mark.asyncio
async def test_failed_lan_check_does_not_raise(make_device, load_miot_spec):
    """Regression: an unreachable device made async_info() raise out of
    update_miot_status, failing the coordinator update instead of marking
    the device unavailable."""
    device = make_cloud_device(make_device, load_miot_spec, OFFLINE)

    assert await poll(device) is not None
    assert device.local.miio.send.await_count == 1


@pytest.mark.asyncio
async def test_device_unavailable_after_three_failed_lan_checks(make_device, load_miot_spec):
    device = make_cloud_device(make_device, load_miot_spec, OFFLINE, OFFLINE, OFFLINE)

    await poll(device)
    await poll(device)
    assert device.available is True

    await poll(device)
    assert device.available is False


@pytest.mark.asyncio
async def test_passing_lan_check_resets_failures(make_device, load_miot_spec):
    device = make_cloud_device(make_device, load_miot_spec, OFFLINE, OFFLINE, OFFLINE, ONLINE, OFFLINE)

    for _ in range(3):
        await poll(device)
    assert device.available is False

    await poll(device)
    assert device.available is True

    await poll(device)
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
    assert device.available is False

    await poll_auto()
    assert device.available is True

    await poll_auto()
    assert device.available is True
