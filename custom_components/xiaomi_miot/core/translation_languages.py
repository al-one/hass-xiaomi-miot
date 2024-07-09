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

        'clock': {
            'stop alarm': '关掉闹钟'
        },

        'fan_level': {
            # 'auto': '自动',
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

        'environment': {
            'environment air quality': '空气质量',
            'environment temperature': '温度',
            'environment relative humidity': '湿度',
            'environment pm2.5 density': 'PM2.5 浓度',
            'environment co2 density': 'CO2 浓度',
            'environment tvoc density': 'TVOC 浓度'
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

        'filter': {
            'filter left time': '滤芯剩余时间',
            'filter used time': '滤芯已用时间',
            'filter life level': '滤芯剩余寿命',
        },

        'intelligent_speaker': {
            'wake up': '唤醒',
            'play music': '播放音乐',
            'play radio': '播放广播',
            'play text': '朗读文本',
            'execute text directive': '执行指令'
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
            'one_time_password': '一次性密码',
            'two_step_verification': '双重认证',
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
            'magnet sensor illumination': '光照度',
        },

        'motion_sensor': {
            'motion sensor': '运动侦测',
            'motion sensor illumination': '光照度',
        },

        'occupancy_sensor': {
            'occupancy sensor occupancy status': '状态'
        },
        'occupancy_sensor.occupancy_status': {
            'someone exists': '有人',
            'no one exists': '无人'
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
            'power consumption voltage': '电压',
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
            'drying time': '烘干时长',
            'high water switch': '高水位',
            'rinsh times': '漂洗次数',
            'shake time': '清新抖散',
            'sleep mode': '夜间洗',
            'soak time': '浸泡时长',
            'spin speed': '脱水转速',
            'start wash': '开始洗涤',
            'status': '工作状态',
            'steam sterilization': '蒸汽除菌',
            'target temperature': '洗涤温度',
            'target water level': '水位',
        },
        'washer.mode': {
            'aromatherapy wash': '香薰洗',
            'baby care': '婴童洗',
            'bacteria mite removal': '除菌螨',
            'boiling': '高温洗',
            'color protection': '护色洗',
            'cotton': '棉麻洗',
            'daily wash': '日常洗',
            'delicate wash': '轻柔洗',
            'down coat': '羽绒服',
            'drum clean': '筒清洁',
            'drum dry': '筒风干',
            'dry air wash': '轻干洗',
            'dry timing': '定时烘干',
            'dry': '单烘干',
            'gold wash': '黄金洗',
            'heavy wash': '大件洗',
            'intensive': '强力洗',
            'jacket': '冲锋衣',
            'jeans': '牛仔洗',
            'mite removal': '除螨',
            'mix': '混合洗',
            'new clothes wash': '新衣洗',
            'pleased wash dry': '随心洗烘',
            'quick wash dry': '快洗烘',
            'quick wash': '快速洗',
            'rinse spin': '漂+脱',
            'rinse': '单漂洗',
            'shirt': '衬衣',
            'silk': '真丝洗',
            'smart': '智能洗',
            'soak wash': '浸泡洗',
            'sock': '袜子',
            'spin': '单脱水',
            'sportswear': '运动服',
            'super quick': '超快洗',
            'synthetic': '化纤洗',
            'towel': '毛巾',
            'underwear': '内衣洗',
            'user define': '自定义',
            'wash dry': '洗+烘',
            'wool': '羊毛洗',
        },
        'washer.drying_level': {
            'extra': '特干',
            'moist': '微湿',
            'none': '不烘干',
            'normal': '正常',
            'smart': '智能烘干',
            'timed': '定时烘干',
        },

        'dishwasher': {
            'dishwasher status': '状态',
            'dishwasher switch status': '开关',
            'dishwasher mode': '洗涤模式',
            'Start Wash': '开始洗涤',
            'Stop Washing': '停止洗涤',
            'dishwasher left time': '洗涤剩余时间',
        },
        'dishwasher.mode': {            
            'Basic': '标准洗',
            'Energy Saving': '节能洗',
            'Quick Wash': '快速洗',
            'Intensive': '强力洗',
            'Glass': '玻璃洗',
            'Disinfecting': '消毒洗',
        },
        'dishwasher.status': {            
            'Off': '已关机',
            'Idle': '已停止',
            'Busy': '工作中',
            'Paused': '暂停',
            'Completed': '洗涤完成',
            'Delay': '已预约',
            'Preservation': '保留',
        },

        'water_heater': {
            'water heater': '热水器',
        },
        'water_heater.mode': {
            'low': '低温',
            'medium': '中温',
            'high': '高温'
        },
        'airer': {
            'airer': '晾衣架',
            'dryer': '干燥功能',
            'drying_level': '烘干级别',
            'left_time': '剩余时间',
            'fault': '设备故障',
        },
        'airer.dryer': {
            'Air Drying': '风干',
            'Hot Air Drying': '烘干',
        },
        'airer.fault': {
            'No Faults': '无故障',
            'Obstruction': '遇阻',
            'Overweight': '超重',
            'Overheat': '过热',
            'Motor Failure': '电机故障',
        },
    },

    'el': {
        'off': 'Κλειστή',
        'idle': 'Αδρανής',
        'busy': 'Σε λειτουργία',
        'pause': 'Σε παύση',
        'fault': 'Σφάλμα',

        '_globals': {
            'mode': 'Λειτουργία',
            'switch status': 'Διακόπτες',
            'battery level': 'Επίπεδο μπαταρίας',
            'target temperature': 'Θερμοκρασία-στόχος',
            'temperature': 'Θερμοκρασία',
            'relative humidity': 'Σχετική υγρασία',
            'illumination': 'Φωτισμός',
            'indicator light': 'Ενδεικτική λυχνία',
            'physical control locked': 'Φυσικός έλεγχος κλειδωμένος',
        },

        'clock': {
            'stop alarm': 'Διακοπή ξυπνητηριού'
        },

        'fan_level': {
            'auto': 'Αυτόματο',
            # 'low': 'Χαμηλό',
            # 'medium': 'Μεσαίο',
            # 'middle': 'Μεσαίο',
            # 'high': 'Υψηλό',
            'quiet': 'Ήσυχο',
            'turbo': 'Τούρμπο',
            'level1': 'Επίπεδο 1',
            'level2': 'Επίπεδο 2',
            'level3': 'Επίπεδο 3',
            'level4': 'Επίπεδο 4',
            'level5': 'Επίπεδο 5',
            'level6': 'Επίπεδο 6',
            'level7': 'Επίπεδο 7',
        },

        'mode': {
            'auto': 'Αυτόματη',
            'basic': 'Βασική',
            'low': 'Χαμηλή',
            'medium': 'Μεσαία',
            'high': 'Υψηλή',
            'sleep': 'Ύπνος',
            'smart': 'Έξυπνη',
            'favorite': 'Αγαπημένη',
        },

        'air_conditioner': {
            'air conditioner': 'Κλιματισμός',
        },

        'air_conditioner.mode': {
            'cool': 'Ψύξη',
            'dry': 'Αφύγρανση',
            'fan': 'Ανεμιστήρας',
            'heat': 'Θέρμανση',
        },

        'air_fresh.mode': {
            'auto': 'Αυτόματη',
            'interval': 'Διαλείπουσα',
            'smart': 'Έξυπνη',
            'silent': 'Ήσυχη',
            'strong': 'Έντονη',
            'none': 'Καμία',
            'sleep': 'Ύπνος',
            'favorite': 'Αγαπημένη',
        },

        'battery': {
            'battery battery level': 'Επίπεδο μπαταρίας',
            'battery charging state': 'Κατάσταση φόρτισης μπαταρίας',
        },

        'door_state': {
            'open': 'Ανοιχτή',
            'close': 'Κλειστή',
            'close_timeout': 'Χρονικό όριο κλεισίματος',
            'knock': 'Χτύπημα',
            'breaking': 'Σπάσιμο',
            'stuck': 'Κόλλησε',
        },

        'environment': {
            'environment temperature': 'Θερμοκρασία',
            'environment relative humidity': 'Σχετική υγρασία περιβάλλοντος',
            'environment pm2.5 density': 'Πυκνότητα περιβάλλοντος PM2.5',
            'environment co2 density': 'Περιβαλλοντική πυκνότητα co2',
            'environment tvoc density': 'Περιβαλλοντική πυκνότητα TVOC'
        },

        'fan.mode': {
            'basic': 'Βασική',
            'basic wind': 'Βασικός άνεμος',
            'straight wind': 'Δυνατός άνεμος',
            'natural wind': 'Φυσικός άνεμος',
            'energy saving': 'Εξοικονόμηση ενέργειας',
            'none': 'Καμία',
            'baby': 'Μωρό',
            'smart': 'Έξυπνη',
            'sleep': 'Ύπνος',
            'strong': 'Δυνατή',
            'circular wind': 'Κυκλικός άνεμος',
        },

        'intelligent_speaker': {
            'wake up': 'Ξύπνημα',
            'play music': 'Αναπαραγωγή μουσικής',
            'play radio': 'Αναπαραγωγή ραδιοφώνου',
            'play text': 'Αναπαραγωγή κειμένου',
            'execute text directive': 'Εκτέλεση οδηγίας κειμένου'
        },

        'ir_aircondition_control': {
            'ir aircondition control': 'Υπέρυθρος έλεγχος κλιματισμού',
            'mode for ir': 'Λειτουργία υπέρθυθρων',
            'temperature for ir': 'θερμοκρασία-στόχος',
            'turn on': 'Ενεργοποίηση',
            'turn off': 'Απενεργοποίηση',
            'fan speed down': 'Ταχύτητα ανεμιστήρα -',
            'fan speed up': 'Ταχύτητα ανεμιστήρα +',
            'temperature down': 'Θερμοκρασία -',
            'temperature up': 'Θερμοκρασία +',
        },
        'ir_aircondition_control.ir_mode': {
            'auto': 'Αυτόματο',
            'cool': 'Ψύξη',
            'dry': 'Αφύγρανση',
            'fan': 'Ανεμιστήρας',
            'heat': 'Θέρμανση',
        },

        'light': {
            'light': 'Φωτισμός',
        },
        'light.mode': {
            'day': 'Ημέρα',
            'night': 'Νύχτα',
            'color': 'Χρώμα',
            'warmth': 'Κορεσμός',
            'tv': 'Τηλεόραση',
            'reading': 'Διάβασμα',
            'computer': 'Υπολογιστής',
            'hospitality': 'Φιλοξενία',
            'entertainment': 'Διασκέδαση',
            'lighting': 'Φωτισμός',
            'night light': 'Φωτισμός νυχτός',
        },

        'lock_method': {
            'bluetooth': 'Bluetooth',
            'password': 'Κωδικός πρόσβασης',
            'biological': 'Βιομετρικά',
            'key': 'Κλειδί',
            'turntable': 'Με περιστρεφή',
            'nfc': 'NFC',
            'one_time_password': 'Κωδικός πρόσβασης μίας χρήσης',
            'two_step_verification': 'Διπλή διαπίστευση',
            'coercion': 'Εξαναγκασμός',
            'homekit': 'Homekit',
            'manual': 'Χειροκίνητη',
            'automatic': 'Αυτόματη',
        },
        'lock_action': {
            'outside_unlock': 'Ξεκλείδωμα εξωτερικής πόρτας',
            'lock': 'Κλείδωμα',
            'anti_lock_on': 'Ενεργοποίηση αντίστροφης κλειδαριάς',
            'anti_lock_off': 'Απενεργοποίηση αντίστροφης κλειδαριάς',
            'inside_unlock': 'Ξεκλείδωμα από μέσα',
            'lock_inside': 'Κλείδωμα μέσα',
            'child_lock_on': 'Ενεργοποίηση παιδικού κλειδώματος',
            'child_lock_off': 'Απενεργοποίηση παιδικού κλειδώματος',
            'lock_outside': 'Κλείδωμα εξωτερικής πόρτας',
        },

        'magnet_sensor': {
            'magnet sensor': 'Αισθητήρες θυρών και παραθύρων',
        },

        'motion_sensor': {
            'motion sensor': 'Ανίχνευση κίνησης',
            'motion sensor illumination': 'Ανίχνευση φωτισμού',
        },

        'occupancy_sensor': {
            'occupancy sensor occupancy status': 'Κατάσταση αισθητήρα παρουσίας'
        },
        'occupancy_sensor.occupancy_status': {
            'someone exists': 'Κάποιος υπάρχει',
            'no one exists': 'Κάποιος δεν υπάρχει'
        },

        'physical_control_locked': {
            'physical control locked': 'Κλείδωμα φυσικού ελέγχου',
        },

        'play_control': {
            'play control': 'Έλεγχος αναπαραγωγής',
            'keycodes': 'Κωδικοί κλειδιών',
        },

        'power_consumption': {
            'power consumption': 'Κατανάλωση ενέργειας',
            'power consumption electric power': 'Κατανάλωση ηλεκτρικής ενέργειας',
            'power consumption electric current': 'Κατανάλωση ηλεκτρικού ρεύματος',
            'power consumption electric voltage': 'Κατανάλωση ηλεκτρικής τάσης',
        },

        'ptc_bath_heater': {
            'ptc bath heater': 'Θερμαντήρας μπάνιου ptc',
        },
        'ptc_bath_heater.mode': {
            'fan': 'Ανεμιστήρας',
            'heat': 'Θέρμανση',
            'ventilate': 'Εξαερισμός',
            'dry': 'Αφύγρανση',
            'defog': 'Αποθαμβωτικό',
            'quick heat': 'Γρήγορη ζέστη',
            'quick defog': 'Γρήγορο αποθαμβωτικό',
        },

        'speaker': {
            'speaker': 'Ήχος',
            'speaker volume': 'Ένταση ήχου',
        },

        'sweep.suction_state': {
            'medium': 'Μεσαίο',
            'silent': 'Ήσυχο',
            'slient': 'Ήσυχο',
            'standard': 'Κανονικό',
            'turbo': 'Τούρμπο',
        },

        'sweep.water_state': {
            '低': 'Χαμηλή',
            '中': 'Μεσαία',
            '高': 'Υψηλή',
        },

        'television': {
            'input control': 'Πηγή εισόδου',
            'tv input control': 'Πηγή εισόδου τηλεόρασης',
        },

        'temperature_humidity_sensor': {
            'temperature humidity sensor temperature': 'Θερμοκρασία',
            'temperature humidity sensor relative humidity': 'Υγρασία',
            'temperature humidity sensor atmospheric pressure': 'Ατμοσφαιρική πίεση',
        },

        'vacuum': {
            'robot cleaner': 'Σκούπα δαπέδου',
            'robot cleaner status': 'Κατάσταση σκούπας',
        },

        'vacuum.mode': {
            'basic': 'Βασική',
            'silent': 'Ήσυχη',
            'standard': 'Κανονική',
            'strong': 'Δυνατή',
            'turbo': 'Τούρμπο',
            'full speed': 'Πλήρης ταχύτητα',
        },

        'washer': {
            'drying level': 'Επίπεδο στεγνώματος',
            'rinsh times': 'Αριθμός ξεβγάλματος',
            'spin speed': 'Ταχύτητα περιστροφής',
            'target water level': 'Στάθμη νερού',
        },
        'washer.mode': {
            'baby care': 'Βρεφικό πλύσιμο',
            'boiling': 'Πλύσιμο σε υψηλή θερμοκρασία',
            'color protection': 'Πλύση προστασίας χρώματος',
            'cotton': 'Βαμβάκι και λινό πλύσιμο',
            'daily wash': 'Καθημερινό πλύσιμο',
            'delicate wash': 'Απαλό πλύσιμο',
            'down coat': 'Πουπουλένιο μπουφάν',
            'drum clean': 'Καθαρισμός κάδου',
            'drum dry': 'Στέγνωμα κάδου',
            'dry air wash': 'Πλύσιμο με αέρα',
            'dry timing': 'Χρόνος στεγνώματος',
            'dry': 'Στέγνωμα',
            'gold wash': 'Πλύσιμο χρυσού',
            'heavy wash': 'Ισχυρό πλύσιμο',
            'intensive': 'Εντατικό',
            'jacket': 'Μπουφάν',
            'jeans': 'Τζιν',
            'mite removal': 'Αφαίρεση ακάρεων',
            'quick wash dry': 'Γρήγορο πλύσιμο και στέγνωμα',
            'quick wash': 'Γρήγορο πλύσιμο',
            'rinse spin': 'Λεύκανση και ξέβγαλμα',
            'rinse': 'Ενιαίο ξέβγαλμα',
            'shirt': 'Πουκάμισα',
            'silk': 'Μετάξι',
            'soak wash': 'Πλύσιμο με μούλιασμα',
            'sock': 'Κάλτσες',
            'spin': 'Στύψιμο',
            'sportswear': 'Αθλητικά ρούχα',
            'super quick': 'Σούπερ γρήγορο πλύσιμο',
            'synthetic': 'Συνθετικά',
            'towel': 'Πετσέτες',
            'underwear': 'Εσώρουχα',
            'user define': 'Προσαρμογή',
            'wash dry': 'Πλύσιμο + Στέγνωμα',
            'wool': 'Μαλλί',
        },
        'washer.drying_level': {
            'moist': 'Ελαφρώς υγρό',
            'normal': 'Κανονικό',
            'extra': 'Έξτρα',
            'none': 'Καθόλου',
        },

        'water_heater': {
            'water heater': 'Θερμοσίφωνας νερού',
        },

        'airer': {
            'airer': 'Απλώστρα',
            'dryer': 'Στεγνωτήριο',
            'drying_level': 'Επίπεδο στεγνώματος',
            'left_time': 'Υπολειπόμενος χρόνος',
            'fault': 'Σφάλμα',
        },
        'airer.dryer': {
            'Air Drying': 'Στέγνωμα',
            'Hot Air Drying': 'Στέγνωμα ζεστού αέρα',
        },
        'airer.fault': {
            'No Faults': 'Κανένα σφάλμα',
            'Obstruction': 'Απόφραξη',
            'Overweight': 'Υπέρβαρο',
            'Overheat': 'Υπερθέρμανση',
            'Motor Failure': 'Βλάβη κινητήρα',
        },
    },

    'ru': {
        'off': 'Выключенный',
        'idle': 'Бездействующий',
        'busy': 'Занятый',
        'pause': 'Пауза',
        'fault': 'Неисправный',
        'Charge-Full': 'Заряжен',

        '_globals': {
            'mode': 'Режим',
            'switch status': 'Статус переключателя',
            'battery level': 'Уровень заряда батареи',
            'target temperature': 'Целевая температура',
            'temperature': 'Температура',
            'relative humidity': 'Относительная влажность',
            'illumination': 'Освещение',
            'indicator light': 'Световой индикатор',
            'physical control locked': 'Физический контроль заблокирован',
        },

        'fan_level': {
            'auto': 'авто',
            # 'low': 'низкий',
            # 'medium': 'средний',
            # 'middle': 'середина',
            # 'high': 'высокий',
            'quiet': 'тихий',
            'turbo': 'турбо',
            'level1': '1-й уровень',
            'level2': '2-й уровень',
            'level3': '3-й уровень',
            'level4': '4-й уровень',
            'level5': '5-й уровень',
            'level6': '6-й уровень',
            'level7': '7-й уровень',
        },

        'mode': {
            'auto': 'авто',
            'basic': 'базовый',
            'low': 'низкий',
            'medium': 'средний',
            'high': 'высокий',
            'sleep': 'спящий',
            'smart': 'умный',
            'favorite': 'любимый',
        },

        'air_conditioner': {
            'air conditioner': 'кондиционер',
        },

        'air_conditioner.mode': {
            'cool': 'охлаждение',
            'dry': 'осушение',
            'fan': 'вентиляция',
            'heat': 'обогрев',
        },

        'air_fresh.mode': {
            'auto': 'авто',
            'interval': 'интервал',
            'smart': 'умный',
            'silent': 'тихий',
            'strong': 'сильный',
            'none': 'никакой',
            'sleep': 'спящий',
            'favorite': 'любимый',
        },

        'battery': {
            'battery battery level': 'уровень заряда батареи',
            'battery charging state': 'состояние зарядки аккумулятора',
        },

        'door_state': {
            'open': 'открыта',
            'close': 'закрыта',
            'close_timeout': 'тайм-аут_закрытия',
            'knock': 'стук',
            'breaking': 'нарушение',
            'stuck': 'застрявший',
        },

        'fan.mode': {
            'basic': 'базовый',
            'basic wind': 'базовая скорость вентилятора',
            'straight wind': 'ровная скорость вентилятора',
            'natural wind': 'естественная скорость вентилятора',
            'energy saving': 'сохранение энергии',
            'none': 'никакой',
            'baby': 'ребенок',
            'smart': 'умный',
            'sleep': 'спящий',
            'strong': 'сильный',
            'circular wind': 'круговая скорость вентилятора',
        },

        'ir_aircondition_control': {
            'ir aircondition control': 'управление кондиционером',
            'mode for ir': 'режим',
            'temperature for ir': 'температура',
            'turn on': 'включить',
            'turn off': 'выключить',
            'fan speed down': 'понизить скорость вентилятора-',
            'fan speed up': 'увеличить скорость вентилятора+',
            'temperature down': 'понизить температуру-',
            'temperature up': 'увеличить температуру+',
        },
        'ir_aircondition_control.ir_mode': {
            'auto': 'авто',
            'cool': 'охлаждение',
            'dry': 'осушение',
            'fan': 'вентиляция',
            'heat': 'обогрев',
        },

        'light': {
            'light': 'свет',
        },
        'light.mode': {
            'day': 'день',
            'night': 'ночь',
            'color': 'цвет',
            'warmth': 'теплый',
            'tv': 'телевизор',
            'reading': 'чтение',
            'computer': 'компьютер',
            'hospitality': 'гостеприимство',
            'entertainment': 'развлечения',
            'lighting': 'освещение',
            'night light': 'ночной свет',
        },

        'lock_method': {
            'bluetooth': 'bluetooth',
            'password': 'пароль',
            'biological': 'биологический',
            'key': 'ключ',
            'turntable': 'поворотный круг',
            'nfc': 'NFC',
            'one_time_password': 'одноразовый пароль',
            'two_step_verification': 'двухэтапная проверка',
            'coercion': 'сдерживание',
            'homekit': 'Homekit',
            'manual': 'руководство',
            'automatic': 'автоматический',
        },
        'lock_action': {
            'outside_unlock': 'внешняя разблокировка',
            'lock': 'замок',
            'anti_lock_on': 'антиблокировка включена',
            'anti_lock_off': 'антиблокировочное отключение',
            'inside_unlock': 'разблокировать внутри',
            'lock_inside': 'замок внутри',
            'child_lock_on': 'блокировка от детей включена',
            'child_lock_off': 'блокировка от детей выключена',
            'lock_outside': 'замок снаружи',
        },

        'magnet_sensor': {
            'magnet sensor': 'магнитный датчик',
        },

        'motion_sensor': {
            'motion sensor': 'датчик движения',
            'motion sensor illumination': 'подсветка датчика движения',
        },

        'physical_control_locked': {
            'physical control locked': 'Физический контроль заблокирован',
        },

        'play_control': {
            'play control': 'контроль',
            'keycodes': 'коды клавиш',
        },

        'power_consumption': {
            'power consumption': 'потребляемая мощность',
            'power consumption electric power': 'потребляемая электрическая мощность',
            'power consumption electric current': 'потребляемый электрический ток',
            'power consumption electric voltage': 'потребляемое электрическое напряжение',
        },

        'ptc_bath_heater': {
            'ptc bath heater': 'нагреватель для ванны',
        },
        'ptc_bath_heater.mode': {
            'fan': 'вентилятор',
            'heat': 'отопление',
            'ventilate': 'вентиляция',
            'dry': 'осушение',
            'defog': 'устранение запотевания',
            'quick heat': 'быстрый нагрев',
            'quick defog': 'быстрое устранение запотевания',
        },

        'speaker': {
            'speaker': 'динамик',
            'speaker volume': 'громкость динамика',
        },

        'television': {
            'input control': 'управление входом',
            'tv input control': 'управление входом телевизора',
        },

        'temperature_humidity_sensor': {
            'temperature humidity sensor temperature': 'температура датчик влажности',
            'temperature humidity sensor relative humidity': 'относительная влажность датчика температуры',
            'temperature humidity sensor atmospheric pressure': 'атмосферное давление датчика температуры влажности',
        },

        'vacuum': {
            'robot cleaner': 'робот-пылесос',
            'robot cleaner status': 'статус робота-пылесоса',
            'robot cleaner mode': 'режим уборки',
            'robot cleaner sweep type': 'тип уборки',
        },
        'alarm': {
            'alarm': 'Подать сигнал',
            'alarm volume': 'Громкость',
        },
        'vacuum.status': {
            'sleep': 'Сон',
            'idle': 'Ожидание',
            'paused': 'На паузе',
            'go charging': 'Едет на зарядку',
            'charging': 'Заряжается',
            'sweeping': 'Сухая уборка',
            'sweeping and mopping': 'Сухая и влажная уборки',
            'mopping': 'Влажная уборка',
            'upgrading': 'Обновление',
        },
        'vacuum.mode': {
            'basic': 'базовый',
            'silent': 'тихий',
            'standard': 'стандартный',
            'strong': 'сильный',
            'turbo': 'турбо',
            'full speed': 'максимальная скорость',
            'sweep': 'Сухая',
            'sweep and mop': 'Сухая и влажная',
            'mop': 'Влажная',
        },
        'vacuum.sweep_type': {
            'Global': 'Глобальная',
            'Mop': 'Влажная',
            'Edge': 'Периметр',
            'Area': 'Зона',
            'Point': 'Точка',
            'Remote': 'Удаленное управление',
            'Explore': 'Обследование',
            'Room': 'Комната',
            'Floor': 'Этаж',
        },
        'sweep': {
            'sweep door-state': 'конейнер',
            'sweep cloth-state': 'тряпка',
            'sweep hypa-life': 'ресурс фильтра',
            'sweep mop-life': 'ресурс тряпки',
            'sweep main-brush-life': 'ресурс основной щетки',
            'sweep side-brush-life': 'ресурс боковой щетки',
            'sweep repeat-state': 'двойная уборка',
            'sweep water_state': 'смачивание тряпки',
            'sweep cleaning_area': 'площадь уборки',
            'sweep cleaning_time': 'время уборки',
            'sweep pet-recognize': 'распознование животных',
            'sweep mop-route': 'тип влажной уборки',
            'sweep ai_recognize': 'распознование AI',
            'sweep dirt-recognize': 'распознование грязи',
        },
        'sweep.water_state': {
            '低': 'Низкое',
            '中': 'Среднее',
            '高': 'Высокое',
        },
        'sweep.mop_route': {
            'Y 字': 'Улучшенная',
            '弓字': 'Обычная',
        },
        'sweep.suction_state': {
            'medium': 'средний',
            '标准': 'Средняя',
            'silent': 'тихий',
            'slient': 'тихий',
            '关': 'Тихая',
            'standard': 'стандартный',
            '节能': 'Стандартная',
            'turbo': 'турбо',
            '强劲': 'Турбо',
        },
        'sweep.door_state': {
            '无': 'Извлечен',
            '尘盒': 'Для мусора',
            '水箱': 'Для воды',
            '二合一水箱': 'Совмещенный',
        },
        'sweep.cloth_state': {
            '没装': 'отсутсвует',
            '装了': 'установлена',
        },
        'clean.mode': {
            '安静': 'Тихий',
            '标准': 'Стандартный',
            '中档': 'Средний',
            '强力': 'Турбо',
        },

        'washer': {
            'drying level': 'уровень сушки',
            'rinsh times': 'время полоскания',
            'spin speed': 'скорость отжима',
            'target water level': 'целевой уровень воды',
        },
        'washer.mode': {
            'baby care': 'забота о ребенке',
            'boiling': 'кипячение',
            'color protection': 'защита цвета',
            'cotton': 'хлопок',
            'daily wash': 'ежедневная стирка',
            'delicate wash': 'деликатная стирка',
            'down coat': 'пуховик',
            'drum clean': 'очистка барабана',
            'drum dry': 'сушка в барабане',
            'dry air wash': 'сушка воздухом',
            'dry timing': 'время сушки',
            'dry': 'сушить',
            'gold wash': 'золотая стирка',
            'heavy wash': 'крупная стирка',
            'intensive': 'интенсивный',
            'jacket': 'куртка',
            'jeans': 'джинсы',
            'mite removal': 'удаление клеща',
            'quick wash dry': 'быстрая сухая стирка',
            'quick wash': 'быстрая стирка',
            'rinse spin': 'режим полоскания',
            'rinse': 'полоскать',
            'shirt': 'рубашка',
            'silk': 'шелк',
            'soak wash': 'замочить',
            'sock': 'носок',
            'spin': 'вращение',
            'sportswear': 'спортивная одежда',
            'super quick': 'супер быстро',
            'synthetic': 'синтетический',
            'towel': 'полотенце',
            'underwear': 'нижнее белье',
            'user define': 'определяемые пользователем',
            'wash dry': 'вымыть и высушить',
            'wool': 'шерсть',
        },
        'washer.drying_level': {
            'moist': 'влажный',
            'normal': 'обычный',
            'extra': 'дополнительный',
            'none': 'ничего',
        },

        'water_heater': {
            'water heater': 'водонагреватель',
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
        'viomi_vacuum': {
            '1挡': 'Level 1',
            '2挡': 'Level 2',
            '3挡': 'Level 3',
            'dust-collection': 'Dust Collection',
            'door-state': 'Dust Bin State',
            '出水量大小': 'Mop Water Volume',
            '边刷剩余寿命百分比': 'Side Brush Life',
            '边刷剩余寿命小时': 'Side Brush Hours',
            '主刷剩余寿命百分比': 'Main Brush Life',
            '主刷剩余寿命小时': 'Main Brush Hours',
            '拖布剩余寿命百分比': 'Mop Life',
            '拖布剩余寿命小时': 'Mop Hours',
            'hypa_hours': 'Dust Box Filter Hours',
            'hypa_life': 'Dust Box Filter Life',
            '清扫使用时间，单位秒': 'Cleaning time',
            '清扫总面积，单位m2': 'Cleaned area',
            '清扫开始时间，时间戳，单位秒': 'Cleaning start time, timestamp, in seconds',
            'Y字形': 'Y-shaped',
            '弓字形': 'S-shaped',
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

    'de': {
        'off': 'aus',
        'idle': 'Inaktiv',
        'busy': 'Beschäftigt',
        'pause': 'Pausiert',
        'fault': 'Fehler',

        '_globals': {
            'mode': 'Modus',
            'switch status': 'Schaltzustand',
            'battery level': 'Batterie-Ladestand',
            'target temperature': 'Zieltemperatur',
            'temperature': 'Temperatur',
            'relative humidity': 'Rel. Luftfeuchtigkeit',
            'illumination': 'Ausleuchtung',
            'indicator light': 'Kontrollleuchte',
            'physical control locked': 'Eingabe am Gerät blockiert',
        },

        'fan_level': {
            'auto': 'auto',
            # 'low': 'niedrig',
            # 'medium': 'medium',
            # 'middle': 'medium',
            # 'high': 'hoch',
            'quiet': 'ruhig',
            'turbo': 'turbo',
            'level1': 'Level 1',
            'level2': 'Level 2',
            'level3': 'Level 3',
            'level4': 'Level 4',
            'level5': 'Level 5',
            'level6': 'Level 6',
            'level7': 'Level 7',
        },

        'mode': {
            'auto': 'auto',
            'basic': 'basic',
            'low': 'niedrig',
            'medium': 'medium',
            'high': 'hoch',
            'sleep': 'schlafen',
            'smart': 'smart',
            'favorite': 'favorit',
        },

        'air_conditioner': {
            'air conditioner': 'Klimaanlage',
        },

        'air_conditioner.mode': {
            'cool': 'kühlen',
            'dry': 'trocknen',
            'fan': 'lüften',
            'heat': 'heizen',
        },

        'air_fresh.mode': {
            'auto': 'auto',
            'interval': 'intervall',
            'smart': 'smart',
            'silent': 'leise',
            'strong': 'stark',
            'none': 'keiner',
            'sleep': 'schlafen',
            'favorite': 'favorit',
        },

        'battery': {
            'battery battery level': 'Batterie-Level',
            'battery charging state': 'Ladezustand des Akkus',
        },

        'door_state': {
            'open': 'offen',
            'close': 'geschlossen',
            'close_timeout': 'nicht geschlossen timeout',
            'knock': 'klopfen',
            'breaking': 'zerstört',
            'stuck': 'tür klemmt',
        },

        'fan.mode': {
            'basic': 'basic',
            'basic wind': 'basic wind',
            'straight wind': 'starker Wind',
            'natural wind': 'natürlicher Wind',
            'energy saving': 'energie sparen',
            'none': 'nichts',
            'baby': 'baby',
            'smart': 'smart',
            'sleep': 'schlafen',
            'strong': 'stark',
            'circular wind': 'kreisförmiger Wind',
        },

        'ir_aircondition_control': {
            'ir aircondition control': 'Infrarot-Klimasteuerung',
            'mode for ir': 'infrarotmodus',
            'temperature for ir': 'infrarottemperatur',
            'turn on': 'einschalten',
            'turn off': 'ausschalten',
            'fan speed down': 'geschwindigkeit verringern',
            'fan speed up': 'geschwindigkeit erhöhen',
            'temperature down': 'kälter',
            'temperature up': 'wärmer',
        },
        'ir_aircondition_control.ir_mode': {
            'auto': 'auto',
            'cool': 'kühlen',
            'dry': 'trocken',
            'fan': 'lüften',
            'heat': 'heizen',
        },

        'light': {
            'light': '灯光',
        },
        'light.mode': {
            'day': 'Tag',
            'night': 'Nacht',
            'color': 'Farbe',
            'warmth': 'Sättigung',
            'tv': 'TV-Modus',
            'reading': 'Lesemodus',
            'computer': 'Computermodus',
            'hospitality': 'Besuchermodus',
            'entertainment': 'Unterhaltungsmodus',
            'lighting': 'Beleuchtung',
            'night light': 'Nachtlicht',
        },

        'lock_method': {
            'bluetooth': 'bluetooth',
            'password': 'passwort',
            'biological': 'biologisch',
            'key': 'schlüssel',
            'turntable': 'drehscheibe',
            'nfc': 'nfc',
            'one_time_password': 'Einmal-Passwort',
            'two_step_verification': 'Zwei-Faktor-Authentifizierung',
            'coercion': 'erzwungen',
            'homekit': 'homekit',
            'manual': 'manuell',
            'automatic': 'automatisch',
        },
        'lock_action': {
            'outside_unlock': 'von aussen entriegeln',
            'lock': 'gesperrt',
            'anti_lock_on': 'anti-lock ein',
            'anti_lock_off': 'anti-lock aus',
            'inside_unlock': 'von innen entriegeln',
            'lock_inside': 'von innen verschliessen',
            'child_lock_on': 'kindersicherung einschalten',
            'child_lock_off': 'kindersicherung ausschalten',
            'lock_outside': 'von aussen verschliessen',
        },

        'magnet_sensor': {
            'magnet sensor': 'tür- und fensterkontakt',
        },

        'motion_sensor': {
            'motion sensor': 'Bewegungserkennung',
            'motion sensor illumination': 'Lichtintensität',
        },

        'physical_control_locked': {
            'physical control locked': 'physikalische Pperre',
        },

        'play_control': {
            'play control': 'Wiedergabesteuerung',
            'keycodes': 'Tastencodes',
        },

        'power_consumption': {
            'power consumption': 'verbrauchte Energie',
            'power consumption electric power': 'Leistung',
            'power consumption electric current': 'elektrischer Strom',
            'power consumption electric voltage': 'Stromspannung',
        },

        'ptc_bath_heater': {
            'ptc bath heater': 'PTC Badheizung',
        },
        'ptc_bath_heater.mode': {
            'fan': 'Lüfter',
            'heat': 'Heizung',
            'ventilate': 'Belüften',
            'dry': 'entfeuchten',
            'defog': 'entnebeln',
            'quick heat': 'schnell heizen',
            'quick defog': 'schnelle entnebelung',
        },

        'speaker': {
            'speaker': 'Lautsprecher',
            'speaker volume': 'Lautstärke',
        },

        'sweep.suction_state': {
            'medium': 'medium',
            'silent': 'ruhig',
            'slient': 'ruhig',
            'standard': 'standard',
            'turbo': 'turbo',
        },

        'television': {
            'input control': 'eingangsquelle',
            'tv input control': 'tv-eingangsquelle',
        },

        'temperature_humidity_sensor': {
            'temperature humidity sensor temperature': 'temperatur',
            'temperature humidity sensor relative humidity': 'rel. luftfeuchtigkeit',
            'temperature humidity sensor atmospheric pressure': 'luftdruck',
        },

        'vacuum': {
            'robot cleaner': 'staubsaugerroboter',
            'robot cleaner status': 'staubsauger-status',
        },

        'vacuum.mode': {
            'basic': 'basic',
            'silent': 'ruhig',
            'standard': 'standard',
            'strong': 'stark',
            'turbo': 'turbo',
            'full speed': 'maximal',
        },

        'washer': {
            'drying level': 'Trocknungsgrad',
            'rinsh times': 'Anzahl Spülungen',
            'spin speed': 'Umdrehungsgeschwindigkeit',
            'target water level': 'Angestrebter Wasserstand',
        },
        'washer.mode': {
            'baby care': 'babywäsche',
            'boiling': 'kochwäsche',
            'color protection': 'farbschutzwäsche',
            'cotton': 'baumwolle',
            'daily wash': 'tägliche wäsche',
            'delicate wash': 'schonwäsche',
            'down coat': 'daunenjacke',
            'drum clean': 'trommelreinigung',
            'drum dry': 'trommel trocknen',
            'dry air wash': 'waschen mit trockener luft',
            'dry timing': 'trocknen zeitgesteuert',
            'dry': 'trocknen',
            'gold wash': 'gold wash',
            'heavy wash': 'schwere wäsche',
            'intensive': 'intensiv',
            'jacket': 'jacke',
            'jeans': 'jeans',
            'mite removal': 'milben entfernen',
            'quick wash dry': 'schnell waschen + trocknen',
            'quick wash': 'schnellwäsche',
            'rinse spin': 'spülmodus',
            'rinse': 'spülen',
            'shirt': 'shirt',
            'silk': 'seide',
            'soak wash': 'einweichen',
            'sock': 'socken',
            'spin': 'auswringen',
            'sportswear': 'sportkleidung',
            'super quick': 'super schnell',
            'synthetic': 'synthetik',
            'towel': 'handtücher',
            'underwear': 'unterwäsche',
            'user define': 'benutzerdefiniert',
            'wash dry': 'waschen + trocknen',
            'wool': 'wolle',
        },
        'washer.drying_level': {
            'moist': 'feucht',
            'normal': 'normal',
            'extra': 'extra',
            'none': 'keins',
        },

        'water_heater': {
            'water heater': 'Wasserkocher',
        },
    },

    'tr': {
        'off': 'Kapalı',
        'idle': 'Boşta',
        'busy': 'Meşgul',
        'pause': 'Duraklat',
        'fault': 'Hata',

        '_globals': {
            'mode': 'Mod',
            'switch status': 'Durum',
            'battery level': 'Pil Seviyesi',
            'target temperature': 'Hedef Sıcaklık',
            'temperature': 'Sıcaklık',
            'relative humidity': 'Bağıl Nem',
            'illumination': 'Aydınlatma',
            'indicator light': 'Gösterge Işığı',
            'physical control locked': 'Çocuk Kilidi',
        },

        'clock': {
            'stop alarm': 'Alarmı Kapat'
        },

        'fan_level': {
            # 'auto': 'Otomatik',
            # 'low': 'Düşük',
            # 'medium': 'Orta',
            # 'middle': 'Orta',
            # 'high': 'Yüksek',
            'quiet': 'Sessiz',
            'turbo': 'Turbo',
            'level1': '1. Seviye',
            'level2': '2. Seviye',
            'level3': '3. Seviye',
            'level4': '4. Seviye',
            'level5': '5. Seviye',
            'level6': '6. Seviye',
            'level7': '7. Seviye',
        },

        'mode': {
            'auto': 'Otomatik',
            'basic': 'Temel',
            'low': 'Düşük',
            'medium': 'Orta',
            'high': 'Yüksek',
            'sleep': 'Uyku Modu',
            'smart': 'Akıllı Mod',
            'favorite': 'Favori Mod',
        },

        'air_conditioner': {
            'air conditioner': 'Klima',
        },

        'air_conditioner.mode': {
            'cool': 'Soğutma',
            'dry': 'Nem Alma',
            'fan': 'Vantilatör',
            'heat': 'Isıtma',
        },

        'air_fresh.mode': {
            'auto': 'Otomatik',
            'interval': 'Aralıklı',
            'smart': 'Akıllı',
            'silent': 'Sessiz',
            'strong': 'Güçlü',
            'none': 'Manuel',
            'sleep': 'Uyku',
            'favorite': 'Favori',
        },

        'battery': {
            'battery battery level': 'Pil Seviyesi',
            'battery charging state': 'Şarj Durumu',
        },

        'door_state': {
            'open': 'Açık',
            'close': 'Kapalı',
            'close_timeout': 'Kapanma Zaman Aşımı',
            'knock': 'Vurma',
            'breaking': 'Zorlama',
            'stuck': 'Sıkışma',
        },

        'environment': {
            'environment air quality': 'Hava Kalitesi',
            'environment temperature': 'Sıcaklık',
            'environment relative humidity': 'Bağıl Nem',
            'environment pm2.5 density': 'PM2.5 Yoğunluğu',
            'environment co2 density': 'CO2 Yoğunluğu',
            'environment tvoc density': 'TVOC Yoğunluğu'
        },

        'fan.mode': {
            'basic': 'Temel',
            'basic wind': 'Temel Esinti',
            'straight wind': 'Doğrudan Esinti',
            'natural wind': 'Doğal Esinti',
            'energy saving': 'Enerji Tasarrufu',
            'none': 'Manuel',
            'baby': 'Bebek',
            'smart': 'Akıllı',
            'sleep': 'Uyku',
            'strong': 'Güçlü',
            'circular wind': 'Dairesel Hava',
        },

        'filter': {
            'filter left time': 'Kalan Filtre Kullanım Süresi',
            'filter used time': 'Filtre Kullanım Süresi',
            'filter life level': 'Filtre Ömrü',
        },

        'intelligent_speaker': {
            'wake up': 'Uyandırma',
            'play music': 'Müzik Çal',
            'play radio': 'Radyo Çal',
            'play text': 'Metni Oku',
            'execute text directive': 'Komutu Uygula'
        },

        'ir_aircondition_control': {
            'ir aircondition control': 'Kızılötesi Klima Kontrolü',
            'mode for ir': 'Mod',
            'temperature for ir': 'Hedef Sıcaklık',
            'turn on': 'Aç',
            'turn off': 'Kapat',
            'fan speed down': 'Fan Hızı Azalt',
            'fan speed up': 'Fan Hızı Arttır',
            'temperature down': 'Sıcaklık Azalt',
            'temperature up': 'Sıcaklık Arttır',
        },
        'ir_aircondition_control.ir_mode': {
            'auto': 'Otomatik',
            'cool': 'Soğutma',
            'dry': 'Nem Alma',
            'fan': 'Vantilatör',
            'heat': 'Isıtma',
        },

        'light': {
            'light': 'Işık',
        },
        'light.mode': {
            'day': 'Gündüz',
            'night': 'Gece',
            'color': 'Renkli',
            'warmth': 'Sıcak',
            'tv': 'TV Modu',
            'reading': 'Okuma Modu',
            'computer': 'Bilgisayar Modu',
            'hospitality': 'Misafir Modu',
            'entertainment': 'Eğlence Modu',
            'lighting': 'Aydınlatma',
            'night light': 'Gece Işığı',
        },

        'lock_method': {
            'bluetooth': 'Bluetooth',
            'password': 'Parola',
            'biological': 'Biyolojik',
            'key': 'Anahtar',
            'turntable': 'Döner Levha',
            'nfc': 'NFC',
            'one_time_password': 'Tek Seferlik Parola',
            'two_step_verification': 'İki Adımlı Doğrulama',
            'coercion': 'Zorlama',
            'homekit': 'Homekit',
            'manual': 'Manuel',
            'automatic': 'Otomatik',
        },
        'lock_action': {
            'outside_unlock': 'Dışarıdan Aç',
            'lock': 'Kilitle',
            'anti_lock_on': 'Kilit Korumasını Aç',
            'anti_lock_off': 'Kilit Korumasını Kapat',
            'inside_unlock': 'İçeriden Aç',
            'lock_inside': 'İçeriden Kilitle',
            'child_lock_on': 'Çocuk Kilidini Aç',
            'child_lock_off': 'Çocuk Kilidini Kapat',
            'lock_outside': 'Dışarıdan Kilitle',
        },

        'magnet_sensor': {
            'magnet sensor': 'Manyetik Sensör',
            'magnet sensor illumination': 'Aydınlatma',
        },

        'motion_sensor': {
            'motion sensor': 'Hareket Sensörü',
            'motion sensor illumination': 'Aydınlatma',
        },

        'occupancy_sensor': {
            'occupancy sensor occupancy status': 'Durum'
        },
        'occupancy_sensor.occupancy_status': {
            'someone exists': 'Var',
            'no one exists': 'Yok'
        },

        'physical_control_locked': {
            'physical control locked': 'Fiziksel Kontrol Kilidi',
        },

        'play_control': {
            'play control': 'Oynatma Kontrolü',
            'keycodes': 'Uzaktan Kumanda Tuşları',
        },

        'power_consumption': {
            'power consumption': 'Güç Tüketimi',
            'power consumption electric power': 'Güç',
            'power consumption electric current': 'Akım',
            'power consumption electric voltage': 'Voltaj',
            'power consumption voltage': 'Voltaj',
        },

        'ptc_bath_heater': {
            'ptc bath heater': 'Havlupan',
        },
        'ptc_bath_heater.mode': {
            'fan': 'Fan',
            'heat': 'Isıtma',
            'ventilate': 'Havalandırma',
            'dry': 'Nem Alma',
            'defog': 'Buğu Giderme',
            'quick heat': 'Hızlı Isıtma',
            'quick defog': 'Hızlı Buğu Giderme',
        },

        'speaker': {
            'speaker': 'Hoparlör',
            'speaker volume': 'Ses Seviyesi',
        },

        'sweep.suction_state': {
            'medium': 'Orta',
            'silent': 'Sessiz',
            'slient': 'Sessiz',
            'standard': 'Standart',
            'turbo': 'Turbo',
        },

        'television': {
            'input control': 'Giriş Kaynağı',
            'tv input control': 'Giriş Kaynağı',
        },

        'temperature_humidity_sensor': {
            'temperature humidity sensor temperature': 'Sıcaklık',
            'temperature humidity sensor relative humidity': 'Bağıl Nem',
            'temperature humidity sensor atmospheric pressure': 'Hava Basıncı',
        },

        'vacuum': {
            'robot cleaner': 'Robot Süpürge',
            'robot cleaner status': 'Robot Süpürge Durumu',
        },

        'vacuum.mode': {
            'basic': 'Normal',
            'silent': 'Sessiz',
            'standard': 'Normal',
            'strong': 'Güçlü',
            'turbo': 'Turbo',
            'full speed': 'Tam Hız',
        },

        'washer': {
            'drying level': 'Kurutma Seviyesi',
            'rinsh times': 'Durulama Sayısı',
            'spin speed': 'Sıkma Hızı',
            'target water level': 'Su Seviyesi',
        },
        'washer.mode': {
            'baby care': 'Bebek Bakımı',
            'boiling': 'Haşlama',
            'color protection': 'Renk Koruması',
            'cotton': 'Pamuklu',
            'daily wash': 'Günlük Yıkama',
            'delicate wash': 'Hassas Yıkama',
            'down coat': 'Tüylü yıkama',
            'drum clean': 'Tambur Temizleme',
            'drum dry': 'Tambur Kurutma',
            'dry air wash': 'Kuru Havayla Yıkama',
            'dry timing': 'Zamanlı Kurutma',
            'dry': 'Kurutma',
            'gold wash': 'Altın Yıkama',
            'heavy wash': 'Yoğun Yıkama',
            'intensive': 'Yoğun',
            'jacket': 'Ceket',
            'jeans': 'Kot',
            'mite removal': 'Akar Temizleme',
            'quick wash dry': 'Hızlı Yıkama ve Kurutma',
            'quick wash': 'Hızlı Yıkama',
            'rinse spin': 'Durulama ve Sıkma',
            'rinse': 'Durulama',
            'shirt': 'Gömlek',
            'silk': 'İpek',
            'soak wash': 'Islatarak Yıkama',
            'sock': 'Çorap',
            'spin': 'Sıkma',
            'sportswear': 'Spor Giyim',
            'super quick': 'Süper Hızlı',
            'synthetic': 'Sentetik',
            'towel': 'Havlu',
            'underwear': 'İç Çamaşırı',
            'user define': 'Kullanıcı Tanımlı',
            'wash dry': 'Yıkama ve Kurutma',
            'wool': 'Yünlü',
        },
        'washer.drying_level': {
            'moist': 'Nemli',
            'normal': 'Normal',
            'extra': 'Ekstra Kuru',
            'none': 'Kurutmasız',
        },

        'water_heater': {
            'water heater': 'Şofben',
        },
        'water_heater.mode': {
            'low': 'Düşük Sıcaklık',
            'medium': 'Orta Sıcaklık',
            'high': 'Yüksek Sıcaklık'
        },
        'airer': {
            'airer': 'Çamaşır Kurutma Askısı',
            'dryer': 'Kurutma Fonksiyonu',
            'drying_level': 'Kurutma Seviyesi',
            'left_time': 'Kalan Süre',
            'fault': 'Cihaz Hatası',
        },
        'airer.dryer': {
            'Air Drying': 'Hava Kurutma',
            'Hot Air Drying': 'Sıcak Hava Kurutma',
        },
        'airer.fault': {
            'No Faults': 'Hata Yok',
            'Obstruction': 'Engel',
            'Overweight': 'Fazla Ağırlık',
            'Overheat': 'Aşırı Isınma',
            'Motor Failure': 'Motor Hatası',
        },
        'air_purifier.mode': {
            'Auto': 'Otomatik',
            'Sleep': 'Uyku',
            'Favorite': 'Favori',
            'Manual': 'Manuel',
        },        
    },    
}
