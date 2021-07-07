
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
        'cgllc.airm.cgdn1': {
            'chunk_properties': 9,
        },
        'deerma.humidifier.jsq3': {
            'chunk_properties': 6,
        },
        'yeelink.light.nl1': {
            'interval_seconds': 15,
        },
        'lumi.sensor_motion.*': {
            'interval_seconds': 15,
            'motion_timeout': 60,
        },
        'lumi.sensor_magnet.*': {
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

TRANSLATION_LANGUAGES = {
    'zh': {
        'off': '关闭',
        'idle': '空闲',
        'busy': '工作中',
        'pause': '暂停',
        'fault': '错误',

        'vacuum.mode': {
            'Silent': '安静',
            'Basic': '标准',
            'Strong': '强力',
        },

        'washer.mode': {
            'Daily Wash': '日常洗',
            'Quick Wash': '快速洗',
            'Delicate Wash': '轻柔洗',
            'Down Coat': '羽绒服',
            'Heavy Wash': '强力洗',
            'User Define': '自定义',
            'Rinse': '单漂洗',
            'Spin': '单脱水',
            'Cotton': '棉麻洗',
            'Synthetic': '化纤洗',
            'Shirt': '衬衣洗',
            'Boiling': '高温洗',
            'Wool': '羊毛洗',
            'Drum Clean': '筒自洁',
            'Baby Care': '婴童洗',
            'Intensive': '精细洗',
            'Jacket': '夹克洗',
            'Wash Dry': '洗+烘',
            'Underwear': '内衣洗',
            'Dry': '单烘干',
            'Dry Air Wash': '空气洗',
            'Quick Wash Dry': '快洗烘',
        },
        'washer.drying_level': {
            'moist': '微湿',
            'normal': '正常',
            'extra': '特干',
            'none': '无烘干',
        },
    },
}
