"""Tests for Xiaomi MIoT device registry compatibility."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.xiaomi_miot import _handle_device_registry_event, HassEntry, DOMAIN

from custom_components.xiaomi_miot.core.device import Device, DeviceInfo


@pytest.mark.parametrize('modern', [False, True])
@pytest.mark.parametrize('found', [False, True])
async def test_registry_event_uses_public_lookup_and_preserves_disable(hass, modern, found):
    identifiers = {(DOMAIN, 'test-device')}
    miot_device = SimpleNamespace(
        identifiers=identifiers, coordinators=[object()],
        async_unload=AsyncMock(), log=Mock(),
    )

    class ModernEntry:
        id = 'test-device'
        config_entry_id = 'test-entry'
        name_by_user = None
        disabled = True

        @property
        def config_entries(self):
            raise AssertionError('Deprecated config_entries must not be read')

    device = ModernEntry() if modern else SimpleNamespace(
        id='test-device', config_entries={'test-entry'},
        name_by_user=None, disabled=True,
    )
    device.identifiers = identifiers

    class Registry:
        async_get = Mock(return_value=device if found else None)

        @property
        def devices(self):
            raise AssertionError('Deprecated devices mapping must not be read')

    registry = Registry()
    listener = Mock()
    entry = SimpleNamespace(devices={'test-device': miot_device})
    with (
        patch('custom_components.xiaomi_miot.dr.async_get', return_value=registry),
        patch.object(type(hass.bus), 'async_listen', listener),
        patch.dict(HassEntry.ALL, {'test-entry': entry}),
    ):
        await _handle_device_registry_event(hass)
        handler = listener.call_args.args[1]
        await handler(SimpleNamespace(data={'action': 'update', 'device_id': 'test-device'}))
        await handler(SimpleNamespace(data={'action': 'update'}))
    registry.async_get.assert_called_once_with('test-device')
    assert miot_device.async_unload.await_count == int(found)


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
