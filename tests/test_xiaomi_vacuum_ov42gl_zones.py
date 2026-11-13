"""Pure-logic tests for the xiaomi.vacuum.ov42gl (H50 Pro) virtual wall /
restricted zone editor helpers - core/vacuum_zones.py doesn't import Home
Assistant at all, so these run without the `hass`/`make_device` fixtures
used by test_xiaomi_vacuum_ov42gl.py.
"""
import json

from custom_components.xiaomi_miot.core import vacuum_zones


def test_rect_to_fb_point_matches_app_corner_order():
    # upperLeft, lowerLeft, lowerRight, upperRight - "upper" = larger world_y,
    # "right" = larger world_x. Regardless of which corner was clicked first.
    assert vacuum_zones.rect_to_fb_point(0, 0, 100, 200) == [0, 200, 0, 0, 100, 0, 100, 200]
    assert vacuum_zones.rect_to_fb_point(100, 200, 0, 0) == [0, 200, 0, 0, 100, 0, 100, 200]


def test_build_and_remove_zone_lists_round_trip():
    regions, walls = vacuum_zones.build_zone_lists(
        [], [], vacuum_zones.ZONE_TYPE_NO_MOP_ONLY, 0, 0, 100, 100,
    )
    assert len(regions) == 1 and regions[0]["fb_attr"] == vacuum_zones.FB_ATTR_NO_MOP_ONLY

    regions, walls = vacuum_zones.build_zone_lists(
        regions, walls, vacuum_zones.ZONE_TYPE_WALL, 0, 0, 50, 50,
    )
    assert len(walls) == 1

    options = vacuum_zones.describe_zones(regions, walls)
    assert options == [("No Mop Only #0", "region", 0), ("Virtual Wall #0", "wall", 0)]

    regions_after, walls_after = vacuum_zones.remove_zone_lists(regions, walls, "wall", 0)
    assert regions_after == regions
    assert walls_after == []


def test_build_zone_lists_enforces_the_combined_shape_limit():
    walls = [{"wall_points": [0, 0, 1, 1]}] * vacuum_zones.MAX_TOTAL_SHAPES
    try:
        vacuum_zones.build_zone_lists([], walls, vacuum_zones.ZONE_TYPE_WALL, 0, 0, 1, 1)
        assert False, "expected ValueError once MAX_TOTAL_SHAPES is reached"
    except ValueError:
        pass


def test_remove_zone_lists_raises_when_index_is_stale():
    try:
        vacuum_zones.remove_zone_lists([], [], "region", 0)
        assert False, "expected ValueError for an out-of-range index"
    except ValueError:
        pass


def test_zone_write_payloads_renumber_ids_by_position():
    regions = [{"fb_point": [0, 0, 0, 1, 1, 1, 1, 0], "fb_attr": 0}]
    walls = [{"wall_points": [0, 0, 1, 1]}]
    regions_payload, walls_payload = vacuum_zones.zone_write_payloads(regions, walls)
    assert json.loads(regions_payload) == {
        "forbidden_regions": [{"id": 0, "fb_point": [0, 0, 0, 1, 1, 1, 1, 0], "fb_attr": 0}],
    }
    assert json.loads(walls_payload) == {
        "restricted_walls": [{"id": 0, "wall_points": [0, 0, 1, 1]}],
    }


def test_parse_zone_property_values_matches_the_devices_own_read_write_shape():
    # This is the exact shape zone_write_payloads() writes, and the shape the
    # device echoes back when restricted_sweep_areas/restricted_walls are
    # read - see MiotOv42glVacuumEntity._async_read_zones in vacuum.py.
    regions_raw = json.dumps({
        "forbidden_regions": [{"id": 0, "fb_point": [0, 0, 0, 1, 1, 1, 1, 0], "fb_attr": 1}],
    })
    walls_raw = json.dumps({
        "restricted_walls": [{"id": 0, "wall_points": [0, 0, 1, 1]}],
    })
    regions, walls = vacuum_zones.parse_zone_property_values(regions_raw, walls_raw)
    assert regions == [{"fb_point": [0, 0, 0, 1, 1, 1, 1, 0], "fb_attr": 1}]
    assert walls == [{"wall_points": [0, 0, 1, 1]}]


def test_parse_zone_property_values_handles_missing_or_invalid_values():
    regions, walls = vacuum_zones.parse_zone_property_values(None, None)
    assert regions == []
    assert walls == []

    regions, walls = vacuum_zones.parse_zone_property_values("not json", "also not json")
    assert regions == []
    assert walls == []


def test_zone_write_payloads_and_parse_zone_property_values_round_trip():
    regions = [{"fb_point": [0, 200, 0, 0, 100, 0, 100, 200], "fb_attr": 0}]
    walls = [{"wall_points": [0, 0, 150, 150]}]
    regions_payload, walls_payload = vacuum_zones.zone_write_payloads(regions, walls)
    parsed_regions, parsed_walls = vacuum_zones.parse_zone_property_values(regions_payload, walls_payload)
    assert parsed_regions == regions
    assert parsed_walls == walls
