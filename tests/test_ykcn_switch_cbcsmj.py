import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.util import dt as dt_util
from zoneinfo import ZoneInfo

from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.miot_local_devices import MIOT_LOCAL_MODELS
from custom_components.xiaomi_miot.core.templates import template
from custom_components.xiaomi_miot.sensor import SensorEntity


MODEL = "ykcn.switch.cbcsmj"


def _prop_converters(device, domain):
    return {
        converter.prop.name: converter
        for converter in device.converters
        if converter.domain == domain
        and getattr(converter, "prop", None) is not None
    }


def test_ykcn_switch_cbcsmj_supports_local_miot():
    assert MODEL in MIOT_LOCAL_MODELS


def test_ykcn_switch_cbcsmj_exposes_supported_entities(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)

    switches = _prop_converters(device, "switch")
    numbers = _prop_converters(device, "number")
    selects = _prop_converters(device, "select")
    sensors = _prop_converters(device, "sensor")

    assert "on" in switches
    assert {"electric_alarm_set", "overcurrent_set", "overvoltage_set", "undervoltage_set"} <= set(switches)
    assert {
        "electric_alarm",
        "overcurrent_alarm",
        "overvoltage_alarm",
        "undervoltage_alarm",
    } <= set(numbers)
    assert "default_power_on_state" in selects
    assert {"electric_power", "voltage", "electric_current", "fault"} <= set(sensors)
    # fault carries a value list (no fault / over power), so it is a text
    # sensor rather than a binary_sensor.
    assert not any(
        c.domain == "binary_sensor" and "fault" in (c.attr or "")
        for c in device.converters
    )
    # the device has no heat sensor, so no heat-alert entities are created
    assert not any("heat_alert" in name for name in switches)
    assert not any("heat_alert" in name for name in numbers)


