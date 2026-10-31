import json
from datetime import datetime

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
    assert {"electric_power", "voltage", "electric_current"} <= set(sensors)
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


def test_ykcn_switch_cbcsmj_power_cost_uses_raw_cloud_records(make_device, load_miot_spec):
    cfg = DEVICE_CUSTOMIZES[MODEL]
    # The vendor app reads cumulative energy from raw prop 3.1 records, not the
    # v2/user/statistics daily aggregate.
    assert cfg["miio_cloud_records"] == "prop.3.1:32:raw"
    assert cfg["miio_prop_3.1_template"] == "ykcn_switch_cbcsmj_power_cost"
    assert cfg["sensor_attributes"] == "power_cost_today,power_cost_month"
    assert "stat_power_cost_key" not in cfg

    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    attrs = {c.attr for c in device.converters if c.domain == "sensor"}
    assert {"power_cost_today", "power_cost_month"} <= attrs

    # Power cost sensors are kWh energy sensors (raw records are 0.01 kWh, so
    # the template already converts to kWh; no extra value_ratio is applied).
    for name in ("power_cost_today", "power_cost_month"):
        conv = next(c for c in device.converters if c.attr == name)
        sensor = SensorEntity(device, conv)
        assert sensor.custom_value_ratio == 0
        assert sensor.device_class == "energy"
        assert sensor.state_class == "total_increasing"
        assert sensor.native_unit_of_measurement == "kWh"


def _rec(day, cum):
    ts = int(datetime.fromisoformat(day).replace(tzinfo=ZoneInfo("Asia/Shanghai")).timestamp())
    return {"time": ts, "value": json.dumps([int(round(cum * 100))])}


@pytest.fixture
def shanghai(hass):
    original = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(ZoneInfo("Asia/Shanghai"))
    yield
    dt_util.set_default_time_zone(original)


@pytest.mark.parametrize(
    "now,records,expected",
    [
        # mid-month: today = latest-today - latest-yesterday, month = month-to-date
        (
            "2026-10-31T12:00:00+08:00",
            [("2026-10-31T09:00:00", 130.5), ("2026-10-30T20:00:00", 123.0),
             ("2026-10-30T08:00:00", 120.5), ("2026-10-29T08:00:00", 100.0)],
            {"power_cost_today": 7.5, "power_cost_month": 130.5},
        ),
        # first of month: previous month's records must not leak into today
        (
            "2026-11-01T12:00:00+08:00",
            [("2026-11-01T09:00:00", 5.0), ("2026-10-31T20:00:00", 200.0)],
            {"power_cost_today": 5.0, "power_cost_month": 5.0},
        ),
        # second of month: today uses previous day within the same month
        (
            "2026-11-02T12:00:00+08:00",
            [("2026-11-02T09:00:00", 8.0), ("2026-11-01T20:00:00", 5.0),
             ("2026-10-31T20:00:00", 200.0)],
            {"power_cost_today": 3.0, "power_cost_month": 8.0},
        ),
        # no record for today -> today unknown, month still reported
        (
            "2026-10-31T08:00:00+08:00",
            [("2026-10-30T20:00:00", 123.0), ("2026-10-29T08:00:00", 100.0)],
            {"power_cost_today": None, "power_cost_month": 123.0},
        ),
        # only one record today -> equals the month-to-date counter
        (
            "2026-10-31T12:00:00+08:00",
            [("2026-10-31T09:00:00", 42.0)],
            {"power_cost_today": 42.0, "power_cost_month": 42.0},
        ),
        # empty result
        ("2026-10-31T12:00:00+08:00", [], {"power_cost_today": None, "power_cost_month": None}),
    ],
)
def test_ykcn_switch_cbcsmj_power_cost_template(hass, freezer, shanghai, now, records, expected):
    freezer.move_to(now)
    result = template("ykcn_switch_cbcsmj_power_cost", hass).async_render(
        {"result": [_rec(day, cum) for day, cum in records]}
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
            _rec("2026-10-31T09:00:00", 10.0),
        ],
    })
    assert result["power_cost_today"] == 10.0
    assert result["power_cost_month"] == 10.0
