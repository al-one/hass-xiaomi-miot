from enum import Enum
from typing import Union

from homeassistant.const import __version__ as HAVERSION  # noqa
from awesomeversion import AwesomeVersion
from .device_customizes import DEVICE_CUSTOMIZES, GLOBAL_CONVERTERS  # noqa
from .miot_local_devices import MIOT_LOCAL_MODELS  # noqa
from .translation_languages import TRANSLATION_LANGUAGES  # noqa

DOMAIN = 'xiaomi_miot'
DEFAULT_NAME = 'Xiaomi Miot'
HA_VERSION = AwesomeVersion(HAVERSION)

CONF_MODEL = 'model'
CONF_XIAOMI_CLOUD = 'xiaomi_cloud'
CONF_SERVER_COUNTRY = 'server_country'
CONF_CONN_MODE = 'conn_mode'
CONF_CONFIG_VERSION = 'config_version'

DEFAULT_CONN_MODE = 'cloud'

SUPPORTED_DOMAINS = [
    'sensor',
    'binary_sensor',
    'switch',
    'number',
    'select',
    'button',
    'text',
    'light',
    'fan',
    'climate',
    'cover',
    'humidifier',
    'media_player',
    'camera',
    'vacuum',
    'water_heater',
    'device_tracker',
    'remote',
    'alarm_control_panel',
]

CLOUD_SERVERS = {
    'cn': '中国大陆',
    'tw': '中國台灣',
    'de': 'Europe',
    'i2': 'India',
    'ru': 'Russia',
    'sg': 'Singapore',
    'us': 'United States',
}

try:
    # python 3.11
    from enum import StrEnum
except (ModuleNotFoundError, ImportError):
    class StrEnum(str, Enum):
        pass

try:
    # hass 2023.3
    from homeassistant.util.json import JsonObjectType
except (ModuleNotFoundError, ImportError):
    JsonObjectType = dict

try:
    # hass 2023.7
    from homeassistant.core import ServiceResponse, SupportsResponse
except (ModuleNotFoundError, ImportError):
    SupportsResponse = None
    ServiceResponse = Union[dict, None]

try:
    # hass 2024.10
    from homeassistant.components.camera import CameraState
except (ModuleNotFoundError, ImportError):
    class CameraState(StrEnum):
        RECORDING = 'recording'
        STREAMING = 'streaming'
        IDLE = 'idle'

try:
    # hass 2024.11
    from homeassistant.core_config import DATA_CUSTOMIZE
except (ModuleNotFoundError, ImportError):
    from homeassistant.helpers.entity import DATA_CUSTOMIZE

try:
    # hass 2024.11
    from homeassistant.components.alarm_control_panel import AlarmControlPanelState
except (ModuleNotFoundError, ImportError):
    class AlarmControlPanelState(StrEnum):
        """Alarm control panel entity states."""
        DISARMED = "disarmed"
        ARMED_HOME = "armed_home"
        ARMED_AWAY = "armed_away"
        ARMED_NIGHT = "armed_night"
        ARMED_VACATION = "armed_vacation"
        ARMED_CUSTOM_BYPASS = "armed_custom_bypass"
        PENDING = "pending"
        ARMING = "arming"
        DISARMING = "disarming"
        TRIGGERED = "triggered"