"""Pure-logic tests for the xiaomi.vacuum.ov42gl (H50 Pro) cleaning
schedule helpers - core/vacuum_schedule.py imports from core/converters.py
only (both plain-Python, no Home Assistant), so these run standalone.
"""
import json

from custom_components.xiaomi_miot.core import vacuum_schedule as vs

# Shape confirmed empirically against a live device - one schedule slot,
# Monday+Wednesday, 21:30, mode 1 (Sweep) - see core/vacuum_schedule.py.
CONFIRMED_SCHEDULE_SAMPLE = {
    'id': [1785600000],
    'on': [1],
    'week': [8 | 32 | 128],  # wednesday(8) + monday(32) + always-on(128)
    'time': [21 * 256 + 30],
    'clean_conf': [{'mode': 1, 'mop': 1}],
}


def test_decode_schedule_matches_confirmed_hardware_sample():
    assert vs.decode_schedule(json.dumps(CONFIRMED_SCHEDULE_SAMPLE)) == CONFIRMED_SCHEDULE_SAMPLE


def test_decode_schedule_handles_missing_or_invalid_values():
    for empty in (None, 'not json', '{}', json.dumps({'on': [0]})):
        data = vs.decode_schedule(empty)
        assert data['id'] and data['on'] == [0] and data['week'] == [0]


def test_schedule_enabled_reads_the_on_flag():
    assert vs.schedule_enabled(CONFIRMED_SCHEDULE_SAMPLE) is True
    assert vs.schedule_enabled({'on': [0]}) is False
    assert vs.schedule_enabled({}) is False


def test_set_schedule_enabled_round_trips():
    data = vs.set_schedule_enabled(dict(CONFIRMED_SCHEDULE_SAMPLE), False)
    assert data['on'] == [0]
    data = vs.set_schedule_enabled(data, True)
    assert data['on'] == [1]


def test_schedule_time_unpacks_hour_and_minute():
    assert vs.schedule_time(CONFIRMED_SCHEDULE_SAMPLE) == (21, 30)
    assert vs.schedule_time({}) == (0, 0)


def test_set_schedule_time_packs_hour_and_minute():
    data = vs.set_schedule_time(dict(CONFIRMED_SCHEDULE_SAMPLE), 6, 5)
    assert data['time'] == [6 * 256 + 5]
    assert vs.schedule_time(data) == (6, 5)


def test_schedule_mode_label_maps_confirmed_values():
    assert vs.schedule_mode_label(CONFIRMED_SCHEDULE_SAMPLE) == 'Sweep'
    assert vs.schedule_mode_label({'clean_conf': [{'mode': 3}]}) == 'Sweep Mop'
    # Unmapped/missing mode falls back to the same default the device
    # itself defaults to (mode 1) rather than erroring.
    assert vs.schedule_mode_label({}) == 'Sweep'


def test_set_schedule_mode_writes_the_numeric_mode_and_preserves_mop():
    data = vs.set_schedule_mode(dict(CONFIRMED_SCHEDULE_SAMPLE), 'Sweep Mop')
    assert data['clean_conf'] == [{'mode': 3, 'mop': 1}]
    # Unknown label is a no-op rather than corrupting the existing config.
    unchanged = vs.set_schedule_mode(dict(CONFIRMED_SCHEDULE_SAMPLE), 'Not A Real Mode')
    assert unchanged == CONFIRMED_SCHEDULE_SAMPLE


def test_schedule_day_enabled_matches_confirmed_week_bits():
    assert vs.schedule_day_enabled(CONFIRMED_SCHEDULE_SAMPLE, 'monday') is True
    assert vs.schedule_day_enabled(CONFIRMED_SCHEDULE_SAMPLE, 'wednesday') is True
    assert vs.schedule_day_enabled(CONFIRMED_SCHEDULE_SAMPLE, 'sunday') is False


def test_set_schedule_day_toggles_only_its_own_bit():
    data = vs.set_schedule_day(dict(CONFIRMED_SCHEDULE_SAMPLE), 'friday', True)
    assert vs.schedule_day_enabled(data, 'friday') is True
    assert vs.schedule_day_enabled(data, 'monday') is True  # untouched
    data = vs.set_schedule_day(data, 'monday', False)
    assert vs.schedule_day_enabled(data, 'monday') is False
    assert vs.schedule_day_enabled(data, 'friday') is True  # untouched


def test_set_schedule_day_clears_always_on_bit_when_last_day_removed():
    data = {'week': [vs.SCHEDULE_DAY_BITS['sunday'] | vs.SCHEDULE_ALWAYS_ON_BIT]}
    data = vs.set_schedule_day(data, 'sunday', False)
    assert data['week'] == [0]


def test_set_schedule_day_sets_always_on_bit_when_enabling():
    data = vs.set_schedule_day({'week': [0]}, 'tuesday', True)
    week = data['week'][0]
    assert week & vs.SCHEDULE_DAY_BITS['tuesday']
    assert week & vs.SCHEDULE_ALWAYS_ON_BIT


# Confirmed empirically against two known values from the Xiaomi Home app:
#   21:00 -> 07:00  => 352323328  == 0x15000700
#   21:05 -> 07:06  => 352651014  == 0x15050706
def test_unpack_dnd_schedule_matches_confirmed_app_values():
    assert vs.unpack_dnd_schedule(352323328) == (21, 0, 7, 0)
    assert vs.unpack_dnd_schedule(352651014) == (21, 5, 7, 6)


def test_unpack_dnd_schedule_handles_none():
    assert vs.unpack_dnd_schedule(None) == (0, 0, 0, 0)


def test_pack_dnd_schedule_matches_confirmed_app_values():
    assert vs.pack_dnd_schedule(21, 0, 7, 0) == 352323328
    assert vs.pack_dnd_schedule(21, 5, 7, 6) == 352651014


def test_pack_unpack_dnd_schedule_round_trips():
    packed = vs.pack_dnd_schedule(6, 45, 23, 15)
    assert vs.unpack_dnd_schedule(packed) == (6, 45, 23, 15)
