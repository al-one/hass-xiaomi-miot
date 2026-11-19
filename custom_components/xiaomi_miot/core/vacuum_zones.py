"""Virtual wall / restricted zone helpers for xiaomi.vacuum.ov42gl (H50 Pro).

Reverse-engineered from the Xiaomi Home app's own map-editor plugin for
interoperability - so a zone/wall added through Home Assistant also shows up
correctly in the app, not just here.

Both square-zone types live in ONE property, `restricted-sweep-areas` (SIID2
PIID13 - the name is misleading, it holds both, dispatched per-shape by
`fb_attr`). Virtual walls are a separate property, `restricted-walls` (SIID2
PIID14). The app always rewrites each property's *entire* list rather than
appending incrementally - `id` is just the shape's position in the array, not
a stable identifier across edits - so writers here do the same.

Both properties are read/write, so the current zones/walls are read back
directly from the device (see `parse_zone_property_values`) - no cloud map
download is involved.
"""
import json

ZONE_SIID = 2
RESTRICTED_AREAS_PIID = 13
RESTRICTED_WALLS_PIID = 14

# `fb_attr` meaning was confirmed empirically (reading back a real device's
# own already-configured zone and comparing its color against the app), not
# just trusted from the plugin's internal (and possibly stale/misleading)
# variable names.
FB_ATTR_NO_SWEEP_AND_MOP = 0  # robot doesn't enter the area at all
FB_ATTR_NO_MOP_ONLY = 1  # robot vacuums the area, just skips mopping there

ZONE_TYPE_WALL = 'wall'
ZONE_TYPE_NO_SWEEP_AND_MOP = 'no_sweep_and_mop'
ZONE_TYPE_NO_MOP_ONLY = 'no_mop_only'

ZONE_TYPE_LABELS = {
    ZONE_TYPE_WALL: 'Virtual Wall',
    ZONE_TYPE_NO_SWEEP_AND_MOP: 'No Sweep and Mop',
    ZONE_TYPE_NO_MOP_ONLY: 'No Mop Only',
}
LABEL_TO_ZONE_TYPE = {v: k for k, v in ZONE_TYPE_LABELS.items()}

# Same limit the app enforces client-side (checkCountIsExceedLimit) on the
# combined count of walls + both restricted-area types; not confirmed
# whether the device also enforces this server-side, so it's enforced here
# too rather than assumed unnecessary.
MAX_TOTAL_SHAPES = 10


def rect_to_fb_point(x1, y1, x2, y2):
    """Order matters beyond just "trace the rectangle boundary": the device
    (and the app) don't treat `fb_point` as a plain fill polygon. Matches the
    app's own rectangle-tool result exactly: upperLeft, lowerLeft,
    lowerRight, upperRight, where "upper" is the larger world_y and "right"
    is the larger world_x."""
    x_min, x_max = (x1, x2) if x1 <= x2 else (x2, x1)
    y_min, y_max = (y1, y2) if y1 <= y2 else (y2, y1)
    upper_left = (x_min, y_max)
    lower_left = (x_min, y_min)
    lower_right = (x_max, y_min)
    upper_right = (x_max, y_max)
    return [*upper_left, *lower_left, *lower_right, *upper_right]


def parse_zone_property_values(regions_raw, walls_raw):
    """Parses the raw string values of `restricted_sweep_areas`
    (`{"forbidden_regions": [...]}`) and `restricted_walls`
    (`{"restricted_walls": [...]}`) - the device's own read/write JSON shape
    for these two properties - into the plain `(regions, walls)` list shape
    the rest of this module works with (`{'fb_point':..,'fb_attr':..}` /
    `{'wall_points':..}`)."""
    try:
        regions_obj = json.loads(regions_raw) if isinstance(regions_raw, str) else (regions_raw or {})
    except (TypeError, ValueError):
        regions_obj = {}
    try:
        walls_obj = json.loads(walls_raw) if isinstance(walls_raw, str) else (walls_raw or {})
    except (TypeError, ValueError):
        walls_obj = {}
    regions = [
        {'fb_point': r['fb_point'], 'fb_attr': r['fb_attr']}
        for r in regions_obj.get('forbidden_regions') or []
    ]
    walls = [
        {'wall_points': w['wall_points']}
        for w in walls_obj.get('restricted_walls') or []
    ]
    return regions, walls


def describe_zones(regions: list, walls: list):
    """One (label, kind, index) tuple per existing region/wall, for a "pick
    one to remove" selector."""
    options = []
    for i, region in enumerate(regions or []):
        zone_type = (
            ZONE_TYPE_NO_SWEEP_AND_MOP
            if region.get('fb_attr') == FB_ATTR_NO_SWEEP_AND_MOP
            else ZONE_TYPE_NO_MOP_ONLY
        )
        options.append((f'{ZONE_TYPE_LABELS[zone_type]} #{i}', 'region', i))
    for i, _wall in enumerate(walls or []):
        options.append((f'{ZONE_TYPE_LABELS[ZONE_TYPE_WALL]} #{i}', 'wall', i))
    return options


def build_zone_lists(regions: list, walls: list, zone_type: str, x1, y1, x2, y2):
    """Returns the new (regions, walls) lists after adding one shape."""
    regions = list(regions or [])
    walls = list(walls or [])
    if len(regions) + len(walls) >= MAX_TOTAL_SHAPES:
        raise ValueError(f'Limit of {MAX_TOTAL_SHAPES} zones/walls total reached (same limit the app enforces)')
    if zone_type == ZONE_TYPE_WALL:
        walls.append({'wall_points': [x1, y1, x2, y2]})
    else:
        fb_attr = FB_ATTR_NO_SWEEP_AND_MOP if zone_type == ZONE_TYPE_NO_SWEEP_AND_MOP else FB_ATTR_NO_MOP_ONLY
        regions.append({'fb_point': rect_to_fb_point(x1, y1, x2, y2), 'fb_attr': fb_attr})
    return regions, walls


def remove_zone_lists(regions: list, walls: list, kind: str, index: int):
    """Returns the new (regions, walls) lists after removing one shape."""
    regions = list(regions or [])
    walls = list(walls or [])
    if kind == 'region':
        if not (0 <= index < len(regions)):
            raise ValueError('Zone not found (the list may have changed) - try refreshing the selection')
        del regions[index]
    else:
        if not (0 <= index < len(walls)):
            raise ValueError('Wall not found (the list may have changed) - try refreshing the selection')
        del walls[index]
    return regions, walls


def zone_write_payloads(regions: list, walls: list):
    """JSON string payloads for `restricted-sweep-areas`/`restricted-walls`,
    renumbering `id` 0..N-1 by array position (ids aren't stable across
    edits - the app always rewrites the full list, never appends)."""
    regions_payload = json.dumps({
        'forbidden_regions': [
            {'id': i, 'fb_point': r['fb_point'], 'fb_attr': r['fb_attr']}
            for i, r in enumerate(regions)
        ]
    })
    walls_payload = json.dumps({
        'restricted_walls': [
            {'id': i, 'wall_points': w['wall_points']}
            for i, w in enumerate(walls)
        ]
    })
    return regions_payload, walls_payload
