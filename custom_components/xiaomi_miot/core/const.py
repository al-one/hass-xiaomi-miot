
DOMAIN = 'xiaomi_miot'
DEFAULT_NAME = 'Xiaomi Miot'

CONF_MODEL = 'model'
CONF_XIAOMI_CLOUD = 'xiaomi_cloud'
CONF_SERVER_COUNTRY = 'server_country'
CONF_CONFIG_VERSION = 'config_version'

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
    'air_quality',
    'water_heater',
    'device_tracker',
    'number',
]

GLOBAL_CUSTOMIZES = {

    'models': {
        'chuangmi.plug.212a01': {
            'chunk_properties': 7,
        },
        'deerma.humidifier.jsq3': {
            'chunk_properties': 6,
        },
        'yeelink.light.nl1': {
            'interval_seconds': 15,
        },
        'xiaomi.tv.*': {
            'number_properties': 'speaker.volume',
        },
        '*.fishbowl.*': {
            'number_properties': 'feeding_measure',
        },
        '*.feeder.*': {
            'number_properties': 'feeding_measure',
        },
    },

}
