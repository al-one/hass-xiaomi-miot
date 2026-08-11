import json
from datetime import time

from custom_components.xiaomi_miot.core.converters import MiotActionConv
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES

MODEL = "xiaomi.vacuum.ov42gl"

EXCLUDED_SERVICE_IIDS = {10, 15, 17, 20, 22}  # vacuum_map, voice_management, ai_small_pictures, custom, self_check


def model_device(make_device, load_miot_spec):
    return make_device(
        load_miot_spec("xiaomi.vacuum.ov42gl.json"),
        model=MODEL,
        customizes=None,  # exercise the real built-in DEVICE_CUSTOMIZES entry, not a stub
    )


def pack_value(start_hour, start_minute, end_hour, end_minute):
    return (start_hour << 24) | (start_minute << 16) | (end_hour << 8) | end_minute


def test_noisy_internal_properties_are_excluded(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    mapped_props = {
        c.prop.name
        for c in device.converters
        if getattr(c, "prop", None) is not None
    }
    # `order_clean` and `base_station_working_status` are deliberately NOT in this list
    # anymore: they now have dedicated converters (schedule/base-station-activity, see
    # test_xiaomi_vacuum_ov42gl_map.py) instead of being fully excluded.
    for excluded in [
        "common_params", "vacuum_route", "room_information",
        "fault_ids", "vacuum_frameware_version", "map_complete_dialog",
    ]:
        assert excluded not in mapped_props


def test_button_actions_cover_parameterless_actions_only(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    buttons = [c for c in device.converters if isinstance(c, MiotActionConv) and c.domain == "button"]
    names = {c.action.name for c in buttons}

    for expected in [
        "start_sweep", "pause_sweeping", "continue_sweep", "start_eject",
        "identify", "start_charge", "reset_filter_life", "reset_mop_life",
    ]:
        assert expected in names

    # Actions that require an `in` parameter can't work as a bare button
    # (see xiaomi_miot_tools_project README: this used to silently misfire).
    for needs_params in ["start_zone_sweep", "start_vacuum_room_sweep", "close_abnormal_card", "remote_control"]:
        assert needs_params not in names

    # `button_actions` is a flat name list matched against every service (it isn't
    # filtered by `exclude_miot_services`), so this only holds because none of the
    # names above happen to collide with an action in those utility services -
    # asserted explicitly so a future edit can't reintroduce one by accident.
    assert not any(c.action.service.iid in EXCLUDED_SERVICE_IIDS for c in buttons)


def test_no_disturb_switch_and_binary_sensors_present(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    by_domain = {}
    for c in device.converters:
        prop = getattr(c, "prop", None)
        if prop is not None:
            by_domain.setdefault(c.domain, set()).add(prop.name)

    assert "no_disturb" in by_domain.get("switch", set())
    assert "current_no_disturb" in by_domain.get("binary_sensor", set())
    assert "statistical_clean_area" in by_domain.get("sensor", set())
    assert "last_clean_time" in by_domain.get("sensor", set())


def test_last_clean_time_is_customized_as_timestamp(make_device, load_miot_spec):
    # Per-property overrides are looked up as "{model}:{prop.name}" (see
    # BasicEntity.customize_keys in core/hass_entity.py) -- matches the pattern
    # already used for xiaomi.vacuum.b108gl:cleaning_area.
    assert DEVICE_CUSTOMIZES[f"{MODEL}:last_clean_time"] == {"device_class": "timestamp"}

    device = model_device(make_device, load_miot_spec)
    prop = device.spec.get_services("vacuum")[0].get_property("last_clean_time")
    assert prop is not None


def test_dnd_schedule_decode_matches_confirmed_hardware_samples(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    # Two independently-confirmed raw values captured against the real Xiaomi Home
    # app for xiaomi.vacuum.ov42gl (enable_time_period, siid 11 piid 2):
    #   21:00-07:00 -> 352323328 (0x15000700)
    #   21:05-07:06 -> 352651014 (0x15050706)
    for raw, start, end in [
        (352323328, time(21, 0), time(7, 0)),
        (352651014, time(21, 5), time(7, 6)),
    ]:
        payload = device.decode({"siid": 11, "piid": 2, "value": raw})
        assert payload["time.dnd_start"] == start
        assert payload["time.dnd_end"] == end


def test_dnd_schedule_write_preserves_the_other_half(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)

    device.props["time.dnd_end"] = time(7, 6)
    payload = device.encode({"time.dnd_start": time(22, 30)})
    assert payload["params"] == [
        {"did": device.did, "siid": 11, "piid": 2, "value": pack_value(22, 30, 7, 6)},
    ]

    device.props["time.dnd_start"] = time(22, 30)
    payload = device.encode({"time.dnd_end": time(6, 15)})
    assert payload["params"] == [
        {"did": device.did, "siid": 11, "piid": 2, "value": pack_value(22, 30, 6, 15)},
    ]


def test_dnd_schedule_write_defaults_missing_sibling_to_midnight(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    payload = device.encode({"time.dnd_start": time(22, 30)})
    assert payload["params"] == [
        {"did": device.did, "siid": 11, "piid": 2, "value": pack_value(22, 30, 0, 0)},
    ]


def test_fault_conv_translates_confirmed_codes(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    payload = device.decode({"siid": 2, "piid": 3, "value": 320004})
    assert payload["sensor.fault"] == "Wheel Error (turn the robot upside down and clean the wheels)"

    payload = device.decode({"siid": 2, "piid": 3, "value": 0})
    assert payload["sensor.fault"] == "No Fault"


def test_fault_conv_falls_back_for_unmapped_codes(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    payload = device.decode({"siid": 2, "piid": 3, "value": 999999})
    assert payload["sensor.fault"] == "Unknown fault (code 999999)"


def test_base_station_activity_conv_decodes_mode_and_progress(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    raw = json.dumps({"mode": 2, "progress": 69})
    payload = device.decode({"siid": 2, "piid": 18, "value": raw})
    assert payload["sensor.base_station_activity"] == "Dust Emptying (69%)"


# order_clean (siid 2, piid 19) sample matching the one documented in
# xiaomi_miot_tools_project/README.md, captured from the real Xiaomi Home
# app: Mon+Wed+Fri at 09:46, vacuum-only.
CONFIRMED_ORDER_CLEAN_SAMPLE = {
    "id": [1785851231],
    "on": [1],
    "week": [170],  # 128 (flag) + 32 (Mon) + 8 (Wed) + 2 (Fri)
    "time": [2350],  # 9 * 256 + 46 -> 09:46
    "clean_conf": [{"mode": 1, "mop": 1}],
}


def test_schedule_decode_matches_confirmed_hardware_sample(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    raw = json.dumps(CONFIRMED_ORDER_CLEAN_SAMPLE)
    payload = device.decode({"siid": 2, "piid": 19, "value": raw})

    assert payload["switch.schedule_enabled"] is True
    assert payload["time.schedule_time"] == time(9, 46)
    assert payload["select.schedule_mode"] == "Sweep"
    assert payload["switch.schedule_day_monday"] is True
    assert payload["switch.schedule_day_wednesday"] is True
    assert payload["switch.schedule_day_friday"] is True
    assert payload["switch.schedule_day_sunday"] is False
    assert payload["switch.schedule_day_tuesday"] is False


def test_schedule_mode_options_available_for_select_entity(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    conv = next(c for c in device.converters if c.full_name == "select.schedule_mode")
    assert conv.options == ["Sweep", "Mop", "Sweep Mop", "Sweep Before Mopping"]


def test_schedule_day_toggle_preserves_the_rest_of_the_schedule(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    device.props["order_clean_raw"] = dict(CONFIRMED_ORDER_CLEAN_SAMPLE)

    payload = device.encode({"switch.schedule_day_tuesday": True})
    written = json.loads(payload["params"][0]["value"])
    assert written["week"] == [170 | 16]  # adds Tuesday's bit, keeps Mon/Wed/Fri/flag
    assert written["on"] == [1]
    assert written["time"] == [2350]
    assert written["clean_conf"] == [{"mode": 1, "mop": 1}]


def test_schedule_turning_off_the_last_day_clears_the_week_bitmask(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    device.props["order_clean_raw"] = {
        "id": [1], "on": [1], "week": [128 | 32], "time": [0],
        "clean_conf": [{"mode": 1, "mop": 1}],
    }
    payload = device.encode({"switch.schedule_day_monday": False})
    written = json.loads(payload["params"][0]["value"])
    assert written["week"] == [0]


def test_schedule_mode_write_preserves_unknown_mop_field(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    device.props["order_clean_raw"] = dict(CONFIRMED_ORDER_CLEAN_SAMPLE)

    payload = device.encode({"select.schedule_mode": "Sweep Mop"})
    written = json.loads(payload["params"][0]["value"])
    assert written["clean_conf"] == [{"mode": 3, "mop": 1}]
