# https://iot.mi.com/new/doc/tools-and-resources/design/spec/description
TRANSLATION_LANGUAGES = {

    'zh': {
        'off': '关闭',
        'idle': '空闲',
        'busy': '工作中',
        'pause': '暂停',
        'fault': '错误',

        '_globals': {
            'mode': '模式',
            'switch status': '开关',
            'battery level': '电量',
            'target temperature': '目标温度',
            'temperature': '温度',
            'relative humidity': '湿度',
            'illumination': '光照度',
            'indicator light': '指示灯',
            'physical control locked': '童锁',
        },

        'fan_level': {
            'auto': '自动',
            'low': '低档',
            'medium': '中档',
            'high': '高档',
            'quiet': '静音',
            'turbo': '超强',
            'level1': '一档',
            'level2': '二档',
            'level3': '三档',
            'level4': '四档',
            'level5': '五档',
            'level6': '六档',
            'level7': '七档',
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

        'air_conditioner': {
            'air conditioner': '空调',
        },

        'air_conditioner.mode': {
            'cool': '制冷',
            'dry': '除湿',
            'fan': '送风',
            'heat': '制热',
        },

        'air_fresh.mode': {
            'auto': '自动',
            'interval': '间歇',
            'smart': '智能',
            'silent': '静音',
            'strong': '强力',
            'none': '手动',
            'sleep': '睡眠',
            'favorite': '最爱',
        },

        'battery': {
            'battery battery level': '电量',
            'battery charging state': '充电状态',
        },

        'fan.mode': {
            'basic': '标准',
            'basic wind': '标准风',
            'straight wind': '直吹风',
            'natural wind': '自然风',
            'energy saving': '节能风',
            'none': '手动',
            'baby': '婴儿',
            'smart': '智能',
            'sleep': '睡眠',
            'strong': '强力',
            'circular wind': '循环风',
        },

        'ir_aircondition_control': {
            'ir aircondition control': '红外空调',
            'mode for ir': '模式',
            'temperature for ir': '目标温度',
            'turn on': '打开',
            'turn off': '关闭',
            'fan speed down': '风速-',
            'fan speed up': '风速+',
            'temperature down': '温度-',
            'temperature up': '温度+',
        },
        'ir_aircondition_control.ir_mode': {
            'auto': '自动',
            'cool': '制冷',
            'dry': '除湿',
            'fan': '风扇',
            'heat': '制热',
        },

        'light': {
            'light': '灯光',
        },
        'light.mode': {
            'day': '日光',
            'night': '夜光',
            'color': '彩光',
            'warmth': '温馨',
            'tv': '电视模式',
            'reading': '阅读模式',
            'computer': '电脑模式',
            'hospitality': '会客模式',
            'entertainment': '娱乐模式',
            'lighting': '照明',
            'night light': '夜灯',
        },

        'magnet_sensor': {
            'magnet sensor': '门窗传感器',
        },

        'motion_sensor': {
            'motion sensor': '运动侦测',
            'motion sensor illumination': '光照度',
        },

        'physical_control_locked': {
            'physical control locked': '物理锁',
        },

        'play_control': {
            'play control': '播放器',
            'keycodes': '遥控按键',
        },

        'power_consumption': {
            'power consumption': '用电量',
            'power consumption electric power': '功率',
            'power consumption electric current': '电流',
            'power consumption electric voltage': '电压',
        },

        'ptc_bath_heater': {
            'ptc bath heater': '浴霸',
        },
        'ptc_bath_heater.mode': {
            'fan': '吹风',
            'heat': '暖风',
            'ventilate': '换气',
            'dry': '除湿',
            'defog': '除雾',
            'quick heat': '极速加热',
            'quick defog': '快速除雾',
        },

        'speaker': {
            'speaker': '音响',
            'speaker volume': '音量',
        },

        'television': {
            'input control': '输入源',
            'tv input control': '输入源',
        },

        'temperature_humidity_sensor': {
            'temperature humidity sensor temperature': '温度',
            'temperature humidity sensor relative humidity': '湿度',
            'temperature humidity sensor atmospheric pressure': '气压',
        },

        'vacuum': {
            'robot cleaner': '扫地机',
            'robot cleaner status': '扫地机状态',
        },

        'vacuum.mode': {
            'basic': '正常',
            'silent': '安静',
            'standard': '正常',
            'strong': '强力',
            'turbo': '强力',
            'full speed': '全速',
        },

        'washer': {
            'drying level': '烘干级别',
            'rinsh times': '漂洗次数',
            'spin speed': '转速',
            'target water level': '水位',
        },
        'washer.mode': {
            'baby care': '婴童洗',
            'boiling': '高温洗',
            'color protection': '护色洗',
            'cotton': '棉麻洗',
            'daily wash': '日常洗',
            'delicate wash': '轻柔洗',
            'down coat': '羽绒服',
            'drum clean': '筒自洁',
            'drum dry': '筒风干',
            'dry air wash': '空气洗',
            'dry timing': '定时烘干',
            'dry': '单烘干',
            'gold wash': '黄金洗',
            'heavy wash': '强力洗',
            'intensive': '精细洗',
            'jacket': '夹克',
            'jeans': '牛仔',
            'mite removal': '除螨',
            'quick wash dry': '快洗烘',
            'quick wash': '快速洗',
            'rinse spin': '漂脱',
            'rinse': '单漂洗',
            'shirt': '衬衣',
            'silk': '丝绸',
            'soak wash': '浸泡洗',
            'sock': '袜子',
            'spin': '单脱水',
            'sportswear': '运动服',
            'super quick': '超快洗',
            'synthetic': '化纤洗',
            'towel': '毛巾',
            'underwear': '内衣',
            'user define': '自定义',
            'wash dry': '洗+烘',
            'wool': '羊毛洗',
        },
        'washer.drying_level': {
            'moist': '微湿',
            'normal': '正常',
            'extra': '特干',
            'none': '无烘干',
        },

        'water_heater': {
            'water heater': '热水器',
        },
    },

}
