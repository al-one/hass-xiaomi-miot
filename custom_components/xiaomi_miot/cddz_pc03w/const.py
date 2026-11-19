"""Constants for the CDDZ PC03W boot card integration."""

from __future__ import annotations

DOMAIN = "cddz_pc03w"
MODEL = "cddz.plug.pc03w"
NAME = "CDDZ PC03W 开机卡"

CONF_DID = "did"

# MIoT properties used by the vendor's Mi Home plugin.
PROP_SWITCH = {"siid": 2, "piid": 1}
PROP_CONFIG = {"siid": 7, "piid": 1}
PROP_PC_NUMBER = {"siid": 7, "piid": 2}
PROP_PC_STATE = {"siid": 7, "piid": 3}
PROP_KEY_BITS = {"siid": 7, "piid": 4}
PROP_SETTING_BITS = {"siid": 7, "piid": 5}
PROP_DURATION_BITS = {"siid": 7, "piid": 6}
PROP_UPTIME = {"siid": 9, "piid": 1}
PROP_OPEN_TIME_SET = {"siid": 6, "piid": 3}

POLL_PROPERTIES = [
    PROP_SWITCH,
    PROP_CONFIG,
    PROP_PC_NUMBER,
    PROP_PC_STATE,
    PROP_KEY_BITS,
    PROP_SETTING_BITS,
    PROP_DURATION_BITS,
    PROP_UPTIME,
    PROP_OPEN_TIME_SET,
]

# setting.ctrl (siid 6 / aiid 1) command values, taken from the official
# cddz.plug.pc03w Mi Home plugin (main.bundle, version 1.1.6).
CMD_POWER_ON = 0x00000001
CMD_POWER_OFF = 0x00000000
CMD_RESTART = 0x01000000
CMD_FORCE_RESTART = 0x01000002
CMD_FORCE_OFF = 0x01000001

# function.state (7.3) values
STATE_ON = 0
STATE_STARTING = 1
STATE_OFF = 2
STATE_STOPPING = 3
STATE_RESTARTING = 4
STATE_FORCE_RESTARTING = 5
STATE_FORCE_STOPPING = 6

STATE_LABELS = {
    STATE_ON: "已开机",
    STATE_STARTING: "开机中",
    STATE_OFF: "已关机",
    STATE_STOPPING: "关机中",
    STATE_RESTARTING: "重启中",
    STATE_FORCE_RESTARTING: "强制重启中",
    STATE_FORCE_STOPPING: "强制关机中",
}

# Bit positions inside function.data_b (7.5), as decoded by the vendor plugin.
# The first number is the most-significant bit index, the second is the width.
SETTING_BITS = {
    "indicator_light": (31, 8),
    "power_on_state": (23, 8),
    "hibernate_interval": (15, 8),
    "child_lock": (7, 1),
    "xa_voice": (6, 1),
    "hibernate": (5, 1),
    "parameter_lock": (4, 1),
    "power_reset": (3, 1),
    "local_timer": (2, 1),
    "reserved": (1, 2),
}

# Feature flags inside function.config (7.1).
CONFIG_BITS = {
    "isHasRestartCard": (31, 1),
    "isHasMultiRestartCard": (30, 1),
    "isHasBootStats": (29, 1),
    "isHasPcNumberSelect": (28, 1),
    "isHasVibrateSwitch": (27, 1),
    "isHasIndicatorLight": (26, 1),
    "isHasFreeSticker": (25, 1),
    "isHasChildLock": (24, 1),
    "isHasPowerOnState": (23, 1),
    "isHasControlPopup": (22, 1),
    "isHasProfessionalSetting": (21, 1),
    "isHasProfessionalSleepShutdown": (20, 1),
    "isHasProfessionalKeyDuration": (19, 1),
    "isHasProfessionalPowerTimeout": (18, 1),
    "isHasProfessionalMacSetting": (17, 1),
    "isHasOnTimeout": (16, 1),
    "isHasRandomExtends": (15, 1),
    "isHasHomeState": (14, 1),
    "isHasProfessionalParameterLock": (13, 1),
    "isHasPowerButtonReset": (12, 1),
    "isHasForceRestartCard": (11, 1),
    "isHasForceOffCard": (10, 1),
    "isHasFirstTime": (9, 1),
    "isHasLocalTimer": (8, 1),
    "isHasLoopTimer": (7, 1),
    "isHasSceneConfig": (6, 1),
}

# Bit positions inside function.data_a (7.4): key/remote button features.
KEY_BITS = {
    "long_press_duration": (31, 8),
    "single_click_mode": (23, 8),
    "double_click_mode": (15, 8),
    "long_press_mode": (7, 8),
}

# Bit positions inside function.data_c (7.6): press durations in 0.5 s units.
DURATION_BITS = {
    "on_duration": (31, 8),
    "off_duration": (23, 8),
    "restart_duration": (15, 8),
    "force_off_duration": (7, 8),
}

INDICATOR_LIGHT_OPTIONS = {
    0: "跟随",
    1: "常亮",
    2: "常灭",
}

POWER_ON_STATE_OPTIONS = {
    0: "关机",
    1: "开机",
    2: "记忆",
}

KEY_FEATURE_OPTIONS = {
    0: "无功能",
    1: "开机",
    2: "关机",
    3: "开/关机",
    4: "重启",
    5: "强制重启",
    6: "强制关机",
}


def extract_bits(value: int, msb: int, length: int) -> int:
    """Extract a bit field, where *msb* is the index of its highest bit."""
    shift = msb - length + 1
    return (int(value) >> shift) & ((1 << length) - 1)


def set_bits(value: int, msb: int, length: int, new_value: int) -> int:
    """Set a bit field, preserving all other bits."""
    shift = msb - length + 1
    mask = ((1 << length) - 1) << shift
    return (int(value) & ~mask) | ((int(new_value) & ((1 << length) - 1)) << shift)
