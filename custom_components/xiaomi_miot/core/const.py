
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

    'models': {
        'cgllc.airm.cgdn1': {
            'chunk_properties': 9,
        },
        'chuangmi.plug.212a01': {
            'chunk_properties': 7,
        },
        'chuangmi.plug.212a01:electric_power': {
            'value_ratio': 0.01,
        },
        'chuangmi.plug.v3': {
            'sensor_attributes': 'electric_power,prop_cal_day.power_cost:today,prop_cal_day.power_cost:month',
            'sensor_miio_commands': {
                'get_power': {
                    'params': [],
                    'values': ['electric_power'],
                },
            },
            'miio_cloud_records': 'prop_cal_day.power_cost:31',
            'miio_prop_cal_day_power_cost_template': "{%- set val = (result.0 | default({})).get('value',{}) %}"
                                                     "{%- set day = now().day %}"
                                                     "{{ {"
                                                     "'today': val.pc | default(0),"
                                                     "'today_duration': val.pc_time | default(0),"
                                                     "'month': result[:day] | sum(attribute='value.pc'),"
                                                     "'month_duration': result[:day] | sum(attribute='value.pc_time'),"
                                                     "} }}",
        },
        'chuangmi.plug.v3:electric_power': {
            'value_ratio': 0.01,
            'device_class': 'power',
            'unit_of_measurement': 'W',
        },
        'chuangmi.plug.v3:prop_cal_day.power_cost:today': {
            'value_ratio': 0.001,
            'device_class': 'energy',
            'unit_of_measurement': 'kWh',
        },
        'chuangmi.plug.v3:prop_cal_day.power_cost:month': {
            'value_ratio': 0.001,
            'device_class': 'energy',
            'unit_of_measurement': 'kWh',
        },
        'chuangmi.plug.*': {
            'sensor_properties': 'temperature',
        },
        'chunmi.health_pot.a1': {
            'miot_local': True,
        },
        'cuco.plug.cp1m': {
            'sensor_properties': 'power_consumption,voltage,electric_current',
        },
        'deerma.humidifier.jsq3': {
            'chunk_properties': 6,
        },
        'hyd.airer.*': {
            'disable_target_position': True,
            'cover_position_mapping': {
                0: 50,
                1: 100,
                2: 0,
            },
        },
        'lumi.sensor_motion.*': {
            'interval_seconds': 15,
            'motion_timeout': 60,
        },
        'lumi.sensor_magnet.*': {
            'interval_seconds': 15,
        },
        'philips.light.cbulb': {
            'miot_cloud_write': True,
            'miot_local_mapping': {
                'light.on': {'siid': 2, 'piid': 1},
                'light.mode': {'siid': 2, 'piid': 2},
                'light.brightness': {'siid': 2, 'piid': 3},
                'light.color': {'siid': 2, 'piid': 4},
                'light.color_temperature': {'siid': 2, 'piid': 5},
            },
        },
        'rockrobo.vacuum.*': {
            'sensor_attributes': 'props:clean_area,props:clean_time',
            'sensor_miio_commands': {
                'get_status': ['props'],
                'get_consumable': ['consumables'],
            },
        },
        'rockrobo.vacuum.*:props:clean_area': {
            'value_ratio': 0.000001,
            'unit_of_measurement': '㎡',
        },
        'rockrobo.vacuum.*:props:clean_time': {
            'value_ratio': 0.016666,
            'unit_of_measurement': 'min',
        },
        'viomi.vacuum.*': {
            'sensor_attributes': 'miio.s_area,miio.s_time',
            'miio_properties': 'run_state,mode,err_state,battary_life,box_type,mop_type,s_time,s_area,'
                               'suction_grade,water_grade,remember_map,has_map,is_mop,has_newmap',
        },
        'xiaomi.tv.*': {
            'number_properties': 'speaker.volume',
        },
        'yeelink.light.nl1': {
            'interval_seconds': 15,
        },
        '*.airer.*': {
            'sensor_properties': 'left_time',
            'switch_properties': 'dryer,uv',
            'fan_properties': 'drying_level',
        },
        '*.cooker.*': {
            'sensor_properties': 'temperature,left_time',
            'switch_properties': 'cooker.on,auto_keep_warm',
        },
        '*.feeder.*': {
            'switch_properties': 'feeding_measure',
        },
        '*.fishbowl.*': {
            'switch_properties': 'feeding_measure',
        },
        '*.lock.*': {
            'sensor_attributes': 'event.7:door_state,event.11:lock_state,event.11:key_id',
            'miio_cloud_records': 'event.7:1,event.11:1',
            'miio_event_7_template':  "{%- set val = (result.0 | default({})).get('value','[-1]') %}"
                                      "{%- set val = (val | from_json).0 | string %}"
                                      "{%- set evt = val[:2] | int(-1,16) %}"
                                      "{%- set els = ['open','close','close_timeout',"
                                      "'knock','breaking','stuck','unknown'] %}"
                                      "{{ {"
                                      "'door_event': evt,"
                                      "'door_state': els[evt] | default('unknown'),"
                                      "} }}",
            'miio_event_11_template': "{%- set val = (result.0 | default({})).get('value','[-1]') %}"
                                      "{%- set val = (val | from_json).0 | string %}"
                                      "{%- set evt = val[:2] | int(-1,16) % 16 %}"
                                      "{%- set how = val[:2] | int(-1,16) // 16 %}"
                                      "{%- set key = (0).from_bytes((0).to_bytes(0,'little')"
                                      ".fromhex(val[2:10]), 'little') %}"
                                      "{%- set els = ['outside_unlock','lock','anti_lock_on','anti_lock_off',"
                                      "'inside_unlock','lock_inside','child_lock_on','child_lock_off','unknown'] %}"
                                      "{%- set mls = ['bluetooth','password','biological','key','turntable',"
                                      "'nfc','one-time password','two-step verification','coercion','homekit',"
                                      "'manual','automatic','unknown'] %}"
                                      "{{ {"
                                      "'lock_event': evt,"
                                      "'lock_state': els[evt] | default('unknown'),"
                                      "'method_id': how,"
                                      "'method': mls[how] | default('unknown'),"
                                      "'key_id': key,"
                                      "} }}",
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

        'fan_level': {
            'auto': '自动',
            'low': '低档',
            'medium': '中档',
            'high': '高档',
        },

        'mode': {
            'auto': '自动',
            'basic': '标准',
            'low': '低档',
            'medium': '中档',
            'high': '高档',
            'sleep': '睡眠模式',
            'smart': '智能模式',
            'favorite': '喜爱模式',
        },

        'air_conditioner.mode': {
            'Cool': '制冷',
            'Dry': '除湿',
            'Fan': '风扇',
            'Heat': '制热',
        },

        'air_fresh.mode': {
            'Interval': '间歇模式',
        },

        'fan.mode': {
            'Straight Wind': '直吹风',
            'Natural Wind': '自然风',
        },

        'light.mode': {
            'Day': '日光',
            'Night': '夜灯',
            'Color': '彩光',
        },

        'ptc_bath_heater.mode': {
            'Fan': '吹风',
            'Heat': '暖风',
            'Ventilate': '换气',
            'Dry': '除湿',
            'Defog': '除雾',
        },

        'vacuum.mode': {
            'Silent': '安静',
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
