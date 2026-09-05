"""Renders decoded xiaomi.vacuum.ov42gl (H50 Pro) map JSON (see
vacuum_map_codec.py) to a PNG image. No Home Assistant imports - only
Pillow, a core Home Assistant dependency already (used for camera
snapshots/QR codes/etc across many integrations), so it doesn't need
declaring separately in manifest.json.

The decoded payload already carries everything needed for the extra layers
below - no separate download per layer:
  - `position`: {x, y, yaw} - robot's current pose
  - `paths`: {points: "<json array of {x,y,type,sweep_mop_mode,yaw}>"} -
    the trail it has cleaned so far
  - `fb_regions`: already-configured restricted zones (polygons)
  - `fb_walls`: already-configured virtual walls (line segments)

Colors and the coordinate math below were reverse-engineered from the real
Xiaomi Home app's own map plugin (the same one vacuum_map_codec.py's crypto
came from) so this renders close to the app's own visual style. The robot
marker itself (map_assets/robot.png) is a plain generic dot drawn for this
project, not the app's own icon - the app's icon is a proprietary asset
extracted from its bundle, unsuitable for redistribution here.
"""
import base64
import json
import math
import zlib
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).parent.parent / "map_assets"

# Color.js picks one of two palettes at runtime (`APP_CONFIG.NEW_MAP_COLOR
# ? MAP_COLOR_NEW : MAP_COLOR_OLD`) - can't read that app config flag from
# here, only guess from what the rendered map actually looks like.
# MAP_COLOR_NEW's 4 room-FLOOR slots are blue/lavender/pink/cyan (tried
# first) but the real app for this device turned out to render every room
# as a shade of blue - that matches MAP_COLOR_INDEX_OLD's FLOOR slots
# (5,6,7,8) instead, so this uses MAP_COLOR_OLD (light theme): index 0 =
# background, 14 = wall, 5/6/7/8 = the 4 room-color-slot FLOOR colors
# (map_room_info[].color is that 1-4 slot, not a room id).
BG_COLOR = (0xF7, 0xF8, 0xFA, 255)
WALL_COLOR = (0x6D, 0x86, 0xAF, 255)
ROOM_PALETTE = [
    (0x5C, 0x93, 0xEE, 255),  # slot 1
    (0x7D, 0xAA, 0xF9, 255),  # slot 2
    (0x9D, 0xBE, 0xFA, 255),  # slot 3
    (0xC0, 0xD7, 0xFC, 255),  # slot 4
]

# PathView.drawPath(): sweep_map_path stroke "#fff" width 0.8 opacity 1,
# mop_map_path stroke "#E2FFF4" width 5 opacity 0.5 (widths are in the app's
# own SVG scale, not ours - picked comparable values below).
SWEEP_PATH_COLOR = (255, 255, 255, 235)
MOP_PATH_COLOR = (0xE2, 0xFF, 0xF4, 140)

# VirtualWallHandler.viewProps: stroke "#FF4E64", strokeWidth 3,
# strokeDasharray "2.67, 2.67".
VWALL_COLOR = (0xFF, 0x4E, 0x64, 255)
VWALL_DASH = (7, 7)

# DataHelper.handleRestrictedAreaData(): each fb_region carries `fb_attr`
# (0 = "restrictedSweepArea"/no-mop, 1 = "restrictedArea"/no-entry) - two
# different zone types with two different styles:
#   fb_attr==1 (RestrictedAreaHandler.viewProps): fill rgba(252,113,255,0.47),
#     dashed border "#F528F9" width 3.
#   fb_attr==0 (RestrictedSweepAreaHandler.viewProps): fill
#     rgba(255,157,170,0.6), dashed border "#FF4E64" width 3 (same red as
#     the virtual wall).
FORBIDDEN_STYLES = {
    1: {"fill": (0xFC, 0x71, 0xFF, 120), "outline": (0xF5, 0x28, 0xF9, 255)},
    0: {"fill": (0xFF, 0x9D, 0xAA, 150), "outline": (0xFF, 0x4E, 0x64, 255)},
}
FORBIDDEN_DASH = (7, 7)

GRID_STEP_MM = 1000  # 1 meter - matches the mm coordinate space fb_point/
# wall_points/position already use (confirmed empirically: this device's
# map has resolution=50 (mm/px), origin_x/origin_y in the thousands).
GRID_LINE_COLOR = (0, 0, 0, 50)
GRID_LABEL_COLOR = (0, 0, 0, 170)


@lru_cache(maxsize=2)
def _load_icon(name: str) -> Image.Image:
    return Image.open(ASSETS_DIR / name).convert("RGBA")


@lru_cache(maxsize=1)
def _grid_font():
    try:
        return ImageFont.load_default(size=13)
    except TypeError:
        # Older Pillow (<10.1) doesn't take a size kwarg here.
        return ImageFont.load_default()


