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
            # 'low': '低档',
            # 'medium': '中档',
            # 'middle': '中档',
            # 'high': '高档',
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

        'door_state': {
            'open': '开门',
            'close': '关门',
            'close_timeout': '超时未关',
            'knock': '敲门',
            'breaking': '撬门',
            'stuck': '门卡住',
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

        'lock_method': {
            'bluetooth': '蓝牙',
            'password': '密码',
            'biological': '生物',
            'key': '钥匙',
            'turntable': '转盘',
            'nfc': 'NFC',
            'one-time password': '一次性密码',
            'two-step verification': '双重认证',
            'coercion': '胁迫',
            'homekit': 'Homekit',
            'manual': '人工',
            'automatic': '自动',
        },
        'lock_action': {
            'outside_unlock': '门外开锁',
            'lock': '上锁',
            'anti_lock_on': '开启反锁',
            'anti_lock_off': '解除反锁',
            'inside_unlock': '门内开锁',
            'lock_inside': '门内上锁',
            'child_lock_on': '开启童锁',
            'child_lock_off': '关闭童锁',
            'lock_outside': '门外上锁',
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

        'sweep.suction_state': {
            'medium': '中档',
            'silent': '安静',
            'slient': '安静',
            'standard': '标准',
            'turbo': '强力',
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

    'en': {
        'clean.mode': {
            '安静': 'Silent',
            '标准': 'Standard',
            '中档': 'Medium',
            '强力': 'Turbo',
        },
        'sweep.suction_state': {
            'slient': 'Silent',
            '关': 'Silent',
            '节能': 'Standard',
            '标准': 'Medium',
            '强劲': 'Turbo',
        },
        'sweep.water_state': {
            '低': 'Low',
            '中': 'Medium',
            '高': 'High',
        },
    },

    'pl': {
        'off': 'Wyłączony',
        'idle': 'Pracuje',
        'busy': 'Zajęty',
        'pause': 'Wstrzymany',
        'fault': 'Błąd',

        '_globals': {
            'mode': 'Tryb',
            'switch status': 'Status przełącznika',
            'battery level': 'Poziom baterii',
            'target temperature': 'Temperatura docelowa',
            'temperature': 'Temperatura',
            'relative humidity': 'Wilgotność',
            'illumination': 'Jasność',
            'indicator light': 'Wskaźnik światła',
            'physical control locked': 'Blokada fizyczna',
        },

        'fan_level': {
            'auto': 'auto',
            # 'low': 'niski',
            # 'medium': 'średni',
            # 'middle': 'średnio wysoki',
            # 'high': 'wysoki',
            'quiet': 'cichy',
            'turbo': 'turbo',
            'level1': 'poziom1',
            'level2': 'poziom2',
            'level3': 'poziom3',
            'level4': 'poziom4',
            'level5': 'poziom5',
            'level6': 'poziom6',
            'level7': 'poziom7',
        },

        'mode': {
            'auto': 'auto',
            'basic': 'podstawowy',
            'low': 'niski',
            'medium': 'średni',
            'high': 'wysoki',
            'sleep': 'nocny',
            'smart': 'smart',
            'favorite': 'ulubiony',
        },

        'air_conditioner': {
            'air conditioner': 'klimatyzacja',
        },

        'air_conditioner.mode': {
            'cool': 'chłodzenie',
            'dry': 'suszenie',
            'fan': 'wiatrak',
            'heat': 'grzanie',
        },

        'air_fresh.mode': {
            'auto': 'auto',
            'interval': 'przerywany',
            'smart': 'smart',
            'silent': 'cichy',
            'strong': 'mocny',
            'none': 'brak',
            'sleep': 'nocny',
            'favorite': 'ulubiony',
        },

        'battery': {
            'battery battery level': 'poziom baterii',
            'battery charging state': 'status baterii',
        },

        'fan.mode': {
            'basic': 'podstawowy',
            'basic wind': 'podstawowy wiatr',
            'straight wind': 'prosty wiatr',
            'natural wind': 'naturalny wiatr',
            'energy saving': 'oszczędzanie energii',
            'none': 'brak',
            'baby': 'dzieciecy',
            'smart': 'smart',
            'sleep': 'nocny',
            'strong': 'mocny',
            'circular wind': 'cyrkulacja wiatrem',
        },

        'ir_aircondition_control': {
            'ir aircondition control': 'pilot podczerwieni',
            'mode for ir': 'tryb dla pilota',
            'temperature for ir': 'temperatura dla pilota',
            'turn on': 'Włącz',
            'turn off': 'Wyłącz',
            'fan speed down': 'zmniejsz prędkość',
            'fan speed up': 'zwiększ prędkość',
            'temperature down': 'zmniejsz temperaturę',
            'temperature up': 'zwiększ temperaturę',
        },
        'ir_aircondition_control.ir_mode': {
            'auto': 'auto',
            'cool': 'chłodzenie',
            'dry': 'osuszanie',
            'fan': 'wiatrak',
            'heat': 'ogrzewanie',
        },

        'light': {
            'light': 'światło',
        },
        'light.mode': {
            'day': 'dzienne',
            'night': 'nocne',
            'color': 'kolor',
            'warmth': 'ciepło',
            'tv': 'telewizyjny',
            'reading': 'czytanie',
            'computer': 'komputerowy',
            'hospitality': 'gościnny',
            'entertainment': 'imprezowy',
            'lighting': 'oświetlający',
            'night light': 'nocny',
        },

        'magnet_sensor': {
            'magnet sensor': 'czujnik magnetyczny',
        },

        'motion_sensor': {
            'motion sensor': 'czujnik ruchu',
            'motion sensor illumination': 'czujnik światła',
        },

        'physical_control_locked': {
            'physical control locked': 'blokada fizyczna',
        },

        'play_control': {
            'play control': 'sterowanie odtwarzaniem',
            'keycodes': 'kody klawiszy',
        },

        'power_consumption': {
            'power consumption': 'pobór energii',
            'power consumption electric power': 'moc',
            'power consumption electric current': 'prąd',
            'power consumption electric voltage': 'napięcie',
        },

        'ptc_bath_heater': {
            'ptc bath heater': 'grzejnik łazienkowy',
        },
        'ptc_bath_heater.mode': {
            'fan': 'wiatrak',
            'heat': 'ogrzewanie',
            'ventilate': 'wentylacja',
            'dry': 'osuszanie',
            'defog': 'odparowanie',
            'quick heat': 'szybkie grzanie',
            'quick defog': 'szybkie odparowanie',
        },

        'speaker': {
            'speaker': 'głośnik',
            'speaker volume': 'głośność',
        },

        'television': {
            'input control': 'wejścia',
            'tv input control': 'TV wejścia',
        },

        'temperature_humidity_sensor': {
            'temperature humidity sensor temperature': 'temperatura',
            'temperature humidity sensor relative humidity': 'wilgotność',
            'temperature humidity sensor atmospheric pressure': 'ciśnienie',
        },

        'vacuum': {
            'robot cleaner': 'Odkurzacz',
            'robot cleaner status': 'stan',
        },

        'vacuum.mode': {
            'basic': 'podstawowy',
            'silent': 'cichy',
            'standard': 'standardowy',
            'strong': 'mocny',
            'turbo': 'turbo',
            'full speed': 'maksymalny',
        },

        'washer': {
            'drying level': 'poziom suszenia',
            'rinsh times': 'czas płukania',
            'spin speed': 'prędkość wirowania',
            'target water level': 'poziom wody',
        },
        'washer.mode': {
            'baby care': 'dziecięcy',
            'boiling': 'wyparzanie',
            'color protection': 'ochrona kolorów',
            'cotton': 'bawełna',
            'daily wash': 'codzienne',
            'delicate wash': 'delikatne',
            'down coat': 'kurtka puchowa',
            'drum clean': 'czyszczenie bębna ',
            'drum dry': 'suszenie bębna',
            'dry air wash': 'pranie suchym powietrzem',
            'dry timing': 'suszenie czasowe',
            'dry': 'suszenie',
            'gold wash': 'gold wash',
            'heavy wash': 'ciężkie pranie',
            'intensive': 'intensywny',
            'jacket': 'kurtka',
            'jeans': 'jeans',
            'mite removal': 'usuwanie roztoczy',
            'quick wash dry': 'szybkie pranie parowe',
            'quick wash': 'szybkie pranie',
            'rinse spin': 'wirowanie z płukaniem',
            'rinse': 'płukanie',
            'shirt': 'koszula',
            'silk': 'jedwab',
            'soak wash': 'namaczanie',
            'sock': 'skarpetki',
            'spin': 'wirowanie',
            'sportswear': 'odzież sportowa',
            'super quick': 'super szybkie',
            'synthetic': 'syntetyczne',
            'towel': 'ręczniki',
            'underwear': 'bielizna',
            'user define': 'ustawienia własne',
            'wash dry': 'pranie parowe',
            'wool': 'wełna',
        },
        'washer.drying_level': {
            'moist': 'wilgotny',
            'normal': 'nirmalny',
            'extra': 'ekstra',
            'none': 'brak',
        },

        'water_heater': {
            'water heater': 'podgrzewacz wody',
        },
    },
    'hu': {
        'off': 'Kikapcsolva',
        'idle': 'Tétlen',
        'busy': 'Elfoglalt',
        'pause': 'Szünetel',
        'fault': 'Hibás',

        '_globals': {
            'mode': 'Mód',
            'switch status': 'Kapcsoló állapota',
            'battery level': 'Akkumulátor szintje',
            'target temperature': 'Célhőmérséklet',
            'temperature': 'Hőmérséklet',
            'relative humidity': 'Relatív páratartalom',
            'illumination': 'Megvilágítás',
            'indicator light': 'Jelzőfény',
            'physical control locked': 'Fizikai vezérlés zárolva',
        },

        'fan_level': {
            'auto': 'auto',
            # 'low': 'alacsony',
            # 'medium': 'közepes',
            # 'middle': 'közepes',
            # 'high': 'magas',
            'quiet': 'halk',
            'turbo': 'turbó',
            'level1': 'szint1',
            'level2': 'szint2',
            'level3': 'szint3',
            'level4': 'szint4',
            'level5': 'szint5',
            'level6': 'szint6',
            'level7': 'szint7',
        },

        'mode': {
            'auto': 'auto',
            'basic': 'alap',
            'low': 'alacsony',
            'medium': 'közepes',
            'high': 'magas',
            'sleep': 'alvó',
            'smart': 'okos',
            'favorite': 'kedvenc',
        },

        'air_conditioner': {
            'air conditioner': 'légkondícionáló',
        },

        'air_conditioner.mode': {
            'cool': 'hűtés',
            'dry': 'szárítás',
            'fan': 'ventilátor',
            'heat': 'fűtés',
        },

        'air_fresh.mode': {
            'auto': 'auto',
            'interval': 'időszakos',
            'smart': 'okos',
            'silent': 'csendes',
            'strong': 'erős',
            'none': 'egyik sem',
            'sleep': 'alvó',
            'favorite': 'kedvenc',
        },

        'battery': {
            'battery battery level': 'akkumulátorszint',
            'battery charging state': 'akkumulátor töltés állapota',
        },

        'fan.mode': {
            'basic': 'alap',
            'basic wind': 'alap fújás',
            'straight wind': 'egyenes fújás',
            'natural wind': 'természetes szél',
            'energy saving': 'energiatakarékos',
            'none': 'brak',
            'baby': 'bébi',
            'smart': 'okos',
            'sleep': 'alvó',
            'strong': 'erős',
            'circular wind': 'körkörös fújás',
        },

        'ir_aircondition_control': {
            'ir aircondition control': 'infravörös légkondícionáló vezérlés',
            'mode for ir': 'infravörös módja',
            'temperature for ir': 'infravörös hőmérséklet',
            'turn on': 'bekapcsolás',
            'turn off': 'kikapcsolás',
            'fan speed down': 'ventilátor sebesség fel',
            'fan speed up': 'ventilátor sebesség le',
            'temperature down': 'hőmérséklet fel',
            'temperature up': 'hőmérséklet le',
        },
        'ir_aircondition_control.ir_mode': {
            'auto': 'auto',
            'cool': 'hűtés',
            'dry': 'szárítás',
            'fan': 'ventilátor',
            'heat': 'fűtés',
        },

        'light': {
            'light': 'fény',
        },
        'light.mode': {
            'day': 'nappal',
            'night': 'éjszaka',
            'color': 'szín',
            'warmth': 'meleg',
            'tv': 'televízió',
            'reading': 'olvasás',
            'computer': 'számítógép',
            'hospitality': 'vendégszeretet',
            'entertainment': 'szórakozás',
            'lighting': 'villámlás',
            'night light': 'éjjelifény',
        },

        'magnet_sensor': {
            'magnet sensor': 'mégneses érzékelő',
        },

        'motion_sensor': {
            'motion sensor': 'mozgásérzékelő',
            'motion sensor illumination': 'mozgásérzékelő fényerősség',
        },

        'physical_control_locked': {
            'physical control locked': 'fizikai vezérlés zárolva',
        },

        'play_control': {
            'play control': 'lejátszásvezérlés',
            'keycodes': 'kulcskódok',
        },

        'power_consumption': {
            'power consumption': 'enegriafogyasztás',
            'power consumption electric power': 'teljesítmény',
            'power consumption electric current': 'áramerősség',
            'power consumption electric voltage': 'feszültség',
        },

        'ptc_bath_heater': {
            'ptc bath heater': 'fürdőszobai hősugárzó',
        },
        'ptc_bath_heater.mode': {
            'fan': 'ventilátor',
            'heat': 'fűtés',
            'ventilate': 'szellőzés',
            'dry': 'szárítás',
            'defog': 'párátlanítás',
            'quick heat': 'gyors fűtés',
            'quick defog': 'gyors párátlanítás',
        },

        'speaker': {
            'speaker': 'hangszóró',
            'speaker volume': 'hangszóró hangereje',
        },

        'television': {
            'input control': 'bevitel vezérlés',
            'tv input control': 'TV bevitel vezérlés',
        },

        'temperature_humidity_sensor': {
            'temperature humidity sensor temperature': 'hőmérséklet',
            'temperature humidity sensor relative humidity': 'páratartalom',
            'temperature humidity sensor atmospheric pressure': 'légnyomás',
        },

        'vacuum': {
            'robot cleaner': 'robotporszívó',
            'robot cleaner status': 'állapot',
        },

        'vacuum.mode': {
            'basic': 'alap',
            'silent': 'csendes',
            'standard': 'alapértelmezett',
            'strong': 'erős',
            'turbo': 'turbó',
            'full speed': 'maximális sebesség',
        },

        'washer': {
            'drying level': 'szárítási szint',
            'rinsh times': 'öblítések száma',
            'spin speed': 'centrifuga sebesség',
            'target water level': 'cél víz szint',
        },
        'washer.mode': {
            'baby care': 'babaápolás',
            'boiling': 'kifőzés',
            'color protection': 'színvédelem',
            'cotton': 'gyapot',
            'daily wash': 'napi mosás',
            'delicate wash': 'finom mosás',
            'down coat': 'pehelykabát',
            'drum clean': 'dobtisztítás',
            'drum dry': 'szekrényszáraz',
            'dry air wash': 'száraz levegős mosás',
            'dry timing': 'szárítási idő',
            'dry': 'szárítás',
            'gold wash': 'gold wash',
            'heavy wash': 'nehéz szennyeződés',
            'intensive': 'intenzív',
            'jacket': 'dzseki',
            'jeans': 'farmer',
            'mite removal': 'atka eltávolító',
            'quick wash dry': 'gyors mosás és szárítás',
            'quick wash': 'gyors mosás',
            'rinse spin': 'centrifugálás öblítéssel',
            'rinse': 'öblítés',
            'shirt': 'póló',
            'silk': 'selyem',
            'soak wash': 'áztatásos mosás',
            'sock': 'zokni',
            'spin': 'kötött',
            'sportswear': 'sportruházat',
            'super quick': 'szupergyors',
            'synthetic': 'szintetikus',
            'towel': 'törölköző',
            'underwear': 'fehérnamű',
            'user define': 'egyéni beállítás',
            'wash dry': 'mosás és szárítás',
            'wool': 'gyapjú',
        },
        'washer.drying_level': {
            'moist': 'nedves',
            'normal': 'normál',
            'extra': 'extra',
            'none': 'egyik sem',
        },

        'water_heater': {
            'water heater': 'vízforraló',
        },
    },
}