def test_ykcn_switch_cbcsmj_sensor_value_ratios(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    sensors = _prop_converters(device, "sensor")

    voltage = SensorEntity(device, sensors["voltage"])
    current = SensorEntity(device, sensors["electric_current"])
    power = SensorEntity(device, sensors["electric_power"])

    # voltage is reported in 0.1 V and current in 0.001 A
    assert voltage.custom_value_ratio == 0.1
    assert current.custom_value_ratio == 0.001
    assert power.custom_value_ratio == 0


def test_ykcn_switch_cbcsmj_power_cost_uses_daily_statistics(make_device, load_miot_spec):
    cfg = DEVICE_CUSTOMIZES[MODEL]
    # The vendor app derives energy from v2/user/statistics stat_day_v3 daily
    # cumulative snapshots ([start-of-day, end-of-day], raw 0.01 kWh units),
    # which cover a whole month in 31 records. The raw prop.3.1 group only
    # returns ~10-minute samples (~5h with limit=32) so it can never reach the
    # month baseline.
    assert cfg["stat_power_cost_key"] == "3.1"
    assert cfg["stat_power_cost_template"] == "ykcn_switch_cbcsmj_power_cost"
    assert cfg["sensor_attributes"] == "power_cost_today,power_cost_month"
    assert "miio_cloud_records" not in cfg
    assert "miio_prop_3.1_template" not in cfg

    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    attrs = {c.attr for c in device.converters if c.domain == "sensor"}
    assert {"power_cost_today", "power_cost_month"} <= attrs

    # Power cost sensors are kWh energy sensors (the template already converts
    # raw 0.01 kWh counters to kWh; no extra value_ratio is applied).
    for name in ("power_cost_today", "power_cost_month"):
        conv = next(c for c in device.converters if c.attr == name)
        sensor = SensorEntity(device, conv)
        assert sensor.custom_value_ratio == 0
        assert sensor.device_class == "energy"
        assert sensor.state_class == "total_increasing"
        assert sensor.native_unit_of_measurement == "kWh"


def test_ykcn_switch_cbcsmj_uses_custom_statistics_template(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    commands = device.cloud_statistics_commands
    assert len(commands) == 1
    command = commands[0]
    assert command["key"] == "3.1"
    assert command["type"] == "stat_day_v3"
    assert command["template"] == "ykcn_switch_cbcsmj_power_cost"


def _rec(day, start, end):
    """A stat_day_v3 record: [start-of-day, end-of-day] cumulative counters."""
    ts = int(datetime.fromisoformat(day).replace(tzinfo=ZoneInfo("Asia/Shanghai")).timestamp())
    return {"time": ts, "value": json.dumps([int(round(start)), int(round(end))])}


@pytest.fixture
def shanghai(hass):
    original = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(ZoneInfo("Asia/Shanghai"))
    yield
    dt_util.set_default_time_zone(original)


@pytest.mark.parametrize(
    "now,records,expected",
    [
        # mid-month: today = end-start of today's snapshot; month = latest end
        # minus earliest start within the month (the lifetime counter never
        # resets, so a difference reproduces the app's 8.74 kWh).
        (
            "2026-10-31T12:00:00+08:00",
            [("2026-10-31", 9830, 9844), ("2026-10-30", 9801, 9829),
             ("2026-10-29", 9773, 9801), ("2026-10-01", 8970, 9001)],
            {"power_cost_today": 0.14, "power_cost_month": 8.74},
        ),
        # first of month: previous month's records must not leak into today or
        # the monthly difference.
        (
            "2026-11-01T12:00:00+08:00",
            [("2026-11-01", 500, 505), ("2026-10-31", 20000, 20100)],
            {"power_cost_today": 0.05, "power_cost_month": 0.05},
        ),
        # second of month: today uses only today's snapshot, month spans 11-01..
        (
            "2026-11-02T12:00:00+08:00",
            [("2026-11-02", 508, 516), ("2026-11-01", 500, 505),
             ("2026-10-31", 20000, 20100)],
            {"power_cost_today": 0.08, "power_cost_month": 0.16},
        ),
        # no record for today -> today unknown, month still reported
        (
            "2026-10-31T08:00:00+08:00",
            [("2026-10-30", 9801, 9829), ("2026-10-29", 9773, 9801)],
            {"power_cost_today": None, "power_cost_month": 0.56},
        ),
        # only one record today -> today and month both the snapshot delta
        (
            "2026-10-31T12:00:00+08:00",
            [("2026-10-31", 4000, 4200)],
            {"power_cost_today": 2.0, "power_cost_month": 2.0},
        ),
        # empty result
        ("2026-10-31T12:00:00+08:00", [], {"power_cost_today": None, "power_cost_month": None}),
    ],
)
def test_ykcn_switch_cbcsmj_power_cost_template(hass, freezer, shanghai, now, records, expected):
    freezer.move_to(now)
    result = template("ykcn_switch_cbcsmj_power_cost", hass).async_render(
        {"result": [_rec(day, start, end) for day, start, end in records]}
    )
    assert result["_entity_attrs"] is True
    assert result["power_cost_today"] == expected["power_cost_today"]
    assert result["power_cost_month"] == expected["power_cost_month"]


def test_ykcn_switch_cbcsmj_power_cost_template_ignores_bad_records(hass, freezer, shanghai):
    freezer.move_to("2026-10-31T12:00:00+08:00")
    result = template("ykcn_switch_cbcsmj_power_cost", hass).async_render({
        "result": [
            {"time": 0, "value": "bad"},
            {"time": 0, "value": "[]"},
            {"time": 0, "value": "[NaN]"},
            {"time": 0, "value": "[-1]"},
            {"time": 0, "value": "[5]"},  # single value: no end-of-day counter
            {"time": 0, "value": "[10,5]"},  # end < start: impossible snapshot
            _rec("2026-10-31", 1000, 1010),
        ],
    })
    assert result["power_cost_today"] == 0.1
    assert result["power_cost_month"] == 0.1


async def test_ykcn_switch_cbcsmj_cloud_statistics_differencing(hass, make_device, load_miot_spec, freezer, shanghai):
    freezer.move_to("2026-10-31T12:00:00+08:00")
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    response = {"code": 0, "result": [
        _rec("2026-10-31", 9830, 9844),
        _rec("2026-10-30", 9801, 9829),
        _rec("2026-10-29", 9773, 9801),
        _rec("2026-10-01", 8970, 9001),
    ]}
    device.cloud = SimpleNamespace(async_request_api=AsyncMock(return_value=response))
    device.dispatch = Mock()

    attrs = await device.update_cloud_statistics()

    assert attrs["power_cost_today"] == pytest.approx(0.14)
    assert attrs["power_cost_month"] == pytest.approx(8.74)
