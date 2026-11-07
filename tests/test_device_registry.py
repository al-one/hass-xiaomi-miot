"""Tests for Xiaomi MIoT device registry compatibility."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

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

    miot_device.async_init = init_coordinators
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


@pytest.mark.parametrize("owner", ["current", "legacy"])
@pytest.mark.parametrize("disabled", [False, True])
@pytest.mark.parametrize("identifiers", [
    [("other", "foreign"), ("xiaomi_miot", "aa:bb:cc:dd:ee:01")],
    [("xiaomi_miot", "unrelated"), ("xiaomi_miot", "aa:bb:cc:dd:ee:01")],
])
async def test_registry_event_matches_owned_identifier(owner, disabled, identifiers):
    """Linking identifiers must not hide a runtime device from registry events."""
    device = _make_registry_device(**(
        {"config_entry_id": "test-entry"} if owner == "current"
        else {"config_entries": {"other-entry", "test-entry"}}
    ))
    # Preserve order deliberately to exercise both first-identifier failure modes.
    device.identifiers = identifiers
    device.disabled = disabled
    registry = Mock(spec=["async_get", "async_remove_device"])
    registry.async_get.return_value = device
    miot_device = _make_miot_device()
    miot_device.async_init = AsyncMock()
    miot_device.async_unload = AsyncMock()
    miot_device.coordinators = [object()] if disabled else []
    wrong_device = _make_miot_device()
    wrong_device.async_init = AsyncMock()
    wrong_device.async_unload = AsyncMock()
    entries = {
        "test-entry": SimpleNamespace(devices={"did": miot_device}),
        "wrong-entry": SimpleNamespace(devices={"did": wrong_device}),
    }
    with patch.dict("custom_components.xiaomi_miot.HassEntry.ALL", entries, clear=True):
        await _fire_device_registry_update(registry, device.id)
    if disabled:
        miot_device.async_unload.assert_awaited_once_with(unload_spec=False)
        miot_device.async_init.assert_not_awaited()
    else:
        miot_device.async_init.assert_awaited_once_with()
        miot_device.async_unload.assert_not_awaited()
    wrong_device.async_init.assert_not_awaited()
    wrong_device.async_unload.assert_not_awaited()


@pytest.mark.parametrize("identifiers", [set(), {("other", "foreign")}])
async def test_registry_event_ignores_non_miot_identifiers(identifiers):
    device = _make_registry_device(config_entry_id="test-entry")
    device.identifiers = identifiers
    registry = Mock(spec=["async_get", "async_remove_device"])
    registry.async_get.return_value = device
    miot_device = _make_miot_device()
    with patch.dict("custom_components.xiaomi_miot.HassEntry.ALL", {
        "test-entry": SimpleNamespace(devices={"did": miot_device}),
    }, clear=True):
        await _fire_device_registry_update(registry, device.id)
    assert not getattr(miot_device, "init_called", False)
    registry.async_remove_device.assert_not_called()


@pytest.mark.parametrize("disabled", [False, True])
async def test_linked_registry_device_disable_and_enable_events(hass, disabled):
    """Exercise real HA registry ownership and bus dispatch for both update paths."""
    from custom_components.xiaomi_miot import _handle_device_registry_event

    entry = MockConfigEntry(domain="xiaomi_miot")
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    miot_device = _make_device(hass, unique_id="aa:bb:cc:dd:ee:01", entry_id=entry.entry_id)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=miot_device.identifiers | {("other", "foreign")},
    )
    if not disabled:
        registry.async_update_device(device.id, disabled_by=dr.DeviceEntryDisabler.USER)
    await hass.async_block_till_done()
    coordinator = SimpleNamespace(async_shutdown=AsyncMock())
    if disabled:
        miot_device.coordinators.append(coordinator)
    with patch.dict("custom_components.xiaomi_miot.HassEntry.ALL", {
        entry.entry_id: SimpleNamespace(devices={"did": miot_device}),
    }, clear=True), patch.object(miot_device, "async_init", new_callable=AsyncMock) as init:
        await _handle_device_registry_event(hass)
        registry.async_update_device(
            device.id, disabled_by=dr.DeviceEntryDisabler.USER if disabled else None
        )
        await hass.async_block_till_done()
        if disabled:
            coordinator.async_shutdown.assert_awaited_once_with()
            init.assert_not_awaited()
        else:
            init.assert_awaited_once_with()
            coordinator.async_shutdown.assert_not_awaited()
    assert registry.async_get(device.id).identifiers == device.identifiers


@pytest.mark.parametrize("filter_type", ["include", "exclude"])
@pytest.mark.parametrize("identifiers", [
    [("other", "foreign"), ("xiaomi_miot", "aa:bb:cc:dd:ee:01")],
    [("xiaomi_miot", "unrelated"), ("xiaomi_miot", "aa:bb:cc:dd:ee:01")],
])
async def test_remove_linked_device_updates_owning_account_filter(filter_type, identifiers):
    from custom_components.xiaomi_miot import async_remove_config_entry_device

    config_entry = SimpleNamespace(data={"filter_did": filter_type, "did_list": ["target", "keep"]})
    entry = SimpleNamespace(entry=config_entry)
    async def lookup(*, mac):
        return {"did": "target"} if mac == "AA:BB:CC:DD:EE:01" else None
    entry.get_cloud_device = AsyncMock(side_effect=lookup)
    device = SimpleNamespace(id="device-id", identifiers=identifiers)
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=Mock()))
    registry = Mock()
    with patch("custom_components.xiaomi_miot.HassEntry.init", return_value=entry), patch(
        "custom_components.xiaomi_miot.dr.async_get", return_value=registry
    ):
        assert await async_remove_config_entry_device(hass, config_entry, device)
    data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert set(data["did_list"]) == ({"target", "keep"} if filter_type == "exclude" else {"keep"})
    assert config_entry.data["did_list"] == ["target", "keep"]
    registry.async_remove_device.assert_called_once_with(device.id)


@pytest.mark.parametrize("identifiers", [set(), {("other", "foreign")}, {("xiaomi_miot", "unknown")}])
async def test_remove_device_without_account_match_preserves_filter(identifiers):
    from custom_components.xiaomi_miot import async_remove_config_entry_device

    config_entry = SimpleNamespace(data={"filter_did": "include", "did_list": ["keep"]})
    entry = SimpleNamespace(entry=config_entry, get_cloud_device=AsyncMock(return_value=None))
    device = SimpleNamespace(id="device-id", identifiers=identifiers)
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=Mock()))
    registry = Mock()
    with patch("custom_components.xiaomi_miot.HassEntry.init", return_value=entry), patch(
        "custom_components.xiaomi_miot.dr.async_get", return_value=registry
    ):
        assert await async_remove_config_entry_device(hass, config_entry, device)
    hass.config_entries.async_update_entry.assert_not_called()
    registry.async_remove_device.assert_called_once_with(device.id)


@pytest.mark.parametrize("owner", ["current", "legacy"])
async def test_registry_event_does_not_match_another_accounts_runtime(owner):
    device = _make_registry_device(**(
        {"config_entry_id": "other-entry"} if owner == "current"
        else {"config_entries": {"other-entry"}}
    ))
    device.identifiers.add(("other", "foreign"))
    registry = Mock(spec=["async_get", "async_remove_device"])
    registry.async_get.return_value = device
    miot_device = _make_miot_device()
    with patch.dict("custom_components.xiaomi_miot.HassEntry.ALL", {
        "test-entry": SimpleNamespace(devices={"did": miot_device}),
    }, clear=True):
        await _fire_device_registry_update(registry, device.id)
    assert not getattr(miot_device, "init_called", False)


async def test_registry_rename_delete_unloads_linked_device():
    device = _make_registry_device(config_entry_id="test-entry")
    device.identifiers.add(("other", "foreign"))
    device.name_by_user = "delete"
    registry = Mock(spec=["async_get", "async_remove_device"])
    registry.async_get.return_value = device
    miot_device = _make_miot_device()
    miot_device.async_unload = AsyncMock()
    with patch.dict("custom_components.xiaomi_miot.HassEntry.ALL", {
        "test-entry": SimpleNamespace(devices={"did": miot_device}),
    }, clear=True):
        await _fire_device_registry_update(registry, device.id)
    miot_device.async_unload.assert_awaited_once_with()
    registry.async_remove_device.assert_called_once_with(device.id)


@pytest.mark.parametrize("disable_before_first_poll", [False, True])
async def test_linked_device_continuous_disable_enable(hass, load_miot_spec, disable_before_first_poll):
    """Restart polling on the same runtime without discarding live entity specs."""
    from datetime import timedelta
    from homeassistant.util import dt
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    from custom_components.xiaomi_miot import _handle_device_registry_event
    from custom_components.xiaomi_miot.core.hass_entry import HassEntry
    from custom_components.xiaomi_miot.core.miot_spec import MiotSpec

    entry = MockConfigEntry(domain="xiaomi_miot", data={"scan_interval": 10})
    entry.add_to_hass(hass)
    runtime_entry = HassEntry(hass, entry)
    source_spec = load_miot_spec("xiaomi.airp.mb5.json")
    info = DeviceInfo({"did": "test-device", "mac": "aa:bb:cc:dd:ee:01",
                       "name": "Test Device", "model": "test.device.model", "urn": source_spec.type})
    device = Device(info, runtime_entry)
    runtime_entry.devices[info.unique_id] = device
    registry = dr.async_get(hass)
    registered = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers=device.identifiers | {("other", "foreign")},
    )
    listener = Mock()
    device.add_listener(listener)
    async def poll(*args, **kwargs):
        device.dispatch({"sample": True})
        return {"sample": True}

    with patch.dict(HassEntry.ALL, {entry.entry_id: runtime_entry}, clear=True), patch.object(
        MiotSpec, "async_from_type", new=AsyncMock(return_value=source_spec)
    ) as fetch, patch.object(device, "update_miot_status", side_effect=poll) as network:
        await device.async_init()
        await _handle_device_registry_event(hass)
        original_spec = device.spec
        original_converters = tuple(device.converters)
        original_identifiers = registered.identifiers
        assert device.coordinators and device.main_coordinators

        async def advance(seconds):
            async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=seconds))
            await hass.async_block_till_done()

        if not disable_before_first_poll:
            await advance(2)
            assert network.await_count > 0
        for cycle in range(2):
            stopped = tuple(device.coordinators)
            registry.async_update_device(registered.id, disabled_by=dr.DeviceEntryDisabler.USER)
            await hass.async_block_till_done()
            count = network.await_count
            await advance(30)
            assert network.await_count == count
            registry.async_update_device(registered.id, disabled_by=None)
            await hass.async_block_till_done()
            await advance(2)
            assert network.await_count > count, "Polling must resume after disabling the same runtime"
            resumed = network.await_count
            await advance(15)
            assert network.await_count > resumed, "Periodic polling must remain scheduled"
            assert device.spec is original_spec
            assert tuple(device.converters) == original_converters
            assert all(coo not in stopped for coo in device.coordinators)
            assert device.main_coordinators
            assert all(coo in device.coordinators for coo in device.main_coordinators)
            assert device._unsub_purge is not None
            assert runtime_entry.devices[info.unique_id] is device
            assert registry.async_get(registered.id).identifiers == original_identifiers
            fetch.assert_awaited_once()
        assert listener.call_count > 0
        assert device.listeners == [listener]
        with patch.object(hass.config_entries, "async_forward_entry_unload", return_value=True):
            assert await runtime_entry.async_unload()
        assert entry.entry_id not in HassEntry.ALL
        assert device.spec is None
        assert device.model not in hass.data["xiaomi_miot"]["miot_specs"]
        assert not device.coordinators and not device.main_coordinators
        assert device._unsub_purge is None
        count = network.await_count
        await advance(60)
        assert network.await_count == count
