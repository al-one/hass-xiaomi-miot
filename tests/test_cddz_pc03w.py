"""Tests for the cddz.plug.pc03w bit fields and control constants."""

from custom_components.xiaomi_miot.cddz_pc03w.const import (
    CMD_FORCE_OFF,
    CMD_FORCE_RESTART,
    CMD_POWER_OFF,
    CMD_POWER_ON,
    CMD_RESTART,
    STATE_LABELS,
    extract_bits,
    set_bits,
)
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES


def test_power_control_values_match_vendor_plugin():
    assert CMD_POWER_ON == 0x00000001
    assert CMD_POWER_OFF == 0x00000000
    assert CMD_RESTART == 0x01000000
    assert CMD_FORCE_RESTART == 0x01000002
    assert CMD_FORCE_OFF == 0x01000001


def test_extract_prop_7_5_fields():
    value = 0x01010080  # indicator=1, power_on_state=1, child_lock=1
    assert extract_bits(value, 31, 8) == 1
    assert extract_bits(value, 23, 8) == 1
    assert extract_bits(value, 7, 1) == 1
    assert extract_bits(value, 6, 1) == 0


def test_set_bits_preserves_other_fields():
    value = 0x01010080
    value = set_bits(value, 6, 1, 1)  # xa_voice
    assert value == 0x010100C0
    value = set_bits(value, 31, 8, 2)  # indicator = always off
    assert value == 0x020100C0
    assert extract_bits(value, 23, 8) == 1
    assert extract_bits(value, 7, 1) == 1


def test_state_labels_cover_vendor_enum():
    assert STATE_LABELS == {
        0: "已开机",
        1: "开机中",
        2: "已关机",
        3: "关机中",
        4: "重启中",
        5: "强制重启中",
        6: "强制关机中",
    }


def test_native_switch_is_excluded():
    customize = DEVICE_CUSTOMIZES["cddz.plug.pc03w"]
    assert customize["exclude_miot_properties"] == "switch.on"
