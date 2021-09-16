from .device_customizes import DEVICE_CUSTOMIZES
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
    'number',
]

try:
    # hass 2021.7.0b0+
    from homeassistant.components.select import DOMAIN as DOMAIN_SELECT
    SUPPORTED_DOMAINS.append(DOMAIN_SELECT)
except ModuleNotFoundError:
    DOMAIN_SELECT = None


GLOBAL_CUSTOMIZES = {
    'models': DEVICE_CUSTOMIZES,
}
