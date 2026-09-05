"""Pure-logic helpers for the xiaomi.vacuum.ov42gl (H50 Pro) cleaning
schedule (`order_clean`, SIID2 PIID19) and DND period (`enable_time_period`,
SIID11 PIID2). No Home Assistant imports - see vacuum_zones.py/vacuum_maps.py
for the same pattern; this module is used directly by vacuum.py's own
schedule/DND entities rather than through a MiotPropConv.

The day-bit/mode constants and DND pack/unpack format below intentionally
duplicate the ones already reverse-engineered in core/converters.py (for
MiotSchedule*Conv/MiotDndStartTimeConv/MiotDndEndTimeConv, defined there for
xiaomi.vacuum.ov42gl's append_converters entry, which isn't reliably
producing entities for this device today - see vacuum.py's own schedule/DND
section for why this module is the actual wiring instead). Duplicated
rather than imported so this stays dependency-free and unit-testable
without Home Assistant installed, same as vacuum_maps.py/vacuum_zones.py -
converters.py itself imports `homeassistant.util`.
"""
import json
import time as time_module

# Confirmed one day at a time by isolating each day in the Xiaomi Home app
# and diffing the resulting `week` value.
SCHEDULE_DAY_BITS = {
    'sunday': 64,
    'monday': 32,
    'tuesday': 16,
    'wednesday': 8,
    'thursday': 4,
    'friday': 2,
    'saturday': 1,
}
# Present in every sample taken with at least one day enabled, even
# single-day ones - meaning not confirmed beyond "looks like an always-on
# repeat flag".
SCHEDULE_ALWAYS_ON_BIT = 128
SCHEDULE_ALL_DAY_BITS = 0x7F

# clean_conf.mode lines up with the same enum as the built-in
# sweep_mop_type property/select.
SCHEDULE_MODE_LABELS = {1: 'Sweep', 2: 'Mop', 3: 'Sweep Mop', 4: 'Sweep Before Mopping'}
SCHEDULE_LABEL_TO_MODE = {v: k for k, v in SCHEDULE_MODE_LABELS.items()}


def decode_schedule(value) -> dict:
    """Parses order_clean's raw JSON string into a dict. Hands back a
    fresh, disabled default (matching the app's own behavior for a device
    with no schedule configured yet) rather than erroring."""
    try:
        data = json.loads(value) if isinstance(value, str) else (value or {})
    except (TypeError, ValueError):
        data = {}
    if not data.get('id'):
        data = {
            'id': [int(time_module.time())],
            'on': [0],
            'week': [0],
            'time': [0],
            'clean_conf': [{'mode': 1, 'mop': 1}],
        }
    return data


def schedule_enabled(data: dict) -> bool:
    return bool((data.get('on') or [0])[0])


def set_schedule_enabled(data: dict, enabled: bool) -> dict:
    data['on'] = [1 if enabled else 0]
    return data


def schedule_time(data: dict):
    """`time[0]` packs `hour * 256 + minute` - same style as the DND
    property but for this single schedule slot."""
    packed = int((data.get('time') or [0])[0])
    return (packed // 256) % 256, packed % 256


def set_schedule_time(data: dict, hour: int, minute: int) -> dict:
    data['time'] = [hour * 256 + minute]
    return data


def schedule_mode_label(data: dict) -> str:
    conf = (data.get('clean_conf') or [{}])[0]
    return SCHEDULE_MODE_LABELS.get(conf.get('mode'), SCHEDULE_MODE_LABELS[1])


def set_schedule_mode(data: dict, label: str) -> dict:
    mode = SCHEDULE_LABEL_TO_MODE.get(label)
    if mode is None:
        return data
    conf = dict((data.get('clean_conf') or [{}])[0])
    conf['mode'] = mode
    data['clean_conf'] = [conf]
    return data


def schedule_day_enabled(data: dict, day: str) -> bool:
    week = int((data.get('week') or [0])[0])
    return bool(week & SCHEDULE_DAY_BITS[day])


def set_schedule_day(data: dict, day: str, enabled: bool) -> dict:
    """Turning the last remaining day off also drops SCHEDULE_ALWAYS_ON_BIT,
    matching the one `week == 0` sample observed (schedule fully
    disabled)."""
    week = int((data.get('week') or [0])[0])
    bit = SCHEDULE_DAY_BITS[day]
    if enabled:
        week = week | bit | SCHEDULE_ALWAYS_ON_BIT
    else:
        week = week & ~bit
        if (week & SCHEDULE_ALL_DAY_BITS) == 0:
            week = 0
    data['week'] = [week]
    return data


def unpack_dnd_schedule(value):
    """Splits a `(start_hour<<24)|(start_minute<<16)|(end_hour<<8)|
    end_minute` uint32 into its four fields - the only documented format
    for `enable_time_period` (SIID 11, PIID 2)."""
    value = int(value or 0)
    return (
        (value >> 24) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    )


def pack_dnd_schedule(start_hour, start_minute, end_hour, end_minute):
    return (
        ((start_hour & 0xFF) << 24)
        | ((start_minute & 0xFF) << 16)
        | ((end_hour & 0xFF) << 8)
        | (end_minute & 0xFF)
    )
