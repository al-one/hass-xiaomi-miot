"""Saved-map list / backup-map list helpers for xiaomi.vacuum.ov42gl (H50 Pro).

This is the device's "map management" screen in the Xiaomi Home app: the set
of maps it has saved (usually one per floor) plus, for whichever one is
currently active, the single automatic backup kept for it. Reverse-engineered
from the app's own map-list plugin for interoperability, the same way as
core/vacuum_zones.py.

Both properties live on a separate MIoT service from the main vacuum one
(SIID 10, "vacuum-map" - entirely excluded from this integration's generic
property/action pipeline via `exclude_miot_services` in device_customizes.py,
same as `restricted_sweep_areas`/`room_information` are excluded from the main
service), so - like zones/rooms - they're read and acted on directly rather
than through a converter; see MiotOv42glVacuumEntity._async_read_maps in
vacuum.py.

Real shapes below were confirmed against a live property snapshot of the
device (H50/results/before.json in the project's own tooling, not part of
this repo), not guessed from the spec's bare "string" format:

    map-management (SIID10 PIID5):
        {"index": 1785640878, "map_array": [
            {"map_name": "", "obj_name": "<uid>/<did>/2", "map_id": 1, "temp": 0, "is_current": true},
        ]}

    backup-map-list (SIID10 PIID13):
        {"index": 1785640880, "backup_map_arr": [
            {"map_name": "1785635606", "obj_name": "<uid>/<did>/8", "map_id": -2, "backup_id": 1},
        ]}

`obj_name` (both) is only useful for downloading the rendered map file (see
core/vacuum_map.py) - not needed for listing/managing maps, so it's carried
through unparsed rather than dropped, in case a future consumer wants it.
"""
import json

MAP_SIID = 10
MAP_MANAGEMENT_PIID = 5
BACKUP_MAP_LIST_PIID = 13

# Same limit the app enforces client-side (`isMapLimited`, checking the count
# of non-temporary maps) on the number of saved maps - not confirmed whether
# the device also enforces this server-side.
MAX_SAVED_MAPS = 4


def _loads(raw) -> dict:
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (TypeError, ValueError):
        return {}


def parse_map_management(raw) -> list:
    """`map-management` -> its `map_array` list, each entry
    `{'map_id', 'map_name', 'obj_name', 'temp', 'is_current'}`."""
    return list(_loads(raw).get('map_array') or [])


def parse_backup_map_list(raw) -> list:
    """`backup-map-list` -> its `backup_map_arr` list, each entry
    `{'map_id', 'map_name', 'obj_name', 'backup_id'}`.

    `backup_id` is the id of the *saved* map (a `map_array` entry's own
    `map_id`) this backup belongs to - matched in the app by comparing
    `backup.backup_id == map.map_id` (plugin_main2.bundle, ~line 128292:
    `item.backup = backupMaps.find(it => it.backup_id == item.map_id)`), see
    `find_backup_for_map`. The backup entry's *own* `map_id` (-2 in the
    sample above) is a fixed sentinel, not a per-backup identifier - it's the
    value the app actually sends to the `restore-map` action (traced through
    `BackupMapPage`/`BackupMapView` to `doAction(RESTORE_MAP, props.map_id)`,
    ~line 148155, where `props` is a spread of the matched backup entry).
    """
    return list(_loads(raw).get('backup_map_arr') or [])


def is_temp_map(entry: dict) -> bool:
    """Matches the app's own `item.temp = item.map_id == 0 || item.temp == 1`
    (plugin_main2.bundle, ~line 128283) - the live map being built, not yet
    saved into `map_array` as its own entry."""
    return entry.get('map_id') == 0 or entry.get('temp') == 1


def map_label(entry: dict) -> str:
    """Display label for a saved map. `map_name` is often an empty string
    (device default, before the user renames it) - falls back to the id,
    same idea as the room list's `f'Room {id}'` fallback in vacuum.py."""
    name = (entry.get('map_name') or '').strip()
    return name or f'Map {entry.get("map_id")}'


def saved_maps(maps: list) -> list:
    """Non-temporary maps only - the ones that can be applied/renamed/deleted."""
    return [m for m in (maps or []) if not is_temp_map(m)]


def find_current_map(maps: list):
    return next((m for m in (maps or []) if m.get('is_current')), None)


def find_backup_for_map(map_id, backups: list):
    """The one backup entry belonging to `map_id`, if any - see
    parse_backup_map_list for the `backup_id`/`map_id` relationship."""
    if map_id is None:
        return None
    return next((b for b in (backups or []) if b.get('backup_id') == map_id), None)


def set_map_name_payload(map_id, name: str) -> str:
    """Exact JSON shape confirmed in plugin_main2.bundle (~line 128824, the
    map-rename screen's `onConfirm`): `params = JSON.stringify({map_id,
    map_name: name})`, passed to the `set-map-name` action."""
    return json.dumps({'map_id': map_id, 'map_name': name})
