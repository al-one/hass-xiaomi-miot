from enum import StrEnum

from awesomeversion import AwesomeVersion
from homeassistant.components.alarm_control_panel.const import AlarmControlPanelState
from homeassistant.components.camera.const import CameraState
from homeassistant.components.vacuum.const import VacuumActivity
from homeassistant.const import __version__ as HAVERSION  # noqa
from homeassistant.core import ServiceResponse, SupportsResponse
from homeassistant.core_config import DATA_CUSTOMIZE

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
    'time',
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
    # hass 2026.7
    from homeassistant.const import UnitOfDensity, UnitOfRatio
except (ModuleNotFoundError, ImportError):
    class UnitOfDensity(StrEnum):
        """Density units."""
        MILLIGRAMS_PER_CUBIC_METER = "mg/m³"
        MICROGRAMS_PER_CUBIC_METER = "μg/m³"

    class UnitOfRatio(StrEnum):
        """Ratio units."""
        PARTS_PER_MILLION = "ppm"
