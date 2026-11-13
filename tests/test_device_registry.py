"""Tests for Xiaomi MIoT device registry compatibility."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from custom_components.xiaomi_miot.core.device import Device, DeviceInfo


def _make_device(hass, *, unique_id, entry_id="test-entry"):
    entry = SimpleNamespace(
        hass=hass,
        cloud=None,
        id=entry_id,
        get_config=lambda key=None, default=None: default,
    )
    info = DeviceInfo({
        "did": unique_id,
        "mac": unique_id,
        "name": "Test Device",
        "model": "test.device.model",
    })
    return Device(info, entry)


def test_device_info_omits_empty_via_device(hass):
    """Do not pass the deprecated via_device key for standalone devices."""
    device = _make_device(hass, unique_id="aa:bb:cc:dd:ee:01")

    assert "via_device" not in device.hass_device_info
    assert "via_device_id" not in device.hass_device_info


def test_device_info_uses_parent_device_id(hass):
    """Link proxy devices using the parent's registry ID on newer HA versions."""
    parent = _make_device(hass, unique_id="aa:bb:cc:dd:ee:01")
    child = _make_device(hass, unique_id="aa:bb:cc:dd:ee:02")
    child._proxy_device = parent
    parent_entry = SimpleNamespace(id="parent-device-id")
    registry = Mock()
    registry.async_get_device_by_identifier.return_value = parent_entry

    with patch(
        "custom_components.xiaomi_miot.core.device.dr.async_get",
        return_value=registry,
    ):
        device_info = child.hass_device_info

    registry.async_get_device_by_identifier.assert_called_once_with(
        next(iter(parent.identifiers)), parent.entry.id
    )
    assert device_info["via_device_id"] == parent_entry.id
    assert "via_device" not in device_info


def test_hass_device_uses_unambiguous_identifier_lookup(hass):
    """Look up devices within their owning config entry on newer HA versions."""
    device = _make_device(hass, unique_id="aa:bb:cc:dd:ee:01")
    registry = Mock()
    registry.async_get_device_by_identifier.return_value = expected = object()

    with patch(
        "custom_components.xiaomi_miot.core.device.dr.async_get",
        return_value=registry,
    ):
        assert device.hass_device is expected

    registry.async_get_device_by_identifier.assert_called_once_with(
        next(iter(device.identifiers)), device.entry.id
    )


def test_device_info_falls_back_to_parent_identifier(hass):
    """Keep proxy device links working on HA versions before 2026.8."""
    parent = _make_device(hass, unique_id="aa:bb:cc:dd:ee:01")
    child = _make_device(hass, unique_id="aa:bb:cc:dd:ee:02")
    child._proxy_device = parent
    registry = SimpleNamespace(async_get_device=Mock())

    with patch(
        "custom_components.xiaomi_miot.core.device.dr.async_get",
        return_value=registry,
    ):
        device_info = child.hass_device_info

    assert device_info["via_device"] == next(iter(parent.identifiers))
    assert "via_device_id" not in device_info


async def _fire_device_registry_update(registry, device_id):
    """Register the registry listener and invoke it with an update event."""
    from custom_components.xiaomi_miot import _handle_device_registry_event

    fake_hass = SimpleNamespace(bus=SimpleNamespace(async_listen=Mock()))
    with patch(
        "custom_components.xiaomi_miot.dr.async_get",
        return_value=registry,
    ):
        await _handle_device_registry_event(fake_hass)
        listener = fake_hass.bus.async_listen.call_args.args[1]
        await listener(SimpleNamespace(data={"action": "update", "device_id": device_id}))


def _make_registry_device(**kwargs):
    return SimpleNamespace(
        id="device-id",
        identifiers={("xiaomi_miot", "aa:bb:cc:dd:ee:01")},
        name_by_user=None,
        disabled=False,
        **kwargs,
    )


def _make_miot_device():
    miot_device = SimpleNamespace(
        identifiers={("xiaomi_miot", "aa:bb:cc:dd:ee:01")},
        coordinators=[],
        log=Mock(),
    )

    async def init_coordinators():
        miot_device.init_called = True

    miot_device.init_coordinators = init_coordinators
    return miot_device


async def test_registry_event_uses_single_config_entry_id():
    """Avoid deprecated registry.devices and DeviceEntry.config_entries access."""
    device = _make_registry_device(config_entry_id="test-entry")
    registry = Mock(spec=["async_get", "async_remove_device"])
    registry.async_get.return_value = device
    miot_device = _make_miot_device()
    entry = SimpleNamespace(devices={"did": miot_device})

    with patch.dict(
        "custom_components.xiaomi_miot.HassEntry.ALL", {"test-entry": entry}
    ):
        await _fire_device_registry_update(registry, device.id)

    registry.async_get.assert_called_once_with(device.id)
    assert getattr(miot_device, "init_called", False)


async def test_registry_event_falls_back_to_config_entries():
    """Keep working on HA versions without DeviceEntry.config_entry_id."""
    device = _make_registry_device(config_entries={"test-entry"})
    registry = Mock(spec=["async_get", "async_remove_device"])
    registry.async_get.return_value = device
    miot_device = _make_miot_device()
    entry = SimpleNamespace(devices={"did": miot_device})

    with patch.dict(
        "custom_components.xiaomi_miot.HassEntry.ALL", {"test-entry": entry}
    ):
        await _fire_device_registry_update(registry, device.id)

    assert getattr(miot_device, "init_called", False)


async def test_registry_event_ignores_removed_device():
    """A removed device is no longer in the registry and is ignored."""
    registry = Mock(spec=["async_get", "async_remove_device"])
    registry.async_get.return_value = None

    await _fire_device_registry_update(registry, "gone-device-id")

    registry.async_remove_device.assert_not_called()
