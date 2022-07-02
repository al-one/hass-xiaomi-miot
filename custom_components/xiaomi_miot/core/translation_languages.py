# https://iot.mi.com/new/doc/tools-and-resources/design/spec/description
TRANSLATION_LANGUAGES = {
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

    'en': {
        'clean.mode': {
            '安静': 'Silent',
            '标准': 'Standard',
            '中档': 'Medium',
            '强力': 'Turbo',
        },
        'sweep.suction_state': {
            '关': 'Silent',
            '节能': 'Standard',
            '标准': 'Medium',
            '强劲': 'Turbo',
        },
    },
}
