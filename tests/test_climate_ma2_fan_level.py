"""Regression coverage for duplicate fan-level properties in v3 AC specs (#2956).

xiaomi.aircondition.ma2 (v3) exposes two same-named ``fan-level`` properties
in the ``fan-control`` service: a discrete ``value-list`` (incl. Auto) and a
stepless ``value-range`` (1..101). Both share ``friendly_name`` so the climate
converter picks up both; without the guard the stepless (value-range) override
wins and ``fan_modes`` becomes 101 levels with no ``auto``.
"""

import pytest

from custom_components.xiaomi_miot.climate import ClimateEntity
from custom_components.xiaomi_miot.core.converters import MiotClimateConv


def _climate_conv(device):
    return next(c for c in device.converters if isinstance(c, MiotClimateConv))


def _fan_modes(entity):
    assert entity._attr_fan_modes  # FAN_MODE feature detected
    return entity._attr_fan_modes


def test_climate_prefers_discrete_fan_level_over_stepless(make_device, load_miot_spec):
    device = make_device(load_miot_spec("xiaomi.aircondition.ma2.json"))
    entity = ClimateEntity(device, _climate_conv(device))

    modes = _fan_modes(entity)
    assert "auto" in modes
    assert len(modes) == 8  # Auto + Level1..7, not 101
    assert "101" not in modes


def test_climate_stepless_fan_alone_still_works(make_device, load_miot_spec):
    device = make_device(load_miot_spec("xiaomi.aircondition.ma2.json"))
    conv = _climate_conv(device)
    # Drop the discrete fan-level property, keep only the stepless value-range.
    for attr in list(conv.attrs):
        prop = device.find_converter(attr).prop
        if prop and prop.name == "fan_level" and prop.value_list:
            conv.attrs.remove(attr)

    entity = ClimateEntity(device, conv)
    modes = _fan_modes(entity)
    # value-range fan_level still provides a fan (1..101) when no discrete one exists.
    assert len(modes) == 101