def _grid_lines_mm(map_data):
    """World-mm coordinates of every grid line that falls inside the map,
    shared by the pre-flip line pass and the post-flip label pass so both
    draw at exactly the same positions."""
    origin_x, origin_y = map_data["origin_x"], map_data["origin_y"]
    resolution = map_data["resolution"]
    max_x = origin_x + map_data["width"] * resolution
    max_y = origin_y + map_data["height"] * resolution
    xs, ys = [], []
    x = math.ceil(origin_x / GRID_STEP_MM) * GRID_STEP_MM
    while x <= max_x:
        xs.append(x)
        x += GRID_STEP_MM
    y = math.ceil(origin_y / GRID_STEP_MM) * GRID_STEP_MM
    while y <= max_y:
        ys.append(y)
        y += GRID_STEP_MM
    return xs, ys, origin_x, origin_y, max_x, max_y


def _dashed_line(draw, p1, p2, fill, width, dash):
    x1, y1 = p1
    x2, y2 = p2
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        return
    dx, dy = (x2 - x1) / length, (y2 - y1) / length
    on, off = dash
    pos = 0.0
    while pos < length:
        seg_end = min(pos + on, length)
        draw.line(
            [(x1 + dx * pos, y1 + dy * pos), (x1 + dx * seg_end, y1 + dy * seg_end)],
            fill=fill, width=width,
        )
        pos += on + off


def _draw_smooth_run(draw, run, fill, width):
    """Draws one continuous stroke with rounded joints/caps (PathView.drawPath()
    uses strokeLinecap/strokeLinejoin "round" - drawing each segment as its
    own separate draw.line() call leaves a visible kink at every joint once
    the stroke is wide; joint="curve" plus round end caps fixes that)."""
    if len(run) < 2:
        return
    draw.line(run, fill=fill, width=width, joint="curve")
    r = width / 2
    for x, y in (run[0], run[-1]):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def _dashed_polygon(draw, points, fill, outline, width, dash):
    draw.polygon(points, fill=fill)
    for i in range(len(points)):
        _dashed_line(draw, points[i], points[(i + 1) % len(points)], outline, width, dash)


def _paste_icon(layer: Image.Image, icon: Image.Image, cx: float, cy: float, size: int, rotate_deg: float = 0):
    resized = icon.resize((size, size), Image.LANCZOS)
    if rotate_deg:
        resized = resized.rotate(rotate_deg, resample=Image.BICUBIC, expand=False)
    layer.paste(resized, (int(cx - size / 2), int(cy - size / 2)), resized)


# Default render scale, pulled out as a constant so camera.py can publish it
# as an entity attribute.
DEFAULT_SCALE = 3


