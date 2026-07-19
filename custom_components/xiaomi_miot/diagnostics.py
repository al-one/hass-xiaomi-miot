"""Sanitized P2P diagnostics for Home Assistant support bundles.

The diagnostics helper intentionally exposes only non-secret scalars so
that support bundles may be shared without leaking DIDs, account IDs,
LAN hosts, negotiated peer ports, tokens, keys, signatures, route URLs,
or raw media payloads. Ineligible entries report an empty P2P block.
"""

from __future__ import annotations

from typing import Any


async def async_get_config_entry_diagnostics(hass, entry) -> dict[str, Any]:
    """Return the P2P diagnostics block for ``entry``.

    The result shape is::

        {
            "p2p": {
                "enabled": bool,
                "sessions": [{"lens": ..., "generation": ..., ...}, ...],
                "bridges": [{"snapshot_id": ..., "lens": ...}, ...],
            }
        }

    Sessions are sorted by ``lens`` so the support bundle is stable.
    No identifiers, hosts, ports, tokens, keys, signatures, route URLs,
    or raw payloads are emitted at any logging level.
    """
    from custom_components.xiaomi_miot.core.hass_entry import HassEntry

    hass_entry = HassEntry.ALL.get(entry.entry_id)
    if hass_entry is None:
        return {"p2p": {"enabled": False, "sessions": [], "bridges": []}}

    eligible = any(
        getattr(device, "p2p_enabled", False)
        for device in hass_entry.devices.values()
    )
    manager = getattr(hass_entry, "p2p_manager", None)
    if not eligible or manager is None:
        return {"p2p": {"enabled": False, "sessions": [], "bridges": []}}

    sessions = _sanitize_sessions(manager)
    bridges = _sanitize_bridges(manager)
    return {
        "p2p": {
            "enabled": True,
            "sessions": sessions,
            "bridges": bridges,
        }
    }


def _sanitize_sessions(manager) -> list[dict[str, Any]]:
    snapshot = manager.snapshot()
    sanitized = []
    for record in snapshot:
        sanitized.append(
            {
                "lens": record.get("lens"),
                "generation": record.get("generation"),
                "active_leases": record.get("active_leases"),
            }
        )
    sanitized.sort(key=lambda item: item.get("lens") or "")
    return sanitized


def _sanitize_bridges(manager) -> list[dict[str, Any]]:
    bridges = getattr(manager, "_bridges", set())
    sanitized = []
    for bridge in bridges:
        sanitized.append(
            {
                "snapshot_id": getattr(bridge, "snapshot_id", None),
                "lens": getattr(bridge, "lens", None),
            }
        )
    sanitized.sort(key=lambda item: (item.get("lens") or "", item.get("snapshot_id") or ""))
    return sanitized