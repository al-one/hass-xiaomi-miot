"""Pure-logic tests for the xiaomi.vacuum.ov42gl (H50 Pro) saved-map list /
backup-map list helpers - core/vacuum_maps.py doesn't import Home Assistant
at all, so these run without the `hass`/`make_device` fixtures used by
test_xiaomi_vacuum_ov42gl.py.
"""
import json

from custom_components.xiaomi_miot.core import vacuum_maps

# Real property snapshot captured from a live xiaomi.vacuum.ov42gl (H50 Pro),
# one saved map with no backup taken yet for it - see
# core/vacuum_maps.py's module docstring.
CONFIRMED_MAP_MANAGEMENT_SAMPLE = {
    "index": 1785640878,
    "map_array": [
        {"map_name": "", "obj_name": "6886224559/1190919101/2", "map_id": 1, "temp": 0, "is_current": True},
    ],
}
CONFIRMED_BACKUP_MAP_LIST_SAMPLE = {
    "index": 1785640880,
    "backup_map_arr": [
        {"map_name": "1785635606", "obj_name": "6886224559/1190919101/8", "map_id": -2, "backup_id": 1},
    ],
}


def test_parse_map_management_matches_confirmed_hardware_sample():
    maps = vacuum_maps.parse_map_management(json.dumps(CONFIRMED_MAP_MANAGEMENT_SAMPLE))
    assert maps == CONFIRMED_MAP_MANAGEMENT_SAMPLE["map_array"]


def test_parse_backup_map_list_matches_confirmed_hardware_sample():
    backups = vacuum_maps.parse_backup_map_list(json.dumps(CONFIRMED_BACKUP_MAP_LIST_SAMPLE))
    assert backups == CONFIRMED_BACKUP_MAP_LIST_SAMPLE["backup_map_arr"]


def test_parse_helpers_handle_missing_or_invalid_values():
    assert vacuum_maps.parse_map_management(None) == []
    assert vacuum_maps.parse_map_management("not json") == []
    assert vacuum_maps.parse_backup_map_list(None) == []
    assert vacuum_maps.parse_backup_map_list("not json") == []


def test_is_temp_map_matches_the_apps_own_check():
    assert vacuum_maps.is_temp_map({"map_id": 0, "temp": 0}) is True
    assert vacuum_maps.is_temp_map({"map_id": 5, "temp": 1}) is True
    assert vacuum_maps.is_temp_map({"map_id": 1, "temp": 0}) is False


def test_map_label_falls_back_to_id_when_name_is_empty():
    assert vacuum_maps.map_label({"map_id": 1, "map_name": ""}) == "Map 1"
    assert vacuum_maps.map_label({"map_id": 2, "map_name": "  "}) == "Map 2"
    assert vacuum_maps.map_label({"map_id": 3, "map_name": "Living Room"}) == "Living Room"


def test_saved_maps_excludes_temporary_entries():
    maps = [
        {"map_id": 0, "temp": 0, "map_name": ""},  # live/unsaved map
        {"map_id": 1, "temp": 0, "map_name": "Floor 1"},
        {"map_id": 2, "temp": 1, "map_name": "Floor 2"},
    ]
    assert vacuum_maps.saved_maps(maps) == [maps[1]]


def test_find_current_map_returns_the_flagged_entry():
    maps = CONFIRMED_MAP_MANAGEMENT_SAMPLE["map_array"]
    assert vacuum_maps.find_current_map(maps) == maps[0]
    assert vacuum_maps.find_current_map([]) is None
    assert vacuum_maps.find_current_map([{"map_id": 1, "is_current": False}]) is None


def test_find_backup_for_map_matches_backup_id_against_the_maps_own_id():
    # backup_id (1) matches the saved map's map_id (1), NOT the backup's own
    # map_id (-2, a fixed sentinel - see the module docstring).
    backup = vacuum_maps.find_backup_for_map(1, CONFIRMED_BACKUP_MAP_LIST_SAMPLE["backup_map_arr"])
    assert backup == CONFIRMED_BACKUP_MAP_LIST_SAMPLE["backup_map_arr"][0]
    assert vacuum_maps.find_backup_for_map(999, CONFIRMED_BACKUP_MAP_LIST_SAMPLE["backup_map_arr"]) is None
    assert vacuum_maps.find_backup_for_map(None, CONFIRMED_BACKUP_MAP_LIST_SAMPLE["backup_map_arr"]) is None


def test_set_map_name_payload_matches_the_apps_own_write_shape():
    # Confirmed in plugin_main2.bundle (~line 128824): params = JSON.stringify({map_id, map_name}).
    payload = vacuum_maps.set_map_name_payload(1, "Living Room")
    assert json.loads(payload) == {"map_id": 1, "map_name": "Living Room"}
