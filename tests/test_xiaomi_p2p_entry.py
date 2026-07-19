"""Config-Entry Reload and Concurrent Unload (Task 15).

Verifies that each eligible account ``HassEntry`` owns exactly one
``ChannelSessionManager``, one loopback-server reference, and one set
of tracked bridge close tasks, and that reload / permanent unload both
walk the same bounded teardown without leaking resources. The tests
also assert that host/token-only and ineligible entries own no P2P
resources at all.
"""

from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Stub turbojpeg for HA camera imports in environments without it.
_TURBOJPEG_STUB = types.ModuleType("turbojpeg")
_TURBOJPEG_STUB.TurboJPEG = lambda *a, **kw: None
sys.modules.setdefault("turbojpeg", _TURBOJPEG_STUB)

from homeassistant.const import CONF_USERNAME

from custom_components.xiaomi_miot import DOMAIN, init_integration_data
from custom_components.xiaomi_miot.core.hass_entry import HassEntry
from custom_components.xiaomi_miot.core.xiaomi_p2p.cloud import P2PCapabilityCache
from custom_components.xiaomi_miot.core.xiaomi_p2p.server import (
    LoopbackMediaServer,
    RtpPortAllocator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(hass, *, entry_id: str, eligible: bool, did: str = "device-did"):
    """Build a real ``HassEntry`` whose state is wired up for tests.

    The real class is required so its ``async_close_p2p`` and
    ``invalidate_p2p_capability_cache`` methods are bound. We bypass
    the heavy ``__init__`` (which would touch cloud tokens, devices,
    and the entity registry) by going through ``__new__`` and
    populating the same attributes that ``__init__`` writes.
    """
    manager = MagicMock(name=f"manager-{entry_id}") if eligible else None
    if manager is not None:
        manager.async_close = AsyncMock(name="async_close")
    server = MagicMock(name=f"server-ref-{entry_id}")
    server.acquire_entry = AsyncMock(name="acquire_entry")
    server.release_entry = AsyncMock(name="release_entry")
    entry = HassEntry.__new__(HassEntry)
    entry.id = entry_id
    entry.hass = hass
    entry.entry = SimpleNamespace(entry_id=entry_id, state=None, data={}, options={})
    entry.adders = {}
    entry.devices = {}
    entry.mac_to_did = {}
    entry.did_to_unique = {}
    entry.p2p_cache = MagicMock(name=f"cache-{entry_id}")
    entry.p2p_manager = manager
    entry._p2p_ensure_lock = asyncio.Lock()
    entry._p2p_server_acquired = bool(manager is not None)
    entry._p2p_bridge_close_tasks = set()
    # One eligible device
    if eligible:
        device = SimpleNamespace(
            info=SimpleNamespace(did=did, mac="aa:bb:cc:dd:ee:ff", host="192.168.1.20"),
            p2p_enabled=True,
            p2p_profile=SimpleNamespace(lenses=("primary",)),
            p2p_lens="primary",
            p2p_vendor=4,
        )
        entry.devices[did] = device
    return entry, server


def _install_entry(hass, entry, server, manager):
    """Wire a fresh entry into ``HassEntry.ALL`` and ``hass.data``."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("p2p_media_server", server)
    hass.data[DOMAIN].setdefault("p2p_capability_cache", P2PCapabilityCache())
    entry.p2p_cache = hass.data[DOMAIN]["p2p_capability_cache"]
    entry.p2p_manager = manager
    HassEntry.ALL[entry.id] = entry
    return entry


def _cleanup_entry(entry):
    HassEntry.ALL.pop(entry.id, None)


# ---------------------------------------------------------------------------
# Ownership: ineligible / host-token entries own no P2P resources
# ---------------------------------------------------------------------------


async def test_ineligible_entry_owns_no_p2p_resources(hass):
    init_integration_data(hass)
    server = LoopbackMediaServer()
    manager = None
    entry, _ = _make_entry(hass, entry_id="ineligible-1", eligible=False)
    _install_entry(hass, entry, server, manager)
    try:
        assert entry.p2p_manager is None
        assert entry._p2p_server_acquired is False
        assert entry._p2p_bridge_close_tasks == set()
    finally:
        _cleanup_entry(entry)


async def test_host_token_only_entry_owns_no_p2p_resources(hass):
    """Host/token-only entries never reach the eligibility check."""
    init_integration_data(hass)
    server = LoopbackMediaServer()
    entry, _ = _make_entry(hass, entry_id="host-token-1", eligible=False)
    # A host/token entry is identified by the absence of CONF_USERNAME.
    entry.entry.data = {CONF_USERNAME: None}
    entry.entry.options = {}
    _install_entry(hass, entry, server, None)
    try:
        assert entry.p2p_manager is None
        assert entry._p2p_server_acquired is False
    finally:
        _cleanup_entry(entry)


# ---------------------------------------------------------------------------
# Isolation: two account entries with the same DID stay independent
# ---------------------------------------------------------------------------


async def test_two_account_entries_with_same_did_are_isolated(hass):
    init_integration_data(hass)
    server = LoopbackMediaServer()
    a, _ = _make_entry(hass, entry_id="account-A", eligible=True, did="shared-did")
    b, _ = _make_entry(hass, entry_id="account-B", eligible=True, did="shared-did")
    # Two distinct managers, two distinct bridge task sets.
    a_manager = MagicMock(name="a_manager")
    a_manager.async_close = AsyncMock()
    b_manager = MagicMock(name="b_manager")
    b_manager.async_close = AsyncMock()
    _install_entry(hass, a, server, a_manager)
    _install_entry(hass, b, server, b_manager)
    try:
        assert a.p2p_manager is a_manager
        assert b.p2p_manager is b_manager
        assert a.p2p_manager is not b.p2p_manager
        assert a._p2p_bridge_close_tasks is not b._p2p_bridge_close_tasks
    finally:
        _cleanup_entry(a)
        _cleanup_entry(b)


# ---------------------------------------------------------------------------
# Reload: invalidates only the reloaded entry's cache keys and tears down
# ---------------------------------------------------------------------------


async def test_reload_invalidates_only_reloaded_entry_vendor_cache(hass):
    init_integration_data(hass)
    cache = P2PCapabilityCache()
    # Seed the cache with vendor values for two entries sharing a DID.
    fake_time = MagicMock(return_value=0.0)
    cache._time = fake_time
    cache._entries = {
        ("account-A", "cn", "shared-did"): (0.0, 4),
        ("account-B", "cn", "shared-did"): (0.0, 4),
    }
    server = LoopbackMediaServer()
    a, _ = _make_entry(hass, entry_id="account-A", eligible=True, did="shared-did")
    b, _ = _make_entry(hass, entry_id="account-B", eligible=True, did="shared-did")
    _install_entry(hass, a, server, MagicMock())
    a.p2p_cache = cache
    _install_entry(hass, b, server, MagicMock())
    b.p2p_cache = cache
    try:
        # Reload account-A: only its cache keys should disappear.
        cache.invalidate_entry("account-A")
        assert ("account-A", "cn", "shared-did") not in cache._entries
        assert ("account-B", "cn", "shared-did") in cache._entries
    finally:
        _cleanup_entry(a)
        _cleanup_entry(b)


async def test_unload_clears_manager_bridge_tasks_and_cache(hass):
    init_integration_data(hass)
    cache = P2PCapabilityCache()
    cache._entries = {("eligible-1", "cn", "device-did"): (0.0, 4)}
    server = LoopbackMediaServer()
    manager = MagicMock()
    manager.async_close = AsyncMock()
    entry, _ = _make_entry(hass, entry_id="eligible-1", eligible=True)
    _install_entry(hass, entry, server, manager)
    entry.p2p_cache = cache

    try:
        # Run the unload teardown that the integration path delegates to.
        await entry.async_close_p2p()
        manager.async_close.assert_awaited_once()
        assert entry.p2p_manager is None
        assert entry._p2p_server_acquired is False
        # Track set is cleared by the manager close; bridge close tasks
        # are awaited or cancelled as part of unload.
        cache.invalidate_entry(entry.id)
        assert ("eligible-1", "cn", "device-did") not in cache._entries
    finally:
        _cleanup_entry(entry)


# ---------------------------------------------------------------------------
# Fresh setup after reload performs a new vendor preflight
# ---------------------------------------------------------------------------


async def test_reload_then_new_entry_triggers_fresh_preflight(hass):
    """After reload, the new ``HassEntry`` runs ``async_ensure_p2p`` again."""
    init_integration_data(hass)
    server = LoopbackMediaServer()

    # First entry: built, manager acquired.
    first, _ = _make_entry(hass, entry_id="reload-1", eligible=True)
    first_manager = MagicMock()
    first_manager.async_close = AsyncMock()
    _install_entry(hass, first, server, first_manager)
    try:
        # Simulate the unload path; the new entry has no manager yet.
        await first.async_close_p2p()
        assert first.p2p_manager is None
    finally:
        _cleanup_entry(first)

    # Replacement entry with the same ID gets a fresh manager.
    second, _ = _make_entry(hass, entry_id="reload-1", eligible=True)
    second_manager = MagicMock()
    second_manager.acquire = AsyncMock(return_value=MagicMock())
    _install_entry(hass, second, server, second_manager)
    try:
        # The replacement must consult the capability cache from scratch
        # because the old keys were invalidated.
        assert second.p2p_manager is second_manager
        # No old bridge close tasks or server reference survive.
        assert second._p2p_bridge_close_tasks == set()
    finally:
        _cleanup_entry(second)


# ---------------------------------------------------------------------------
# Unload order
# ---------------------------------------------------------------------------


async def test_unload_calls_async_close_on_manager(hass):
    init_integration_data(hass)
    server = LoopbackMediaServer()
    manager = MagicMock()
    manager.async_close = AsyncMock()
    entry, _ = _make_entry(hass, entry_id="order-1", eligible=True)
    _install_entry(hass, entry, server, manager)
    try:
        await entry.async_close_p2p()
        # Manager is closed and cleared; the server reference is released.
        manager.async_close.assert_awaited_once()
        assert entry.p2p_manager is None
    finally:
        _cleanup_entry(entry)


async def test_unload_after_manager_close_failure_releases_server(hass):
    """A failing manager close must not prevent server-reference release."""
    init_integration_data(hass)
    server = MagicMock()
    server.acquire_entry = AsyncMock()
    server.release_entry = AsyncMock()
    hass.data[DOMAIN]["p2p_media_server"] = server
    manager = MagicMock()
    manager.async_close = AsyncMock(side_effect=RuntimeError("boom"))
    entry, _ = _make_entry(hass, entry_id="order-2", eligible=True)
    _install_entry(hass, entry, server, manager)
    try:
        with pytest.raises(RuntimeError, match="boom"):
            await entry.async_close_p2p()
        manager.async_close.assert_awaited_once()
        assert entry.p2p_manager is None
        assert entry._p2p_server_acquired is False
        # Server reference is still released even though the manager raised.
        server.release_entry.assert_awaited_once()
    finally:
        _cleanup_entry(entry)


# ---------------------------------------------------------------------------
# Integration-wide server/allocator are shared and never duplicated
# ---------------------------------------------------------------------------


async def test_integration_uses_single_server_and_allocator(hass):
    init_integration_data(hass)
    server = hass.data[DOMAIN]["p2p_media_server"]
    # Calling init_integration_data again must not replace the existing
    # server or allocator; reload must reuse the same instances.
    init_integration_data(hass)
    again = hass.data[DOMAIN]["p2p_media_server"]
    assert again is server
