"""Pure-logic helpers for the xiaomi.vacuum.ov42gl (H50 Pro) "clean this
area now" feature (`start-zone-sweep`, SIID2 AIID37) - draw one or more
ad-hoc rectangles and clean them immediately, without saving a room or a
permanent restricted zone. No Home Assistant imports - see
vacuum_zones.py/vacuum_maps.py for the same pattern.

Reuses vacuum_zones.rect_to_fb_point for the 8-point corner ordering:
confirmed in the app's own bundle that this feature's rectangle tool
(`ZoneHandler`) extends the same base class as the restricted-zone editor
(`BaseRectPanHandler`) without overriding its corner ordering, so it's
identical to zones - see vacuum_zones.py's own docstring for the app-code
reference.
"""
from .vacuum_zones import rect_to_fb_point

# Same limit the app enforces client-side (`zone_limit: 5`, passed into
# ZonePage) - not confirmed whether the device also enforces this
# server-side.
MAX_AREAS = 5


def build_area_list(areas: list, x1, y1, x2, y2) -> list:
    """Returns the new areas list after queueing one more rectangle."""
    areas = list(areas or [])
    if len(areas) >= MAX_AREAS:
        raise ValueError(f'Limit of {MAX_AREAS} areas at once reached (same limit the app enforces)')
    areas.append((x1, y1, x2, y2))
    return areas


def describe_areas(areas: list) -> list:
    return [f'Area #{i}: ({x1}, {y1}) - ({x2}, {y2})' for i, (x1, y1, x2, y2) in enumerate(areas or [])]


def area_sweep_payload(areas: list) -> list:
    """The `start-zone-sweep` action's input - one dict per area.
    `blocks_attr` is always 0 in every sample observed in the app's own
    code for this feature - not the same field/semantics as restricted
    zones' `fb_attr`, just a fixed value here."""
    return [
        {'blocks_region': rect_to_fb_point(x1, y1, x2, y2), 'blocks_attr': 0}
        for (x1, y1, x2, y2) in (areas or [])
    ]
