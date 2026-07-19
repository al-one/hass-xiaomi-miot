"""Sanitized P2P diagnostics (Task 16)."""

from __future__ import annotations

import asyncio
import logging
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_TURBOJPEG_STUB = types.ModuleType("turbojpeg")
_TURBOJPEG_STUB.TurboJPEG = lambda *a, **kw: None
sys.modules.setdefault("turbojpeg", _TURBOJPEG_STUB)

from custom_components.xiaomi_miot import DOMAIN, init_integration_data
from custom_components.xiaomi_miot.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.xiaomi_miot.core.hass_entry import HassEntry
from custom_components.xiaomi_miot.core.xiaomi_p2p import (
    DEFAULT_P2P_PROFILE,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.cloud import P2PCapabilityCache
from custom_components.xiaomi_miot.core.xiaomi_p2p.server import LoopbackMediaServer


PROHIBITED = {
    "did-secret",
    "192.168.1.20",
    "41000",
    "service-token",
    "private-key",
    "device-public-key",
    "cloud-signature",
    "route-token",
    "auth=",
    "raw-media-payload",
    "bootstrap",
    "signature",
    "client-private",
    "public-key",
    "pass-token",
    "service-token",
}


def assert_sanitized(value) -> None:
    text = repr(value)
    for secret in PROHIBITED:
        assert secret not in text, (
            f"prohibited token {secret!r} found in diagnostics output"
        )


def _make_entry(hass, *, entry_id: str, eligible: bool):
    manager = MagicMock(name=f"manager-{entry_id}") if eligible else None
    if manager is not None:
        manager.snapshot = MagicMock(return_value=tuple())
    entry = HassEntry.__new__(HassEntry)
    entry.id = entry_id
    entry.hass = hass
    entry.entry = SimpleNamespace(entry_id=entry_id, state=None, data={}, options={})
    entry.adders = {}
    entry.devices = {}
    entry.mac_to_did = {}
    entry.did_to_unique = {}
    entry.p2p_cache = P2PCapabilityCache()
    entry.p2p_manager = manager
    entry._p2p_ensure_lock = asyncio.Lock()
    entry._p2p_server_acquired = bool(manager is not None)
    entry._p2p_bridge_close_tasks = set()
    return entry


def _install_entry(hass, entry):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("p2p_media_server", LoopbackMediaServer())
    hass.data[DOMAIN].setdefault("p2p_capability_cache", P2PCapabilityCache())
    entry.p2p_cache = hass.data[DOMAIN]["p2p_capability_cache"]
    HassEntry.ALL[entry.id] = entry


def _cleanup_entry(entry):
    HassEntry.ALL.pop(entry.id, None)


def _config_entry(entry_id: str):
    return SimpleNamespace(
        entry_id=entry_id,
        state=None,
        data={},
        options={},
    )


async def test_ineligible_entry_returns_empty_p2p_block(hass):
    init_integration_data(hass)
    entry = _make_entry(hass, entry_id="diag-ineligible", eligible=False)
    _install_entry(hass, entry)
    try:
        result = await async_get_config_entry_diagnostics(
            hass, _config_entry(entry.id)
        )
        assert result["p2p"]["enabled"] is False
        assert result["p2p"]["sessions"] == []
        assert result["p2p"]["bridges"] == []
        assert_sanitized(result)
    finally:
        _cleanup_entry(entry)


async def test_eligible_entry_advertises_enabled_flag(hass):
    init_integration_data(hass)
    entry = _make_entry(hass, entry_id="diag-eligible", eligible=True)
    device = SimpleNamespace(
        p2p_enabled=True,
        p2p_profile=DEFAULT_P2P_PROFILE,
        p2p_lens="primary",
    )
    entry.devices["device-did"] = device
    _install_entry(hass, entry)
    try:
        result = await async_get_config_entry_diagnostics(
            hass, _config_entry(entry.id)
        )
        assert result["p2p"]["enabled"] is True
        assert_sanitized(result)
    finally:
        _cleanup_entry(entry)


async def test_session_snapshot_carries_only_sanitized_scalars(hass):
    init_integration_data(hass)
    entry = _make_entry(hass, entry_id="diag-snapshot", eligible=True)
    entry.p2p_manager.snapshot = MagicMock(
        return_value=(
            {
                "lens": "primary",
                "generation": 1,
                "active_leases": 1,
                "transport": "auto",
                "raw_quality": 0,
            },
        )
    )
    device = SimpleNamespace(
        p2p_enabled=True,
        p2p_profile=DEFAULT_P2P_PROFILE,
        p2p_lens="primary",
    )
    entry.devices["device-did"] = device
    _install_entry(hass, entry)
    try:
        result = await async_get_config_entry_diagnostics(
            hass, _config_entry(entry.id)
        )
        sessions = result["p2p"]["sessions"]
        assert len(sessions) == 1
        session = sessions[0]
        assert session["lens"] == "primary"
        assert "did" not in session
        assert "host" not in session
        assert "port" not in session
        assert "token" not in session
        assert "key" not in session
        assert "bootstrap" not in session
        assert_sanitized(session)
    finally:
        _cleanup_entry(entry)


async def test_sessions_are_sorted_by_lens(hass):
    init_integration_data(hass)
    entry = _make_entry(hass, entry_id="diag-sort", eligible=True)
    entry.p2p_manager.snapshot = MagicMock(
        return_value=(
            {"lens": "secondary", "generation": 1, "active_leases": 0},
            {"lens": "primary", "generation": 1, "active_leases": 0},
        )
    )
    device = SimpleNamespace(
        p2p_enabled=True,
        p2p_profile=DEFAULT_P2P_PROFILE,
        p2p_lens="primary",
    )
    entry.devices["device-did"] = device
    _install_entry(hass, entry)
    try:
        result = await async_get_config_entry_diagnostics(
            hass, _config_entry(entry.id)
        )
        sessions = result["p2p"]["sessions"]
        assert [s["lens"] for s in sessions] == ["primary", "secondary"]
    finally:
        _cleanup_entry(entry)


async def test_bridge_snapshot_is_sanitized(hass):
    init_integration_data(hass)
    entry = _make_entry(hass, entry_id="diag-bridge", eligible=True)

    class _FakeBridge:
        # Default object identity hash; matches the un-keyed object used
        # by the manager's set bookkeeping.
        def __init__(self, snapshot_id: str, lens: str) -> None:
            self.snapshot_id = snapshot_id
            self.lens = lens

    fake_bridge = _FakeBridge("opaque-bridge-id-1", "primary")
    entry.p2p_manager._bridges = {fake_bridge}
    device = SimpleNamespace(
        p2p_enabled=True,
        p2p_profile=DEFAULT_P2P_PROFILE,
        p2p_lens="primary",
    )
    entry.devices["device-did"] = device
    _install_entry(hass, entry)
    try:
        result = await async_get_config_entry_diagnostics(
            hass, _config_entry(entry.id)
        )
        bridges = result["p2p"]["bridges"]
        assert bridges == [{"snapshot_id": "opaque-bridge-id-1", "lens": "primary"}]
        assert_sanitized(bridges)
    finally:
        _cleanup_entry(entry)


async def test_prohibited_tokens_never_appear(hass):
    init_integration_data(hass)
    entry = _make_entry(hass, entry_id="diag-prohibited", eligible=True)
    entry.p2p_manager.snapshot = MagicMock(
        return_value=(
            {
                "lens": "primary",
                "generation": 1,
                "active_leases": 0,
            },
        )
    )
    device = SimpleNamespace(
        p2p_enabled=True,
        p2p_profile=DEFAULT_P2P_PROFILE,
        p2p_lens="primary",
    )
    entry.devices["device-did"] = device
    _install_entry(hass, entry)
    try:
        result = await async_get_config_entry_diagnostics(
            hass, _config_entry(entry.id)
        )
        assert_sanitized(result)
    finally:
        _cleanup_entry(entry)


async def test_diagnostics_emit_no_request_or_url_log_records(hass, caplog):
    init_integration_data(hass)
    entry = _make_entry(hass, entry_id="diag-logging", eligible=True)
    _install_entry(hass, entry)
    try:
        with caplog.at_level(logging.DEBUG):
            result = await async_get_config_entry_diagnostics(
                hass, _config_entry(entry.id)
            )
        for record in caplog.records:
            text = record.getMessage()
            assert "path_qs" not in text
            assert "rel_url" not in text
            assert "raw-media-payload" not in text
            assert "auth=" not in text
            assert "http://" not in text
        assert_sanitized(result)
    finally:
        _cleanup_entry(entry)
