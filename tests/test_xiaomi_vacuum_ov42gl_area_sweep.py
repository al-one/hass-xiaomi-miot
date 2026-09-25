"""Pure-logic tests for the xiaomi.vacuum.ov42gl (H50 Pro) ad-hoc
"clean this area now" helpers - core/vacuum_area_sweep.py only imports
core/vacuum_zones.py (also plain-Python), so these run standalone.
"""
import pytest

from custom_components.xiaomi_miot.core import vacuum_area_sweep as vas
from custom_components.xiaomi_miot.core.vacuum_zones import rect_to_fb_point


def test_build_area_list_appends_the_new_rectangle():
    areas = vas.build_area_list([], 0, 0, 1000, 2000)
    assert areas == [(0, 0, 1000, 2000)]
    areas = vas.build_area_list(areas, 500, 500, 1500, 1500)
    assert areas == [(0, 0, 1000, 2000), (500, 500, 1500, 1500)]


def test_build_area_list_enforces_the_app_limit():
    areas = [(0, 0, 1, 1)] * vas.MAX_AREAS
    with pytest.raises(ValueError):
        vas.build_area_list(areas, 0, 0, 1, 1)


def test_describe_areas_formats_each_rectangle():
    areas = [(0, 0, 1000, 2000), (500, 500, 1500, 1500)]
    assert vas.describe_areas(areas) == [
        'Area #0: (0, 0) - (1000, 2000)',
        'Area #1: (500, 500) - (1500, 1500)',
    ]
    assert vas.describe_areas([]) == []
    assert vas.describe_areas(None) == []


def test_area_sweep_payload_reuses_zone_corner_ordering():
    areas = [(0, 0, 1000, 2000)]
    payload = vas.area_sweep_payload(areas)
    assert payload == [{'blocks_region': rect_to_fb_point(0, 0, 1000, 2000), 'blocks_attr': 0}]


def test_area_sweep_payload_one_entry_per_area_with_fixed_attr():
    areas = [(0, 0, 1000, 2000), (500, 500, 1500, 1500)]
    payload = vas.area_sweep_payload(areas)
    assert len(payload) == 2
    assert all(entry['blocks_attr'] == 0 for entry in payload)
    assert all(len(entry['blocks_region']) == 8 for entry in payload)


def test_area_sweep_payload_empty():
    assert vas.area_sweep_payload([]) == []
    assert vas.area_sweep_payload(None) == []