def render_map_png(
    map_data: dict,
    scale: int = DEFAULT_SCALE,
    show_charge_station: bool = True,
    show_robot_position: bool = True,
    show_path: bool = True,
    show_forbidden_zones: bool = True,
) -> bytes:
    width = map_data["width"]
    height = map_data["height"]
    grid = zlib.decompress(base64.b64decode(map_data["map_data"]))

    room_color_by_grid_id = {
        r["grid_id"]: r["color"] for r in map_data.get("map_room_info", [])
    }

    # Each byte in `grid` is already a flat palette index (0 = background,
    # 1 = wall, anything else = a room's grid_id) in row-major order, i.e.
    # exactly what Pillow's "P" mode expects natively - building the image
    # this way is one C-level call instead of a pure-Python per-pixel loop
    # (`img.load()[x, y] = color` for every one of width*height pixels,
    # ~1-2 orders of magnitude slower on a real-size map, and this runs on
    # every single camera_image request, not just the 30s poll - see
    # camera.py's RobotMapCamera render cache for the other half of that).
    palette = bytearray(256 * 3)
    palette[0:3] = BG_COLOR[:3]
    palette[3:6] = WALL_COLOR[:3]
    for grid_id in range(2, 256):
        # Same -1 (1-based slot -> 0-indexed palette) as before - see the
        # "Kitchen" room note this replaced for why that offset matters.
        slot = room_color_by_grid_id.get(grid_id, 1)
        color = ROOM_PALETTE[(slot - 1) % len(ROOM_PALETTE)]
        palette[grid_id * 3:grid_id * 3 + 3] = bytes(color[:3])
    img = Image.frombytes("P", (width, height), bytes(grid))
    img.putpalette(bytes(palette))
    img = img.convert("RGBA")

    if scale != 1:
        img = img.resize((width * scale, height * scale), Image.NEAREST)

    origin_x, origin_y = map_data["origin_x"], map_data["origin_y"]
    resolution = map_data["resolution"]

    def to_px(world_x, world_y):
        return (
            (world_x - origin_x) / resolution * scale,
            (world_y - origin_y) / resolution * scale,
        )

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    if show_forbidden_zones:
        for region in map_data.get("fb_regions") or []:
            pts = region.get("fb_point") or []
            poly = [to_px(pts[i], pts[i + 1]) for i in range(0, len(pts) - 1, 2)]
            if len(poly) >= 3:
                style = FORBIDDEN_STYLES.get(region.get("fb_attr"), FORBIDDEN_STYLES[1])
                _dashed_polygon(draw, poly, style["fill"], style["outline"], max(2, scale), FORBIDDEN_DASH)
        for wall in map_data.get("fb_walls") or []:
            wp = wall.get("wall_points") or []
            if len(wp) >= 4:
                _dashed_line(draw, to_px(wp[0], wp[1]), to_px(wp[2], wp[3]), VWALL_COLOR, max(2, scale), VWALL_DASH)

    if show_path:
        raw_paths = map_data.get("paths") or []
        paths = [raw_paths] if isinstance(raw_paths, dict) else raw_paths
        for path in paths:
            if not path:
                continue
            try:
                points = json.loads(path["points"])
            except (KeyError, TypeError, ValueError):
                continue
            # PathView.svgPath(): `type` is pen-up(0)/pen-down(1), not a
            # point-validity flag - a segment is only connected when BOTH
            # ends are type 1 (either end being 0 lifts the pen). Points
            # also arrive with a long run of literal (0,0,type:0) padding
            # at the start, which this naturally skips since they're all
            # type 0. `sweep_mop_mode` picks sweep-trail (1), mop-trail
            # (2), or both (3) for that segment. Points are accumulated
            # into a run per trail and only handed to Pillow as one
            # polyline (draw once per continuous stretch, not once per
            # segment) so joint="curve" can round the joints.
            sweep_width = max(3, scale)
            mop_width = max(10, scale * 5)
            sweep_run, mop_run = [], []
            prev = None
            for cur in points:
                connected = prev is not None and prev.get("type") == 1 and cur.get("type") == 1
                mode = cur.get("sweep_mop_mode") or 1
                do_sweep = connected and mode in (1, 3)
                do_mop = connected and mode in (2, 3)

                if do_sweep:
                    if not sweep_run:
                        sweep_run.append(to_px(prev["x"], prev["y"]))
                    sweep_run.append(to_px(cur["x"], cur["y"]))
                else:
                    _draw_smooth_run(draw, sweep_run, SWEEP_PATH_COLOR, sweep_width)
                    sweep_run = []

                if do_mop:
                    if not mop_run:
                        mop_run.append(to_px(prev["x"], prev["y"]))
                    mop_run.append(to_px(cur["x"], cur["y"]))
                else:
                    _draw_smooth_run(draw, mop_run, MOP_PATH_COLOR, mop_width)
                    mop_run = []

                prev = cur
            _draw_smooth_run(draw, sweep_run, SWEEP_PATH_COLOR, sweep_width)
            _draw_smooth_run(draw, mop_run, MOP_PATH_COLOR, mop_width)

    img = Image.alpha_composite(img, overlay)

    # Confirmed empirically that rotate(270) -> flip_lr -> rotate(90) (the
    # sequence found by trial and error against the app's own orientation)
    # is exactly equivalent to a single vertical flip - collapsed to that
    # here, and reused as closed-form point math below so icons don't need
    # to be pasted pre-rotation and dragged through 3 transposes.
    img = img.transpose(Image.FLIP_TOP_BOTTOM)
    final_height = img.size[1]

    def to_final_px(world_x, world_y):
        x, y = to_px(world_x, world_y)
        return x, final_height - 1 - y

    icon_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))

    if show_charge_station and map_data.get("have_pile"):
        cx, cy = to_final_px(map_data["pile_x"], map_data["pile_y"])
        _paste_icon(icon_layer, _load_icon("charge_station.png"), cx, cy, max(16, 8 * scale))

    if show_robot_position and map_data.get("position"):
        pos = map_data["position"]
        rx, ry = to_final_px(pos["x"], pos["y"])
        yaw_raw = pos.get("yaw") or 0
        # Exact formula from the app's RobotView (robotRotate), applied to
        # the real robot.png icon via a CSS rotateZ in the original - not
        # verified against a live heading yet, since that needs the robot
        # actually mid-clean to eyeball; flip the sign here if it turns out
        # mirrored once tested live.
        robot_rotate_deg = 180 - round(yaw_raw / 1000 * 180 / math.pi)
        _paste_icon(icon_layer, _load_icon("robot.png"), rx, ry, max(52, 21 * scale), robot_rotate_deg)

    img = Image.alpha_composite(img, icon_layer)

    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
