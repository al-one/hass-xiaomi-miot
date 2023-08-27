from enum import Enum
from typing import Union

from .device_customizes import DEVICE_CUSTOMIZES  # noqa
from .miot_local_devices import MIOT_LOCAL_MODELS  # noqa
from .translation_languages import TRANSLATION_LANGUAGES  # noqa

DOMAIN = 'xiaomi_miot'
DEFAULT_NAME = 'Xiaomi Miot'

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
    # hass 2020.12.2
    from homeassistant.components.number import DOMAIN as DOMAIN_NUMBER
    SUPPORTED_DOMAINS.append(DOMAIN_NUMBER)
except (ModuleNotFoundError, ImportError):
    DOMAIN_NUMBER = None

try:
    # hass 2021.7
    from homeassistant.components.select import DOMAIN as DOMAIN_SELECT
    SUPPORTED_DOMAINS.append(DOMAIN_SELECT)
except (ModuleNotFoundError, ImportError):
    DOMAIN_SELECT = None

try:
    # hass 2021.12
    from homeassistant.components.button import DOMAIN as DOMAIN_BUTTON
    SUPPORTED_DOMAINS.append(DOMAIN_BUTTON)
except (ModuleNotFoundError, ImportError):
    DOMAIN_BUTTON = None

try:
    # hass 2021.12
    from homeassistant.helpers.entity import EntityCategory
    ENTITY_CATEGORY_VIA_ENUM = True
except (ModuleNotFoundError, ImportError):
    class EntityCategory(Enum):
        CONFIG = 'config'
        DIAGNOSTIC = 'diagnostic'
        SYSTEM = 'system'
    ENTITY_CATEGORY_VIA_ENUM = False

try:
    # hass 2022.12
    from homeassistant.components.text import DOMAIN as DOMAIN_TEXT
    SUPPORTED_DOMAINS.append(DOMAIN_TEXT)
except (ModuleNotFoundError, ImportError):
    DOMAIN_TEXT = None

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
