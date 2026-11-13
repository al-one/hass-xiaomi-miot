"""Device availability broadcast: a device that goes offline must grey out its
entities instead of leaving them stuck on their last known state."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.xiaomi_miot.button import ButtonEntity
from custom_components.xiaomi_miot.core.utils import DeviceException
from custom_components.xiaomi_miot.select import SelectEntity
from custom_components.xiaomi_miot.sensor import SensorEntity

MODEL = "xiaomi.airp.mb5"
PM1 = {"siid": 3, "piid": 9, "code": 0, "value": 5}
BRIGHTNESS = {"siid": 7, "piid": 2, "code": 0, "value": 1}


def _device(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    device.async_refresh_local_device = AsyncMock(return_value=False)
    return device


def _local(device, *, results=None, error=None):
    device.local = SimpleNamespace(
        get_max_properties=lambda mapping: 10,
        async_get_properties_for_mapping=AsyncMock(return_value=results, side_effect=error),
    )


async def _poll(device):
    return await device.update_miot_status(use_local=True, use_cloud=False, auto_cloud=False)


async def test_offline_marks_entities_unavailable_and_recovery_restores(make_device, load_miot_spec):
    device = _device(make_device, load_miot_spec)
    sensor = SensorEntity(device, device.find_converter("sensor.environment.pm1"))
    select = SelectEntity(device, device.find_converter("select.screen.brightness"))

    _local(device, results=[PM1, BRIGHTNESS])
    await _poll(device)
    assert device.available is True
    assert sensor._attr_available is True
    assert select._attr_available is True

    _local(device, error=DeviceException("offline"))
    for _ in range(3):
        await _poll(device)
    assert device.available is False
    assert sensor._attr_available is False
    assert select._attr_available is False

    # A device-level recovery event reaches entities that did not report data
    # in the recovering poll (select here only gets sensor data).
    _local(device, results=[PM1])
    await _poll(device)
    assert device.available is True
    assert sensor._attr_available is True
    assert select._attr_available is True


async def test_recovery_does_not_fake_availability_for_unseen_entities(make_device, load_miot_spec):
    device = _device(make_device, load_miot_spec)
    sensor = SensorEntity(device, device.find_converter("sensor.environment.pm1"))
    assert sensor._attr_available is False

    _local(device, error=DeviceException("offline"))
    for _ in range(3):
        await _poll(device)
    assert device.available is False
    assert sensor._attr_available is False

    # The device is back, but this entity never reported a value; it must not
    # be flipped to available just because the device is reachable again.
    _local(device, results=[BRIGHTNESS])
    await _poll(device)
    assert device.available is True
    assert sensor._attr_available is False


async def test_info_entity_is_not_greyed_by_device_availability(make_device, load_miot_spec):
    device = _device(make_device, load_miot_spec)
    info = ButtonEntity(device, device.find_converter("button.info"))
    assert info._attr_available is True

    _local(device, error=DeviceException("offline"))
    for _ in range(3):
        await _poll(device)
    assert device.available is False
    assert info._attr_available is True
