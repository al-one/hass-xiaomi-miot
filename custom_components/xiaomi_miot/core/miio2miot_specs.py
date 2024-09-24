import logging

_LOGGER = logging.getLogger(__name__)


def set_callback_via_param_index(index=0):
    def cbk(prop, params, props, **kwargs):
        if prop in props and len(params) > index:
            props[prop] = params[index]
        _LOGGER.debug('New miio props after setting %s(%s): %s', prop, params, props)
    return cbk


MIIO_TO_MIOT_SPECS = {

    '090615.switch.switch01': '090615.switch.xswitch01',
    '090615.switch.switch02': '090615.switch.xswitch02',
    '090615.switch.switch03': '090615.switch.xswitch03',
    '090615.switch.xswitch01': {
        'without_props': True,
        'ignore_result': True,
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': [0],
                'values': ['power1', 'led'],
            },
            {'method': 'get_prop', 'params': ['switchname1'], 'values': ['name1']},
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'power1', 'setter': 'SetSwitch1', 'set_template': '{{ [value|int(0)] }}'},
            'prop.2.2': {'prop': 'name1', 'setter': 'SetSwtichname1'},
        },
    },
    '090615.switch.xswitch02': {
        'extend_model': '090615.switch.xswitch01',
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': [0, 0],
                'values': ['power1', 'power2', 'led'],
            },
            {'method': 'get_prop', 'params': ['switchname1'], 'values': ['name1']},
            {'method': 'get_prop', 'params': ['switchname2'], 'values': ['name2']},
        ],
        'miio_specs': {
            'prop.3.1': {'prop': 'power2', 'setter': 'SetSwitch2', 'set_template': '{{ [value|int(0)] }}'},
            'prop.3.2': {'prop': 'name2', 'setter': 'SetSwtichname2'},
        },
    },
    '090615.switch.xswitch03': {
        'extend_model': '090615.switch.xswitch02',
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': [0, 0, 0],
                'values': ['power1', 'power2', 'power3', 'led'],
            },
            {'method': 'get_prop', 'params': ['switchname1'], 'values': ['name1']},
            {'method': 'get_prop', 'params': ['switchname2'], 'values': ['name2']},
            {'method': 'get_prop', 'params': ['switchname3'], 'values': ['name3']},
        ],
        'miio_specs': {
            'prop.4.1': {'prop': 'power3', 'setter': 'SetSwitch3', 'set_template': '{{ [value|int(0)] }}'},
            'prop.4.2': {'prop': 'name3', 'setter': 'SetSwtichname3'},
        },
    },

    'aice.motor.kzmu3': {
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': ['houseAst'],
                'values': True,
            },
        ],
        'miio_specs': {
            'prop.2.1': {
                'prop': None,
                'setter': True,
                'set_template': '{{ {"method":'
                                '"ctrl_openDoor" if value == 1 else '
                                '"ctrl_closeDoor" if value == 2 else '
                                '"ctrl_pauseDoor"} }}',
            },
            'prop.2.2': {
                'prop': 'houseAst',
                'setter': 'set_openHouseAst',
                'set_template': '{{ ["on" if value else "off"] }}',
            },
            'prop.2.3': {'prop': None, 'template': '{{ 1 }}'},
        },
    },

    'air.fan.ca23ad9': {
        'without_props': True,
        'ignore_result': True,
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': ['on'],
                'values': ['power', 'mode', 'speed', 'lrWind', 'udWind', 'onTime', 'offTime'],
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': 'SetSwitch', 'set_template': '{{ [value|int] }}'},
            'prop.2.2': {'prop': 'speed', 'setter': 'SetLevel'},
            'prop.2.3': {'prop': 'lrWind', 'setter': 'SetH_Swing', 'set_template': '{{ [value|int] }}'},
            'prop.2.4': {'prop': 'udWind', 'setter': 'SetV_Swing', 'set_template': '{{ [value|int] }}'},
            'prop.2.5': {'prop': 'mode', 'setter': 'SetMode'},
        },
    },

    'airdog.airpurifier.x5': {
        'without_props': True,
        'ignore_result': True,
        'miio_commands': [
            {
                'method': 'get_prop',
                'values': ['power', 'mode', 'speed', 'lock', 'clean', 'pm25'],
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff', 'set_template': '{{ [value|int] }}'},
            'prop.2.2': {'prop': 'speed', 'setter': 'set_wind', 'set_template': '{{ [props.mode, value|int] }}'},
            'prop.2.3': {'prop': 'mode', 'setter': 'set_wind', 'set_template': '{{ [value|int, props.speed] }}'},
            'prop.3.1': {'prop': 'pm25'},
            'prop.4.1': {
                'prop': 'lock', 'setter': True,
                'template': '{{ value in ["lock"] }}',
                'set_template': '{{ [value|int] }}',
            },
        },
    },
    'airdog.airpurifier.x7': 'airdog.airpurifier.x5',
    'airdog.airpurifier.x7sm': {
        'extend_model': 'airdog.airpurifier.x5',
        'entity_attrs': ['hcho'],
        'miio_commands': [
            {
                'method': 'get_prop',
                'values': ['power', 'mode', 'speed', 'lock', 'clean', 'pm25', 'hcho'],
            },
        ],
    },

    'bj352.waterpuri.s100cm': {
        'without_props': True,
        'entity_attrs': ['PureWasteRatio', 'HeatingStatus', 'TotalPureWater', 'TotalWasteWater', 'error_code'],
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': [],
                'values': [
                    'RawWaterTDS', 'FinishedWaterTDS', 'WaterTemperature', 'PureWasteRatio', 'HeatingStatus',
                    'WorkStatus', 'TotalPureWater', 'TotalWasteWater', 'FilterLifeTimePercent1', 'FilterLifeTimeDays1',
                    'FilterLifeTimePercent2', 'FilterLifeTimeDays2', 'OneTimeProducedWater', 'error_code',
                ],
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'RawWaterTDS'},
            'prop.2.2': {'prop': 'FinishedWaterTDS'},
            'prop.3.1': {'prop': 'FilterLifeTimePercent1'},
            'prop.3.2': {'prop': 'FilterLifeTimeDays1'},
            'prop.4.1': {'prop': 'FilterLifeTimePercent2'},
            'prop.4.2': {'prop': 'FilterLifeTimeDays2'},
            'prop.5.1': {'prop': 'WorkStatus', 'template': '{{ 2 if value|int(0) in [1,2] else 1 }}'},
            'prop.5.2': {'prop': 'WaterTemperature'},
        },
    },

    'cgllc.airmonitor.s1': {
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_value',
                'params': ['aqi', 'pm25', 'co2', 'tvoc', 'humidity', 'temperature', 'tvoc_unit', 'temperature_unit'],
                'template': '{{ results | default({},true) }}',
            },
        ],
        'entity_attrs': ['aqi', 'tvoc_unit', 'temperature_unit'],
        'miio_specs': {
            'prop.2.1': {'prop': 'humidity'},
            'prop.2.2': {'prop': 'pm25'},
            'prop.2.3': {'prop': 'temperature'},
            'prop.2.4': {'prop': 'co2'},
            'prop.2.5': {'prop': 'tvoc'},
        },
    },

    'chuangmi.camera.ipc019': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'flip', 'setter': True, 'template': '{{ 0 if value in ["off"] else 180 }}'},
            'prop.2.3': {'prop': 'night_mode', 'setter': True},
            'prop.2.4': {'prop': 'watermark', 'setter': True, 'format': 'onoff'},
            'prop.2.5': {'prop': 'wdr', 'setter': True, 'format': 'onoff'},
            'prop.2.6': {'prop': 'full_color', 'setter': True, 'format': 'onoff'},
            'prop.2.7': {'prop': 'motion_record', 'setter': True, 'dict': {
                'stop': 1,
                'off': 2,
                'on': 3,
            }, 'default': 1},
            'action.3.1': {'setter': 'sd_format'},
            'action.3.2': {'setter': 'sd_umount'},
        },
    },
    'chuangmi.plug.hmi205': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'temperature'},
        },
    },
    'chuangmi.plug.hmi206': 'chuangmi.plug.hmi205',
    'chuangmi.plug.hmi208': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.3.1': {
                'prop': 'usb_on',
                'setter': True,
                'set_template': '{{ {"method": "set_usb_on" if value else "set_usb_off"} }}',
            },
            'prop.2.2': {'prop': 'temperature'},
        },
    },
    'chuangmi.plug.m1': {
        'extend_model': 'chuangmi.plug.hmi205',
        'miio_specs': {
            'prop.3.1': {'prop': 'wifi_led', 'setter': True, 'format': 'onoff'},
        },
    },
    'chuangmi.plug.m3': 'chuangmi.plug.m1',
    'chuangmi.plug.v1': {
        'miio_specs': {
            'prop.2.1': {
                'prop': 'on',
                'setter': True,
                'set_template': '{{ {"method": "set_on" if value else "set_off"} }}',
            },
            'prop.3.1': {
                'prop': 'usb_on',
                'setter': True,
                'set_template': '{{ {"method": "set_usb_on" if value else "set_usb_off"} }}',
            },
            'prop.2.101': {'prop': 'temperature'},
            'prop.300.301': {'prop': 'wifi_led', 'setter': True, 'format': 'onoff'},
        },
    },
    'chuangmi.plug.v3': {
        'entity_attrs': ['electric_power'],
        'miio_commands': [
            {
                'method': 'get_power',
                'params': [],
                'values': ['electric_power'],
            },
        ],
        'miio_specs': {
            # must ['on', 'usb_on', 'temperature', 'wifi_led']
            'prop.2.1': {'prop': 'on', 'setter': 'set_power', 'format': 'onoff'},
            'prop.3.1': {
                'prop': 'usb_on',
                'setter': True,
                'set_template': '{{ {"method": "set_usb_on" if value else "set_usb_off"} }}',
            },
            'prop.2.2': {'prop': 'temperature'},
            'prop.4.1': {'prop': 'wifi_led', 'setter': True, 'format': 'onoff'},
        },
    },

    'chunmi.cooker.eh1': {
        # ['status','phase','menu','t_cook','t_left','t_pre','t_kw','taste','temp','rice','favs','akw',
        # 't_start','t_finish','version','setting','code','en_warm','t_congee','t_love','boil']
        # [1       ,0      ,"0001",60      ,3600    ,0      ,0     ,1      ,15    ,0     ,"0009",1    ,
        # 0        ,0         ,13       ,0        ,0     ,15       ,120       ,60      ,0     ]
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'status', 'template': '{{ 9 if value == "finish" else value }}'},
            'prop.2.2': {'prop': 'temp'},
            'prop.2.3': {'prop': 'akw'},
            'prop.2.101': {'prop': 'menu', 'template': '{{ value|string }}'},
            'prop.2.102': {'prop': 't_left'},
            'action.2.1': {'setter': 'cancel_cooking'},
        },
    },
    'chunmi.ihcooker.chefnic': {
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': ['all'],
                'values': [
                    'func',     'menu', 'action', 'tFunc', 'version',  'custom', 'setStatus', 'play',
                    # ['pause', '0100', '0e0b00', '01000', '00050a04', '002497', '01'       , '0e00']
                ],
            },
        ],
        'entity_attrs': ['func'],
        'miio_specs': {
            'prop.2.1': {'prop': 'func', 'dict': {
                'running':    1,
                'timing':     2,
                'pause':      3,
                'pause_time': 3,
                'shutdown':   4,
                'waiting':    5,
                'finish':     5,
            }, 'default': 4},
            'prop.2.3': {'prop': 'action', 'template': '{{ (value|string)[4:6]|int(0,16) }}'},
            'prop.2.2': {
                'prop': 'tFunc',  # left-time
                'template': '{{ (value|string)[8:10]|int(0,16) * 60 + (value|string)[10:12]|int(0,16) }}',
            },
            'prop.2.4': {
                'prop': 'tFunc',  # working-time
                'template': '{{ (value|string)[4:6]|int(0,16) * 60 + (value|string)[6:8]|int(0,16) }}',
            },
            'action.2.101': {'setter': 'set_func', 'set_template': '{{ ["end030307"] }}'},
        },
    },
    'chunmi.ihcooker.v1': 'chunmi.ihcooker.chefnic',
    'chunmi.microwave.n23l01': {
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': ['all'],
                'values': [
                    'status', 'phase', 'menuid', 'tCook', 'tLeft', 'tPre', 'tPause', 'fire', 'cookPhase',
                    'pauseTimeout', 'eCode', 'version', 'customDetails', 'v13', 'orderTime', 'cookCount', 'number',
                    # [12   , 0      , "000002", 0      , 0      , 0     ,  0      , 6     , 0,
                    # "00"        , "00"   , "0009"   , "0000000000000", 0    , 0          , 0          , 0]
                ],
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'status'},
            'prop.2.2': {'prop': 'tLeft'},
            'action.2.1': {'setter': 'pause_cooking', 'set_template': '{{ ["050201"] }}'},
        },
    },

    'deerma.humidifier._base': {
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'OnOff_State', 'setter': 'Set_OnOff', 'set_template': '{{ [value|int] }}'},
            'prop.3.1': {'prop': 'Humidity_Value'},
            'prop.3.2': {'prop': 'TemperatureValue'},
            'prop.4.1': {'prop': 'TipSound_State', 'setter': 'SetTipSound_Status', 'set_template': '{{ [value|int] }}'},
            'prop.5.1': {'prop': 'Led_State', 'setter': 'SetLedState', 'set_template': '{{ [value|int] }}'},
            'prop.2.101': {'prop': 'HumiSet_Value', 'setter': 'Set_HumiValue'},
            'prop.2.102': {'prop': 'waterstatus'},
            'prop.2.103': {'prop': 'watertankstatus'},
        },
    },
    'deerma.humidifier.jsq': {
        'extend_model': 'deerma.humidifier._base',
        'miio_specs': {
            'prop.4.1': {'prop': 'Led_State', 'setter': 'SetLedState', 'set_template': '{{ [value|int] }}'},
            'prop.5.1': {'prop': 'TipSound_State', 'setter': 'SetTipSound_Status', 'set_template': '{{ [value|int] }}'},
            'prop.2.104': {'prop': 'Humidifier_Gear', 'setter': 'Set_HumidifierGears'},
        },
    },
    'deerma.humidifier.jsq1': {
        'extend_model': 'deerma.humidifier._base',
        'miio_specs': {
            'prop.2.2': {'prop': 'Humidifier_Gear', 'setter': 'Set_HumidifierGears'},
        },
    },
    'deerma.humidifier.mjjsq': {
        'extend_model': 'deerma.humidifier.jsq1',
        'miio_specs': {
            'prop.3.3': {'prop': 'HumiSet_Value', 'setter': 'Set_HumiValue'},
        },
    },

    'dmaker.fan.p5': {
        """
        https://github.com/rytilahti/python-miio/blob/31c5d740d403c6f45f1e7e0d4a8a6276684a8ecd/miio/integrations/fan/dmaker/fan.py#L28
        {'power': False, 'mode': 'normal', 'speed': 35, 'roll_enable': False, 'roll_angle': 140,
        'time_off': 0, 'light': True, 'beep_sound': False, 'child_lock': False}
        """
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': [
                    'power', 'mode', 'speed', 'roll_enable', 'roll_angle',
                    'time_off', 'light', 'beep_sound', 'child_lock',
                ],
                'values': True,
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': 's_power'},
            'prop.2.2': {'prop': 'roll_enable', 'setter': 's_roll'},
            'prop.2.3': {'prop': 'mode', 'setter': 's_mode', 'dict': {
                'nature': 0,
                'normal': 1,
            }},
            'prop.2.4': {
                'prop': 'speed',
                'setter': 's_speed',
                'template': '{{ (value/25)|round }}',
                'set_template': '{{ [(value*25)|round] }}',
            },
            'prop.2.5': {'prop': 'roll_angle', 'setter': 's_angle', 'set_template': '{{ [value|int] }}'},
            'prop.2.6': {'prop': 'speed', 'setter': 's_speed', 'set_template': '{{ [value|int] }}'},
            'prop.3.1': {'prop': 'child_lock', 'setter': 's_lock'},
            'prop.4.1': {'prop': 'light', 'setter': 's_light'},
            'prop.5.1': {'prop': 'beep_sound', 'setter': 's_sound'},
            'prop.6.1': {'prop': 'time_off', 'setter': 's_t_off', 'set_template': '{{ [value|int] }}'},
            'prop.200.201': {'prop': 'time_off', 'setter': 's_t_off', 'set_template': '{{ [value|int] }}'},
        },
    },

    'fawad.airrtc.fwd20011': {
        # ["real_fan_speed","fan_mode","Wind_Out","hot_switch_status","power_status","work_mode","fan_speed",
        # "temperature_current","temperature_set","timers_info","timers_enable","low_temp_protect_enable",
        # "screen_lock_enable","heat_type"]
        # [3               ,1         ,0         ,0                  ,0             ,3          ,0          ,
        # 12.61004447937011    ,30               ,[[0,0,0,0,0]],false          ,false                    ,
        # false               ,2]
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'power_status', 'setter': True, 'set_template': '{{ [value|int] }}'},
            'prop.2.2': {'prop': 'work_mode', 'setter': True, 'dict': {
                1: 2,
                2: 1,
                3: 3,
            }, 'default': 1},
            'prop.2.3': {'prop': 'temperature_set', 'setter': True, 'set_template': '{{ [value|int] }}'},
            'prop.3.1': {'prop': 'fan_speed', 'setter': True, 'dict': {
                0: 3,
                1: 2,
                2: 1,
                3: 0,
            }, 'default': 0},
            'prop.4.1': {'prop': 'temperature_current'},
        },
    },

    'hfjh.fishbowl.v1': {
        # ["Equipment_Status","feed_num","feed_switch","feed_time","feed_time_week","heater_switch",
        # "led_board_brightness","led_board_color","led_board_model","led_board_speed","led_board_stream",
        # "led_board_sun","pump_switch","pump_value","water_tds","water_temp","water_temp_value"]
        # [true,17,false,"00:00","",false,0,16753920,1,24,0,16771985,true,36,243,25,26]
        'miio_specs': {
            'prop.2.1': {'prop': 'Equipment_Status'},
            'prop.2.4': {'prop': 'feed_num'},
            'prop.2.3': {'prop': 'feed_switch'},
            'prop.9.1': {'prop': 'feed_time'},
            'prop.9.2': {'prop': 'feed_time_week'},
            'prop.2.6': {'prop': 'heater_switch'},
            'prop.3.1': {'prop': 'led_board_brightness'},
            'prop.3.2': {'prop': 'led_board_color'},
            'prop.3.3': {'prop': 'led_board_model'},
            'prop.3.4': {'prop': 'led_board_speed'},
            'prop.3.5': {'prop': 'led_board_stream'},
            'prop.3.6': {'prop': 'led_board_sun'},
            'prop.2.2': {'prop': 'pump_switch'},
            'prop.2.5': {'prop': 'pump_value'},
            'prop.4.1': {'prop': 'water_tds'},
            'prop.2.7': {'prop': 'water_temp'},
            'prop.2.8': {'prop': 'water_temp_value'},
        },
    },

    'isa.camera.hlc6': {
        # ["light","motion_record","flip","watermark","sdcard_status","power","night_mode","rect","max_client"]
        # ["on"   ,"on"           ,"off" ,"on"       ,0              ,"on"   ,"0"         ,"on"  ,0]
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},  # restart_device []
            'prop.2.2': {'prop': 'flip', 'template': '{{ 0 if value in ["off"] else 180 }}'},
            'prop.2.3': {'prop': 'night_mode'},
            'prop.2.4': {'prop': 'watermark', 'format': 'onoff'},
            'prop.2.5': {'prop': 'motion_record', 'dict': {
                'stop': 1,
                'off':  2,
                'on':   3,
            }, 'default': 1},
        },
    },

    'ksmb.walkingpad.v1': {
        # https://github.com/al-one/hass-xiaomi-miot/issues/261#issuecomment-1001213758
        # ['mode:2', 'time:0', 'sp:0.0', 'dist:0', 'cal:0', 'step:0']
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': ['all'],
                'values': ['mode', 'time', 'speed', 'dist', 'calorie', 'step'],
            },
            {
                'method': 'get_prop',
                'params': ['auto'],
                'values': ['auto'],
                'delay': 2,
            },
            {
                'method': 'get_prop',
                'params': ['state'],
                'values': ['state'],
                'delay': 2,
            },
        ],
        'miio_specs': {
            'prop.2.1': {
                'prop': 'mode',  # switch
                'setter': True,
                'template': '{{ (value|string).split(":")[1]|default(2)|int != 2 }}',
                'set_template': '{{ [1 if value else 2] }}',
            },
            'prop.2.2': {'prop': 'auto', 'setter': True, 'template': '{{ value|int(0) }}'},
            'prop.2.3': {'prop': 'state', 'template': '{{ 1 if value == "run" else 0 }}'},
            'prop.2.4': {
                'prop': 'speed',
                'setter': True,
                'template': '{{ (value|string).split(":")[1]|default(0)|round(1) }}',
                'set_template': '{{ [value|round(1)|string] }}',
            },
            'prop.2.5': {'prop': 'dist', 'template': '{{ (value|string).split(":")[1]|default(0)|int }}'},
            'prop.2.6': {'prop': 'time', 'template': '{{ (value|string).split(":")[1]|default(0)|int }}'},
            'prop.2.7': {'prop': 'step', 'template': '{{ (value|string).split(":")[1]|default(0)|int }}'},
            'prop.2.8': {'prop': 'calorie', 'template': '{{ (value|string).split(":")[1]|default(0)|int }}'},
        },
    },

    'lumi.acpartner.mcn02': {
        # ['power', 'mode', 'tar_temp', 'fan_level', 'ver_swing', 'load_power']
        # ['on',    'dry',   16,        'small_fan', 'off',        84.0]
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'mode', 'setter': True, 'dict': {
                'auto': 0,
                'cool': 1,
                'dry':  2,
                'heat': 3,
                'wind': 4,
            }, 'default': 0},
            'prop.2.3': {'prop': 'tar_temp', 'setter': True},
            'prop.3.1': {'prop': 'fan_level', 'setter': True, 'dict': {
                'auto_fan':   0,
                'small_fan':  1,
                'medium_fan': 2,
                'large_fan':  3,
            }, 'default': 0},
            'prop.3.2': {'prop': 'ver_swing', 'setter': True, 'format': 'onoff'},
            'prop.5.1': {'prop': 'load_power'},
        },
    },

    'lumi.acpartner.v1': {
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_model_and_state',
                'template': 'lumi_acpartner_miio_status',
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'power'},
            'prop.2.2': {'prop': 'mode'},
            'prop.2.3': {'prop': 'target_temperature'},
            'prop.3.1': {'prop': 'fan_level'},
            'prop.3.2': {'prop': 'vertical_swing'},
        },
    },
    'lumi.acpartner.v2': 'lumi.acpartner.v1',
    'lumi.acpartner.v3': 'lumi.acpartner.v1',
    'lumi.airer.acn01': {
        # ["lumi.0","light","airer_state","en_night_tip_light","level",
        # "limit_configured","limit_locked","run_time","dry_remaining_time","dry_status"]
        # [         "off"  ,"stop"       ,1                   ,0      ,
        # 1                 ,0             ,27        ,0                   ,"off"]
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_device_prop',
                'params': [
                    'lumi.0', 'light', 'airer_state', 'en_night_tip_light', 'level', 'limit_configured',
                    'limit_locked', 'run_time', 'dry_remaining_time', 'dry_status',
                ],
                'values': [
                    'light', 'airer_state', 'en_night_tip_light', 'level', 'limit_configured',
                    'limit_locked', 'run_time', 'dry_remaining_time', 'dry_status',
                ],
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'motor', 'setter': 'toggle_device', 'dict': {
                'up':   0,
                'down': 1,
                'stop': 2,
            }},
            'prop.2.2': {'prop': 'level', 'setter': True},
            'prop.2.3': {'prop': 'airer_state', 'dict': {
                'down': 1,
                'up':   2,
                'stop': 3,
            }, 'default': 3},
            'prop.2.4': {
                'prop': 'dry_status',
                'template': '{{ value != "off" }}',
                'setter': 'control_device',
                'set_template': '{{ '
                                '["start_hotdry",90] if value else '
                                '["stop_hotdry",0] if "hotdry" in props.dry_status else '
                                '["stop_winddry",0] }}',
            },
            'prop.2.101': {
                'prop': 'dry_status',
                'dict': {
                    'off':     0,
                    'hotdry':  1,
                    'winddry': 2,
                },
                'setter': 'control_device',
                'set_template': '{{ '
                                '["start_hotdry",90] if value == 1 else '
                                '["start_winddry",90] if value == 2 else '
                                '["stop_hotdry",0] if "hotdry" in props.dry_status else '
                                '["stop_winddry",0] }}',
            },
            'prop.2.5': {'prop': 'dry_remaining_time'},
            'prop.3.1': {'prop': 'light', 'setter': 'toggle_light', 'format': 'onoff'},
        },
    },

    'midea.aircondition.v1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'mode', 'setter': True, 'dict': {
                'auto': 0,
                'cold': 1,
                'dehumidifier': 2,
                'hot': 3,
                'wind': 4,
            }},
            'prop.2.3': {'prop': 'temp', 'setter': True},
            'prop.2.101': {'prop': 'temp_indoor'},
            'prop.3.1': {
                'prop': 'wind_speed',
                'setter': True,
                'dict': {
                    0: 0,
                    20: 1,
                    60: 2,
                    100: 3,
                },
                'template': '{{ '
                            '1 if value <= 40 else '
                            '2 if value <= 60 else '
                            '3 if value >= 80 else '
                            '0 }}',
            },
            'prop.3.2': {'prop': 'wind_up_down', 'setter': True, 'format': 'onoff'},
        },
    },
    'midea.aircondition.xa1': {
        'miio_specs': {
            'prop.2.2': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.1': {'prop': 'mode', 'setter': True, 'dict': {
                'auto': 1,
                'hot': 2,
                'cold': 3,
                'dehumidifier': 4,
                'wind': 5,
            }},
            'prop.2.3': {'prop': 'temp', 'setter': True},
            'prop.2.101': {'prop': 'temp_indoor'},
            'prop.3.1': {'prop': 'wind_up_down', 'setter': True, 'format': 'onoff'},
            'prop.3.2': {
                'prop': 'wind_speed',
                'setter': True,
                'dict': {
                    20: 1,
                    40: 2,
                    60: 3,
                    80: 4,
                    100: 5,
                },
            },
            'prop.4.1': {'prop': 'screen_display', 'setter': True, 'format': 'onoff'},
        },
    },
    'midea.aircondition.xa2': 'midea.aircondition.xa1',

    'mijia.camera.v3': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'flip', 'template': '{{ 0 if value in ["off"] else 180 }}'},
            'prop.2.3': {'prop': 'night_mode'},
            'prop.2.5': {'prop': 'band_nearby'},
            'prop.2.7': {'prop': 'watermark', 'format': 'onoff'},
            'prop.2.8': {'prop': 'motion_record', 'dict': {
                'off': 1,
                'on':  2,
            }, 'default': 1},
        },
    },

    'minij.washer.v5': {
        # ["state","process","cycle","time_remain","child_lock","lock","dry_set","dirty_type"]
        # ["off","option:load,prewash,wash,rinse,spin;processing:invalid","dailywash","0069","off","unlock","none","none"]
        'miio_specs': {
            'prop.2.1': {
                'prop': 'state',
                'format': 'onoff',
                'setter': 'set_power',
                'template': '{{ value != "off" }}',
            },
            'prop.2.2': {'prop': 'state', 'setter': True,  'dict': {
                'off':     1,
                'standby': 2,
                'run':     3,
                'delay':   4,
                'pause':   5,
                'fault':   6,
                'eoc':     7,
            }},
            'prop.2.3': {'prop': 'cycle', 'setter': True, 'dict': {
                'dailywash':    1,  # mode
                'quick':        2,
                'delicate':     3,
                'down':         4,
                'heavy':        5,
                'userdefine':   6,
                'rinse':        7,
                'spin':         8,
                'cotton':       9,
                'synthetic':    10,
                'shirt':        11,
                'boiling':      12,
                'wool':         13,
                'drumclean':    14,
                'babycare':     15,
                'intensive':    16,
                'jacket':       17,
                'washdry':      18,
                'underwear':    19,
                'dry':          20,
                'dryairwash':   21,
                'washdryquick': 22,
            }, 'default': 1},
            'prop.2.4': {'prop': 'time_remain', 'setter': True},
            'prop.2.5': {
                'prop': 'speed',
                'setter': True,
                'template': '{{ value | regex_replace("rpm","") | int }}',
                'set_template': '{{ [value ~ "rpm"] }}',
            },
            'prop.2.6': {
                'prop': 'temp',
                'setter': True,
                'template': '{{ value | int(0) }}',
                'set_template': '{{ [value | string if value else "cool"] }}',
            },
            'prop.2.7': {'prop': 'water_level', 'setter': True, 'dict': {
                'high':   1,
                'middle': 2,
                'low':    3,
            }, 'default': 3},
            'prop.2.8': {
                'prop': 'rinse_time',
                'setter': True,
                'template': '{{ value | int(0) }}',
                'set_template': '{{ [value | string] }}',
            },
            'prop.2.9': {'prop': 'dry_set', 'setter': True, 'dict': {
                'moist':  1,
                'normal': 2,
                'extra':  3,
                'none':   4,
            }, 'default': 4},
            'prop.3.1': {'prop': 'child_lock', 'setter': True},
            'prop.4.1': {'prop': 'volume', 'setter': True},
        },
    },
    'minij.washer.v8': {
        'extend_model': 'minij.washer.v5',
        'chunk_properties': 1,
    },
    'minij.washer.v14': {
        'extend_model': 'minij.washer.v5',
        'chunk_properties': 1,
    },

    'mmgg.feeder.petfeeder': {
        'without_props': True,
        'miio_commands': [
            {
                'method': 'getprops',
                'values': [
                    'food_status', 'feed_status', 'door_status', 'feed_today', 'clean_days', 'outlet_status',
                    'dryer_days', 'weight_level', 'wifi_led', 'key_lock', 'country_code',
                ],
            },
        ],
        'miio_specs': {
            'prop.2.101': {'prop': 'food_status'},
            'prop.2.102': {'prop': 'feed_status', 'setter': 'stopfeed', 'set_template': '{{ [value|int] }}'},
            'prop.2.103': {'prop': 'feed_today'},
            'prop.2.104': {'prop': 'dryer_days'},
            'prop.2.105': {'prop': 'clean_days'},
            'prop.2.106': {'prop': 'door_status'},
            'prop.2.107': {'prop': 'outlet_status'},
            'action.2.1': {'setter': 'outfood'},
            'action.2.101': {'setter': 'resetdryer'},
            'prop.200.201': {'prop': 'wifi_led', 'setter': 'wifiledon', 'set_template': '{{ [value|int] }}'},
            'prop.300.301': {
                'prop': 'key_lock',
                'setter': 'keylock',
                'template': '{{ not value }}',
                'set_template': '{{ [0 if value else 1] }}',
            },
        }
    },
    'mrbond.airer.m1pro': {
        'chunk_properties': 1,
        'entity_attrs': ['airer_location'],
        'miio_commands': [
            {'method': 'get_prop', 'values': True, 'ignore_error': True, 'params': ['drytime']},
            {'method': 'get_prop', 'values': True, 'ignore_error': True, 'params': ['airer_location']},
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'motor', 'setter': True},
            'prop.2.2': {
                'prop': 'dry',
                'setter': True,
                'template': '{{ value|int > 0 }}',
                'set_template': '{{ [value|int] }}',
            },
            'prop.2.3': {'prop': 'dry', 'setter': 'set_dry'},
            'prop.2.4': {'prop': 'dry', 'template': '{{ props.drytime|default(0)|int }}'},
            'prop.3.1': {'prop': 'led', 'setter': True, 'set_template': '{{ [value|int] }}'},
        }
    },
    'mrbond.airer.m1s': 'mrbond.airer.m1pro',

    'nwt.derh.wdh318efw1': {
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'on_off', 'setter': 'set_power', 'format': 'onoff'},
            'prop.2.2': {
                'prop': 'mode',
                'setter': True,
                'dict': {
                    'auto': 0,
                    'on': 1,
                    'dry_cloth': 2,
                },
                'set_template': '{{ '
                                '["on"] if value == 1 else '
                                '["dry_cloth"] if value == 2 else '
                                '{"method": "set_auto","params": [props.auto]} }}',
            },
            'prop.2.3': {'prop': 'fan_st', 'setter': 'set_fan_level'},
            'prop.2.101': {'prop': 'auto', 'setter': True},
            'prop.2.102': {'prop': 'tank_full', 'format': 'onoff'},
            'prop.3.1': {'prop': 'humidity'},
            'prop.4.1': {'prop': 'buzzer', 'setter': True, 'format': 'onoff'},
            'prop.5.1': {'prop': 'led', 'setter': True, 'format': 'onoff'},
            'prop.6.1': {'prop': 'child_lock', 'setter': True, 'format': 'onoff'},
        },
    },

    'opple.light.bydceiling': {
        'without_props': True,
        'miio_commands': [
            {
                'method': 'SyncBaseInfo',
                'params': [],
                'values': ['state', 'ColorTemperature', 'Brightness', 'Scenes'],
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'state', 'setter': 'SetState'},
            'prop.2.2': {'prop': 'Scenes', 'setter': 'SetScenes', 'dict': {
                'NIGHT': 1,
                'TV':    2,
                'GUEST': 3,
                'PLAY':  4,
            }, 'default': 3},
            'prop.2.3': {'prop': 'Brightness', 'setter': 'SetBrightness'},
            'prop.2.4': {'prop': 'ColorTemperature', 'setter': 'SetColorTemperature'},
        },
    },
    'opple.light.fanlight': {
        # ["LightPower","Brightness","ColorTemperature","Scenes","FanPower","Speed",
        # "SmartBtn","SmartVal","Gear","Temperature","Circular","CountdownTime","CountdownAct"]
        # [true       ,100          ,3000              ,"GUEST" ,false     ,42     ,
        # false     ,26        ,"NONE",15           ,false     ,0              ,false]
        'miio_specs': {
            'prop.2.1': {'prop': 'LightPower', 'setter': 'SetLightPower'},
            'prop.2.2': {'prop': 'Scenes', 'setter': 'SetScenes', 'dict': {
                'GUEST': 1,
                'TV':    2,
                'PLAY':  3,
                'NIGHT': 4,
            }, 'default': 1},
            'prop.2.3': {'prop': 'Brightness', 'setter': 'SetBrightness'},
            'prop.2.4': {'prop': 'ColorTemperature', 'setter': 'SetColorTemperature'},
            'prop.3.1': {'prop': 'FanPower', 'setter': 'SetFanPower'},
            'prop.3.2': {'prop': 'Speed', 'setter': 'SetSpeed'},
            'prop.3.3': {'prop': 'Gear', 'setter': 'SetGear', 'dict': {
                'NONE': 1,
                'LOW':  2,
                'MID':  3,
                'HIGH': 4,
            }, 'default': 1},
        },
    },

    'ows.towel_w.mj1x0': {
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_props',
                'values': [
                    'power', 'mode', 'tempdry', 'tempheat', 'drytime',
                    'temprog', 'tempsurf', 'tempind', 'percent', 'errflag',
                ],
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'set_template': '{{ [value|int(0)] }}'},
            'prop.2.2': {'prop': 'mode', 'setter': True},
            'prop.2.3': {
                'prop': 'tempheat',
                'setter': True,
                'template': '{{ [props.tempdry,value,value,props.temprog][props.mode]|default(value)/2 }}',
                'set_template': '{{ {"method": '
                                '"set_tempdry" if props.mode == 0 else '
                                '"set_tempheat" if props.mode == 1 else '
                                '"set_temprog",'
                                '"params": [value * 2],'
                                '} }}',
            },
            'prop.2.4': {'prop': 'tempsurf', 'template': '{{ value|int(0)/2 }}'},
            'prop.2.101': {'prop': 'drytime', 'setter': True},
        },
    },

    'philips.light.bceiling1': 'philips.light.downlight',
    'philips.light.bulb': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {'prop': 'snm', 'setter': 'apply_fixed_scene', 'dict': {
                1: 1,
                2: 3,
                3: 4,
                4: 2,
            }, 'default': 1},
            'prop.2.4': {
                'prop': 'cct',
                'setter': True,
                'template': '{{ ((max - min) * value / 100 + min) | round }}',
                'set_template': '{% set num = ((value - min) / (max - min) * 100) | round %}'
                                '{{ [num if num > 0 else 1] }}',
            },
        },
    },
    'philips.light.cbulb': {
        'extend_model': 'philips.light.bulb',
        'miio_specs': {
            'prop.2.3': {'prop': 'cid', 'setter': True},
            'prop.2.5': {'prop': 'snm', 'setter': 'apply_fixed_scene'},
            'prop.2.6': {'prop': 'cid', 'template': '{{ 2 if val == 360 else 1 }}'},
        },
    },
    'philips.light.downlight': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {
                'prop': 'cct',
                'setter': True,
                'template': '{{ ((max - min) * value / 100 + min) | round }}',
                'set_template': '{% set num = ((value - min) / (max - min) * 100) | round %}'
                                '{{ [num if num > 0 else 1] }}',
            },
            'prop.2.4': {'prop': 'snm', 'setter': 'apply_fixed_scene'},
        },
    },
    'philips.light.moonlight': {
        'extend_model': 'philips.light.bulb',
        'miio_specs': {
            'prop.2.1': {'prop': 'pow', 'setter': 'set_power', 'format': 'onoff'},
            'prop.2.2': {'prop': 'bri', 'setter': 'set_bright'},
            'prop.2.3': {'prop': 'rgb', 'setter': True, 'format': 'rgb'},
            'prop.2.5': {
                'prop': 'snm',
                'setter': True,
                'template': '{{ 1 if value == 6 else 0 }}',
                'set_template': '{{ {"method": "go_night"} '
                                'if value == 1 else '
                                '{"method": "apply_fixed_scene","params": [5]} }}',
            },
            'prop.2.6': {'prop': 'sta', 'template': '{{ 2 if value == 0 else 1 }}'},
        },
    },
    'philips.light.sread1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
        },
    },
    'philips.light.sread2': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {'prop': 'scene_num', 'setter': True, 'dict': {
                'None': 0,
                'Child Reading': 1,
                'Adult Reading': 2,
                'Computer': 3,
            }},
            'prop.3.2': {'prop': 'ambstatus', 'setter': True, 'format': 'onoff'},
            'prop.3.3': {'prop': 'ambvalue', 'setter': True},
            'prop.3.4': {'prop': 'notifystatus', 'setter': True, 'format': 'onoff'},
            'prop.3.5': {'prop': 'eyecare', 'setter': True, 'format': 'onoff'},
        },
    },

    'roborock.vacuum._base': {
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_status',
                'template': '{{ results.0 | default({}) }}',
            },
            {
                'method': 'get_consumable',
                'template': '{{ results.0 | default({}) }}',
            },
            {
                'method': 'get_custom_mode',
                'values': ['fan_mode'],
            },
        ],
    },
    'roborock.vacuum.m1s': {
        'extend_model': 'roborock.vacuum._base',
        'miio_specs': {
            'prop.2.1': {
                'prop': 'fan_mode',
                'setter': 'set_custom_mode',
                'template': '{{ value|int - 100 }}',
                'set_template': '{{ [value|int + 100] }}',
            },
            'prop.2.3': {'prop': 'state', 'dict': {
                1: 5,  # Starting
                4: 7,  # Remote control active
            }},
            'prop.4.1': {'prop': 'battery'},
            'action.2.1': {'setter': 'app_start'},
            'action.2.2': {'setter': 'app_stop'},
            'action.4.1': {'setter': 'app_charge'},
        },
    },
    'roborock.vacuum.a01': 'roborock.vacuum.t6',
    'roborock.vacuum.a08': {
        'extend_model': 'roborock.vacuum.t6',
        'miio_specs': {
            'prop.2.1': {'prop': 'state'},
            'prop.2.2': {'prop': 'fan_mode', 'setter': 'set_custom_mode'},
        },
    },
    'roborock.vacuum.a09': 'roborock.vacuum.t6',
    'roborock.vacuum.a10': 'roborock.vacuum.t6',
    'roborock.vacuum.a11': 'roborock.vacuum.t6',
    'roborock.vacuum.a14': {
        'extend_model': 'roborock.vacuum.t6',
        'miio_commands': [
            {
                'method': 'get_status',
                'template': '{{ results.0 | default({}) }}',
            },
            {
                'method': 'get_consumable',
                'template': '{{ results.0 | default({}) }}',
            },
            {
                'method': 'get_custom_mode',
                'values': ['fan_mode'],
            },
            {
                'method': 'get_water_box_custom_mode',
                'values': ['water_level'],
            },
            {
                'method': 'get_mop_mode',
                'values': ['mop_mode'],
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'state'},
            'prop.2.2': {'prop': 'error_code'},
            'prop.2.4': {'prop': 'fan_mode', 'setter': 'set_custom_mode'},
            'prop.2.102': {'prop': 'water_level', 'setter': 'set_water_box_custom_mode'},
            'prop.2.103': {'prop': 'mop_mode', 'setter': 'set_mop_mode'},
            # 'action.2.4': {'setter': 'app_start'},  # start-mop
            # 'action.2.5': {'setter': 'app_start'},  # start-sweep-mop
            'action.2.6': {
                'setter': 'app_segment_clean',
                'set_template': '{% set ids = params[0]|default("")|string %}'
                                '{% set arr = ids|from_json if ids[0:1] == "[" else ids.split(",") %}'
                                '{{ arr }}',
            },
            'prop.9.2': {'prop': 'main_brush_work_time', 'template': '{{ 100-(value/(36*300))|round }}'},
            'prop.10.2': {'prop': 'side_brush_work_time', 'template': '{{ 100-(value/(36*200))|round }}'},
            'prop.11.1': {'prop': 'filter_work_time', 'template': '{{ 100-(value/(36*150))|round }}'},
        },
    },
    'roborock.vacuum.a15': 'roborock.vacuum.a14',
    'roborock.vacuum.a19': 'roborock.vacuum.a14',
    'roborock.vacuum.a23': 'roborock.vacuum.a14',
    'roborock.vacuum.a26': 'roborock.vacuum.a14',
    'roborock.vacuum.a27': 'roborock.vacuum.a14',
    'roborock.vacuum.a29': 'roborock.vacuum.a14',
    'roborock.vacuum.a30': 'roborock.vacuum.a14',
    'roborock.vacuum.a34': 'roborock.vacuum.a14',
    'roborock.vacuum.a37': 'roborock.vacuum.a14',
    'roborock.vacuum.a38': 'roborock.vacuum.a14',
    'roborock.vacuum.a40': 'roborock.vacuum.a14',
    'roborock.vacuum.a46': 'roborock.vacuum.a14',
    'roborock.vacuum.a50': 'roborock.vacuum.a14',
    'roborock.vacuum.a51': 'roborock.vacuum.a14',
    'roborock.vacuum.a52': 'roborock.vacuum.a14',
    'roborock.vacuum.a62': 'roborock.vacuum.a14',
    'roborock.vacuum.a64': 'roborock.vacuum.a14',
    'roborock.vacuum.a65': 'roborock.vacuum.a14',
    'roborock.vacuum.a66': 'roborock.vacuum.a14',
    'roborock.vacuum.a69': 'roborock.vacuum.a14',
    'roborock.vacuum.a70': 'roborock.vacuum.a14',
    'roborock.vacuum.a74': 'roborock.vacuum.a14',
    'roborock.vacuum.a75': 'roborock.vacuum.a14',
    'roborock.vacuum.a76': 'roborock.vacuum.a14',
    'roborock.vacuum.c1': 'rockrobo.vacuum.v1',
    'roborock.vacuum.e2': 'rockrobo.vacuum.v1',
    'roborock.vacuum.p5': 'roborock.vacuum.a08',
    'roborock.vacuum.s4': 'roborock.vacuum.t4',
    'roborock.vacuum.s5': 'rockrobo.vacuum.v1',
    'roborock.vacuum.s5e': 'rockrobo.vacuum.a08',
    'roborock.vacuum.s6': 'roborock.vacuum.t6',
    'roborock.vacuum.t4': {
        'extend_model': 'roborock.vacuum.t6',
        'miio_specs': {
            'prop.2.2': {
                'prop': 'fan_mode',
                'setter': 'set_custom_mode',
                'template': '{{ value|int - 101 }}',
                'set_template': '{{ [value|int + 101] }}',
            },
        },
    },
    'roborock.vacuum.t6': {
        'extend_model': 'roborock.vacuum._base',
        'miio_specs': {
            'prop.2.1': {'prop': 'state', 'dict': {
                1: 2,  # Starting
                2: 7,  # Charger disconnected
                3: 1,  # Idle
                4: 6,  # Remote control active
                5: 2,  # Cleaning
                6: 5,  # Returning home
                7: 6,  # Manual mode
                8: 3,  # Charging
                9: 7,  # Charging problem
                10: 4,  # Paused
                11: 2,  # Spot cleaning
                12: 7,  # Error
                13: 7,  # Shutting down
                15: 1,  # Docking
                16: 6,  # Going to target
                17: 2,  # Zoned cleaning
                18: 2,  # Segment cleaning
            }, 'default': 1},
            'prop.2.2': {
                'prop': 'fan_mode',
                'setter': 'set_custom_mode',
                'template': '{{ value|int - 100 }}',
                'set_template': '{{ [value|int + 100] }}',
            },
            'prop.3.1': {'prop': 'battery'},
            'action.2.1': {'setter': 'app_start'},
            'action.2.2': {'setter': 'app_stop'},
            'action.3.1': {'setter': 'app_charge'},
        },
    },
    'rockrobo.vacuum.v1': {
        'extend_model': 'roborock.vacuum.t6',
        'miio_specs': {
            'prop.2.2': {'prop': 'fan_power', 'setter': 'set_custom_mode'},
            'prop.3.2': {'prop': 'charging', 'template': '{{ 1 if props.state in [8] else 2 }}'},
        },
    },

    'shuii.humidifier.jsq002': {
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_props',
                'values': [
                    'power', 'gear', 'humidity', 'ledLevel', 'temperature', 'waterLevel',
                    'heat', 'beaPower', 'childLock', 'targetTemp', 'targetHumidity',
                ],
            },
        ],
        'miio_specs': {
            'prop.2.1': {
                'prop': 'power',
                'setter': 'on_off',
                'template': '{{ value == 1 and props.waterLevel not in [0,6] }}',
                'set_template': '{{ [value|int] }}',
            },
            'prop.2.2': {'prop': 'gear', 'setter': True},
            'prop.2.3': {'prop': 'heat', 'setter': 'warm_on', 'set_template': '{{ [value|int] }}'},
            'prop.2.4': {'prop': 'targetHumidity', 'setter': 'set_humidity'},
            'prop.2.5': {'prop': 'waterLevel'},
            'prop.2.6': {'prop': 'targetTemp', 'setter': 'set_temp'},
            'prop.3.1': {'prop': 'humidity'},
            'prop.3.2': {'prop': 'temperature'},
            'prop.4.1': {'prop': 'ledLevel', 'setter': 'set_led'},
            'prop.5.1': {'prop': 'beaPower', 'setter': 'buzzer_on', 'set_template': '{{ [value|int] }}'},
            'prop.6.1': {'prop': 'childLock', 'setter': 'set_lock', 'set_template': '{{ [value|int] }}'},
        },
    },

    'skyrc.pet_waterer.fre1': {
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_prop',
                'values': ['bright_value', 'filter', 'on', 'pump', 'var5', 'water_type', 'power'],
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'set_template': '{{ [1 if value else 0] }}'},
            'prop.3.1': {'prop': 'bright_value', 'setter': True, 'set_template': '{{ [1 if value else 0] }}'},
            'prop.4.1': {'prop': 'filter'},  # set_filter_alarm [0]
        },
    },

    'tinymu.toiletlid.v1': {
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': ['work_state', 'filter_use_time', 'filter_use_flux'],
                'values': ['work_state', 'filter_use_time', 'filter_use_flux'],
            },
            {
                'method': 'get_aled_v_of_uid',
                'params': [''],
                'values': ['ambient_light'],
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'filter_use_time'},
            'prop.2.2': {'prop': 'filter_use_flux'},
            'prop.3.1': {'prop': None, 'setter': 'seat_heat', 'format': 'onoff'},
            'prop.3.2': {'prop': None, 'setter': 'deodorant', 'format': 'onoff'},
            'prop.3.101': {'prop': 'work_state', 'template': '{{ (value|int(1) - 1) // 16 }}'},
            'prop.3.102': {'prop': 'work_state', 'template': '{{ value|int(0) not in [1,97] }}'},
            'prop.3.103': {
                'prop': 'ambient_light',
                'setter': 'set_aled_v_of_uid',
                'template': '{{ value | int }}',
                'set_template': '{{ ["", value | string] }}',
            },
        },
    },

    'viomi.fridge.p1': {
        # ["Mode","RCSetTemp","FCSetTemp","RCSet","Error","IndoorTemp","SmartCool","SmartFreeze"]
        # ["none",8          ,-15        ,"on"   ,0      ,10          ,"off"      ,"off"]
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'Mode', 'setter': 'setMode', 'dict': {
                'holiday': 1,
                'none':    2,
            }, 'default': 2},
            'prop.3.1': {'prop': 'RCSetTemp'},
            'prop.3.2': {'prop': 'RCSetTemp', 'setter': 'setRCSetTemp'},
            'prop.4.1': {'prop': 'FCSetTemp'},
            'prop.4.2': {'prop': 'FCSetTemp', 'setter': 'setFCSetTemp'},
            'prop.3.3': {'prop': 'RCSet', 'setter': 'setRCSet', 'format': 'onoff'},
        },
    },
    'viomi.fridge.m1': {
        # ["Mode","RCSetTemp","FCSetTemp","RCSet","Error","IndoorTemp","SmartCool","SmartFreeze"]
        # ["none",8          ,-15        ,"on"   ,0      ,30          ,"off"      ,"off"]
        # 'chunk_properties': 8,
        'chunk_properties': 1,
        'miio_props': ['ScreenOn', 'Error', 'SmartCool', 'SmartFreeze'],
        'entity_attrs': ['ScreenOn', 'Error', 'SmartCool', 'SmartFreeze'],
        'miio_specs': {
            'prop.2.1': {'prop': 'Mode', 'setter': 'setMode', 'dict': {
                'smart': 1,
                'holiday': 2,
                'energy': 3,
                'none': 4,
            }, 'default': 1},
            'prop.3.1': {'prop': 'RCSetTemp', 'setter': 'setRCSetTemp'},
            'prop.3.2': {'prop': 'RCSet', 'setter': 'setRCSet', 'format': 'onoff'},
            'prop.3.3': {'prop': 'RCSetTemp'},
            'prop.4.1': {'prop': 'FCSetTemp', 'setter': 'setFCSetTemp'},
            'prop.4.2': {'prop': 'FCSetTemp'},
            'prop.2.2': {'prop': 'IndoorTemp'},
        },
    },
    'viomi.juicer.v1': {
        # ["work_status","run_status","mode","cooked_time","curr_tempe","cook_start","rev","stand_top_num","mode_sort"        ,"cook_status","warm_time","cook_time","left_time","voice"]
        # [0,           ,768         ,7     ,0            ,-300        ,1699143554  ,0    ,0              ,'7-8-9-4-3-1-5-2-6',1            ,6514       ,1668       ,0          ,0      ]
        'miio_props': ['work_status', 'run_status', 'mode', 'cooked_time', 'cook_start', 'rev', 'stand_top_num', 'mode_sort', 'warm_time', 'cook_time',  'voice'],
        'entity_attrs': ['work_status', 'run_status', 'mode', 'cooked_time', 'cook_start', 'rev', 'stand_top_num', 'mode_sort', 'warm_time', 'cook_time',  'voice'],
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'cook_status'},
            'prop.2.2': {'prop': 'left_time'},
            'prop.2.3': {'prop': 'curr_tempe'},
        },
    },
    'yunmi.plmachine.mg2': {
        'miio_props': ['fault','run_status', 'water_remain_time', 'custom_tempe1', 'min_set_tempe', 'drink_remind_time', 'water_state', 'water_fetch'],
        'entity_attrs': ['fault','run_status', 'water_remain_time', 'custom_tempe1', 'min_set_tempe', 'drink_remind_time', 'water_state', 'water_fetch'],
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.4': {'prop': 'work_mode'},
            'prop.2.5': {'prop': 'curr_tempe'},
            'prop.2.6': {
                'prop': 'setup_tempe', 
                'setter': 'set_tempe_setup',
                'set_template': '{{ [1, value|int(52)] }}',
                },
            'prop.2.7': {'prop': 'uv_state'},
            'prop.3.1': {'prop': 'tds'},
        },
    },
    'scishare.coffee.s1102': {
        # set_methods:
        # "Espresso_Coffee_Set [coffee.coffee, coffee.temp],
        # "Americano_Coffee_Set [coffee.water, coffee.temp, coffee.coffee, 85]"
        # "Hot_Wate_Set[coffee.water, coffee.temp]","Boiler_Preheating_Set [temp]"
        #
        # query_on_off_methods
        # ["Query_Machine_Status []","Machine_ON []","Machine_OFF []"]
        # ["['ok',5]",              ,"ok"           ,"ok"]
        #
        # make_coffee_methods
        # 0 : Espresso_Coffee : "Espresso_Coffee [coffee.coffee, coffee.temp]"
        # 1 : Americano_Coffee : "Americano_Coffee [coffee.water, coffee.temp, coffee.coffee, 85]"
        # 2 : Hot_Wate: "Hot_Wate [coffee.water, coffee.temp]"
        #
        # control_methods
        # ["Cancel_Work_Alarm []","All_Recovery []","Machine_Descaling []","Stop_Boiler_Preheat []","Continue_Operation []"]

        'chunk_properties': 1,
        'miio_commands': [
            {
                'method': 'Query_Machine_Status',
                'params': [],
                'values': ['online', 'state'],
            },
        ],
        'miio_specs': {
            'prop.2.1': { 'prop': 'state', },
            'prop.2.2': {
                'prop': 'state',
                'template': '{{ value != 1 }}',
                'setter': True,
                'set_template': '{{ {"method": "Machine_ON" if value else "Machine_OFF"} }}',
            },
        },
    },
    'viomi.oven.so1': {
        # methods:
        # ['get_prop', 'setDish', 'deleteDish', 'getDishs', 'setStartDish', 'setStartMode', 'setPrepareDish', 'setPrepareMode', 'setPause', 'canclePrepare', 'setEnd', 'setBootUp', 'setTurnOff'];
        'miio_props': ['hwInfo', 'swInfo', 'error', 'dishId', 'dishName',  'tempSetZ', 'timeSetZ', 'tempSetK', 'timeSetK', 'waterTank', 'prepareTime', 'doorIsOpen'],
        'entity_attrs': ['hwInfo', 'swInfo', 'error', 'dishId', 'dishName',  'tempSetZ', 'timeSetZ', 'tempSetK', 'timeSetK', 'waterTank', 'prepareTime', 'doorIsOpen'],
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'status', 'dict': {
                0: 1,
                1: 2,
                2: 3,
                3: 4,
                4: 5,
                },
            },
            'prop.2.2': {
                'setter': True,
                'set_template': '{{ {'
                                '"method":"setBootUp" if value else "setTurnOff",'
                                '"params": "[]",'
                                '} }}',
            },
            'prop.2.3': {'prop': 'leftTime'},
            'prop.2.4': {'prop': 'workTime'},
            'prop.2.5': {'prop': 'temp'},
            'prop.2.6': {'prop': 'mode', 'default': 0},
            'action.2.2': {'setter': 'setEnd'},
        },
    },
    'viomi.dishwasher.v01': {
        'chunk_properties': 1,
        'miio_props': ['program', 'custom_program'],
        'miio_specs': {
            # program_mapping:
            #miio.program, miio.custom_program -> miot_spec2.2_program    
            #       0                          -> 0,
            #       1                          -> 2,
            #       2                          -> 1,
            #       3  and custom_program == 3 -> 4,
            #       3  and custom_program == 4 -> 5,
            #       3  and custom_program == 5 -> 3,
            #       3 and custom_program == 250-> 6,
            
            'prop.2.2': {
                'prop': 'program', 
                'setter': 'set_program',
                'template': '{{ '
                            '0 if props.program == 0 else '
                            '1 if props.program == 2 else '
                            '2 if props.program == 1 else '
                            '3 if props.program == 3 and props.custom_program == 5 else '
                            '4 if props.program == 3 and props.custom_program == 3 else '
                            '5 if props.program == 3 and props.custom_program == 4 else '
                            '6 if props.program == 3 and props.custom_program == 250 else '
                            '0 }}',
                'set_template': '{{ {'
                                '"method": "set_program" if value <= 2 else "set_custom_program",'
                                '"params": '
                                '0 if value == 0 else '
                                '2 if value == 1 else '
                                '1 if value == 2 else '
                                '5 if value == 3 else '
                                '3 if value == 4 else '
                                '4 if value == 5 else '
                                '250 if value == 6 else '
                                '0,} }}',
            },
            'prop.2.3': {'prop': 'left_time', 'template': '{{ value|default(0,true)/60.0 }}'},
            'prop.2.4': {'prop': 'wash_status', 'dict': {
                0: 1,
                1: 2,
            }},
            'prop.2.5': {'prop': 'wash_temp'},
            'action.2.1': {
                'setter': True,
                'set_template': '{{ {'
                                '"method": "set_wash_action",'
                                '"params": 1,'
                                '} }}',
            },
            'action.2.2': {
                'setter': True,
                'set_template': '{{ {'
                                '"method": "set_wash_action",'
                                '"params": 0,'
                                '} }}',
            },
            'prop.3.1': {'prop': 'child_lock', 
                'setter': 'set_child_lock',
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
                },
        },
    },
    'viomi.health_pot.v1': {
        # methods: ['set_voice', 'set_work', 'delete_modes', 'set_mode_sort', 'set_mode']
        'miio_props': ['run_status', 'warm_data', 'last_time', 'last_temp', 'heat_power', 'warm_time', 'cook_time', 'cook_status', 'cooked_time', 'voice', 'stand_top_num', 'mode_sort'],
        'entity_attrs': ['run_status', 'warm_data', 'last_time', 'last_temp', 'heat_power', 'warm_time', 'cook_time', 'cook_status', 'cooked_time', 'voice', 'stand_top_num', 'mode_sort'],
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'work_status', 'dict': {
                0: 1,
                1: 2,
                2: 3,
                3: 4,
                4: 5,
                5: 6,
                },
            },
            'prop.2.2': {'prop': 'left_time'},
            'prop.2.3': {'prop': 'mode'},
            'prop.2.4': {'prop': 'curr_tempe'},
        },
    },
    'viomi.hood.v1': {
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': 'setPower', 'set_template': '{{ [value|int] }}'},
            'prop.2.2': {'prop': 'offDetime', 'setter': 'setOffTime'},
            'prop.3.1': {'prop': 'wind', 'setter': 'setWind', 'dict': {
                0: 1,
                1: 2,
                2: 3,
            }},
            'prop.4.1': {'prop': 'light', 'setter': 'setLight', 'set_template': '{{ [value|int] }}'},
        },
    },
    'viomi.vacuum.v7': {
        'miio_props': [
            'run_state', 'mode', 'err_state', 'battary_life', 'box_type', 'mop_type', 's_time', 's_area',
            'suction_grade', 'water_grade', 'remember_map', 'has_map', 'is_mop', 'has_newmap',
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'suction_grade', 'setter': 'set_suction', 'dict': {
                0: 0,  # Silent
                1: 1,  # Standard
                2: 1,  # Medium
                3: 2,  # Turbo
            }, 'default': 1},
            'prop.2.2': {'prop': 'run_state', 'dict': {
                0: 1,  # IdleNotDocked
                1: 1,  # Idle
                2: 3,  # Idle2
                3: 4,  # Cleaning
                4: 5,  # Returning
                5: 6,  # Docked
                6: 8,  # VacuumingAndMopping
                7: 7,  # Mopping
            }, 'default': 1},
            'prop.3.1': {'prop': 'battary_life'},
            'action.2.1': {'setter': 'set_mode_withroom', 'set_template': '{{ [0,1,0] }}'},  # start-sweep
            'action.2.2': {'setter': 'set_mode', 'set_template': '{{ [0] }}'},  # stop-sweeping
            'action.2.3': {'setter': 'set_mode_withroom', 'set_template': '{{ [1,1,0] }}'},  # start-sweep-mop
            'action.2.4': {'setter': 'set_mode_withroom', 'set_template': '{{ [3,1,0] }}'},  # start-mop
            'action.2.5': {'setter': 'set_mode_withroom', 'set_template': '{{ [0,3,0] }}'},  # pause-sweeping
            'action.3.1': {'setter': 'set_charge', 'set_template': '{{ [1] }}'},  # start-charge
            'prop.200.201': {'prop': 'main_brush_life'},
            'prop.200.202': {'prop': 'side_brush_life'},
            'prop.200.203': {'prop': 'hypa_life'},
            'prop.200.204': {'prop': 'mop_life'},
        },
    },
    'viomi.vacuum.v8': {
        'extend_model': 'viomi.vacuum.v7',
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': [
                    'sw_info', 'run_state', 'mode', 'err_state', 'battary_life', 'box_type', 'mop_type', 's_time',
                    's_area', 'suction_grade', 'water_grade', 'remember_map', 'has_map', 'is_mop', 'has_newmap',
                ],
                'values': True,
            },
            {
                'method': 'get_consumables',
                'template': '{%- set c0 = results[0] | default(0) | int(0) %}'
                            '{%- set c1 = results[1] | default(0) | int(0) %}'
                            '{%- set c2 = results[2] | default(0) | int(0) %}'
                            '{%- set c3 = results[3] | default(0) | int(0) %}'
                            '{{ {'
                            '"main_brush_hours": c0,'
                            '"side_brush_hours": c1,'
                            '"hypa_hours": c2,'
                            '"mop_hours": c3,'
                            '"main_brush_life": [100 - c0 / 360 * 100, 0] | max | round,'
                            '"side_brush_life": [100 - c1 / 180 * 100, 0] | max | round,'
                            '"hypa_life": [100 - c2 / 180 * 100, 0] | max | round,'
                            '"mop_life": [100 - c3 / 180 * 100, 0] | max | round,'
                            '} }}',
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'run_state', 'dict': {
                0: 1,  # IdleNotDocked
                1: 1,  # Idle
                2: 3,  # Idle2
                3: 4,  # Cleaning
                4: 5,  # Returning
                5: 6,  # Docked
                6: 8,  # VacuumingAndMopping
                7: 7,  # Mopping
            }, 'default': 1},
            'prop.2.2': {'prop': 'suction_grade', 'setter': 'set_suction'},
            'prop.3.1': {'prop': 'battary_life'},
        },
    },
    'viomi.waterheater.e1': {
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'targetTemp', 'setter': 'set_temp', 'set_template': '{{ [value|int] }}'},
            'prop.2.2': {'prop': 'waterTemp'},
            'prop.2.3': {'prop': 'washStatus'},
            'prop.2.4': {
                'prop': 'washStatus',
                'setter': 'set_power',
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
            'prop.2.5': {'prop': 'hotWater'},  # water-level
            'prop.2.6': {'prop': 'modeType', 'setter': 'set_mode'},
        },
    },
    'viomi.waterheater.u1': {
        'miio_specs': {
            'prop.2.2': {'prop': 'targetTemp', 'setter': 'set_temp', 'set_template': '{{ [value|int] }}'},
            'prop.2.3': {'prop': 'waterTemp'},
            'prop.2.5': {'prop': 'washStatus'},
            'prop.2.6': {
                'prop': 'washStatus',
                'setter': 'set_power',
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
            'prop.2.103': {'prop': 'velocity'},
        },
    },
    'viomi.waterheater.u7': {
        # ["washStatus","velocity","waterTemp","targetTemp","errStatus","preHeatTime1","preHeatTime2","isPreHeatNow"]
        # [2          ,    4      ,     44    ,       44   ,      0    ,  "0-6-10"   ,   "0-16-22"   ,   0]
        'miio_specs': {
            'prop.2.1': {'prop': 'targetTemp', 'setter': 'set_temp', 'set_template': '{{ [value|int] }}'},
            'prop.2.2': {'prop': 'waterTemp'},
            'prop.2.3': {'prop': 'washStatus'},
            'prop.2.4': {  # viomi.waterheater.u12
                'prop': 'washStatus',
                'setter': 'set_power',
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
            'prop.2.5': {
                'prop': 'washStatus',
                'setter': 'set_power',
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
            'prop.2.102': {'prop': 'targetTemp', 'setter': 'set_temp', 'dict': {
                99: 0,  # Custom
                39: 1,  # Children
                40: 2,  # Comfortable
                42: 3,  # Old Man
                36: 4,  # Kitchen
            }, 'default': 0},
            'prop.2.103': {'prop': 'velocity'},
            'prop.200.201': {
                'prop': 'isPreHeatNow',
                'setter': 'set_preheat_now',
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
        },
    },
    'viomi.waterheater.u8': 'viomi.waterheater.u7',
    'viomi.waterheater.u11': 'viomi.waterheater.u7',
    'viomi.waterheater.u12': 'viomi.waterheater.u7',

    'xiaomi.aircondition.ma1': {
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {
                'prop': 'power',
                'setter': True,
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
            'prop.2.2': {'prop': 'mode', 'setter': 'set_mode'},
            'prop.2.3': {'prop': 'settemp', 'setter': 'set_temp'},
            'prop.2.4': {
                'prop': 'energysave',
                'setter': True,
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
            'prop.2.5': {
                'prop': 'auxheat',
                'setter': True,
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
            'prop.2.6': {
                'prop': 'sleep',
                'setter': True,
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
            'prop.2.7': {
                'prop': 'dry',
                'setter': True,
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
            'prop.3.1': {'prop': 'wind_level', 'setter': True},
            'prop.3.2': {
                'prop': 'swing',
                'setter': True,
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
            'prop.4.1': {'prop': 'temperature'},
            'prop.5.1': {
                'prop': 'beep',
                'setter': True,
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
            'prop.6.1': {
                'prop': 'light',
                'setter': True,
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
        },
    },
    'xiaomi.aircondition.ma2': {
        'extend_model': 'xiaomi.aircondition.ma1',
        'miio_specs': {
            'prop.3.3': {},
        },
    },
    'xiaomi.aircondition.ma4': {
        'extend_model': 'xiaomi.aircondition.ma1',
        'miio_specs': {
            'prop.3.3': {
                'prop': 'swingh',
                'setter': True,
                'template': '{{ value != 0 }}',
                'set_template': '{{ [value|int(1)] }}',
            },
        },
    },
    'xiaomi.aircondition.ma5': 'xiaomi.aircondition.ma4',
    'xiaomi.aircondition.ma6': 'xiaomi.aircondition.ma1',
    'xiaomi.aircondition.ma9': 'xiaomi.aircondition.ma1',

    'xjx.toilet.pro': {
        'miio_specs': {
            'prop.2.1': {'prop': 'seating'},
        },
    },
    'xjx.toilet.relax': {
        'extend_model': 'xjx.toilet.pro',
        'miio_specs': {
            'prop.2.1': {'prop': 'seating'},
            'prop.2.2': {'prop': 'status_bubbleshield', 'setter': 'set_bubble', 'set_template': '{{ [value|int] }}'},
            'prop.3.1': {'prop': 'status_seatheat', 'setter': 'work_seatheat', 'set_template': '{{ [value|int] }}'},
            'prop.3.2': {'prop': 'seat_temp', 'setter': 'set_seat_temp'},
            'prop.4.1': {'prop': 'status_led', 'setter': 'work_night_led', 'set_template': '{{ [value|int] }}'},
            'action.2.101': {'setter': 'flush_on'},
        },
    },

    'yeelink.bhf_light.v1': {
        'extend_model': 'yeelink.bhf_light.v2',
        'miio_specs': {
            'prop.2.3': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': '{{ [value,"smooth",500] }}'},
            'prop.3.2': {'prop': 'temperature'},
            'prop.4.2': {
                'prop': 'swing_action',
                'setter': 'set_swing',
                'template': '{{ value in ["swing"] }}',
                'set_template': '{{ ["swing" if value else "stop",0] }}',
            },
            'prop.4.3': {'prop': 'swing_angle', 'setter': 'set_swing', 'set_template': '{{ ["swing",value] }}'},
            'prop.5.1': {'prop': 'temperature'},
            'prop.5.2': {'prop': 'humidity'},
        },
    },
    'yeelink.bhf_light.v2': {
        'miio_props': ['light_mode', 'nl_br'],
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {
                'prop': 'bright',
                'setter': True,
                'set_template': '{{ [value,"smooth",500] }}',
                'template': '{% set nlb = props.nl_br|default(0)|int(0) %}'
                            '{{ nlb if props.light_mode == "nightlight" else value }}',
            },
            'prop.2.101': {
                'prop': 'delayoff',
                'setter': 'set_scene',
                'set_template': '{{ ["auto_delay_off",props.bright|default(100)|int,value] }}',
            },
            'prop.2.103': {
                'prop': 'light_mode',
                'setter': 'set_power',
                'set_template': '{{ ["on","smooth",500,value] }}',
                'template': '{{ 5 if props.light_mode == "nightlight" else 1 }}',
            },
            'prop.3.1': {
                'prop': 'bh_mode',
                'setter': True,
                'dict': {
                    'bh_off':   1,  # stop_bath_heater
                    'warmwind': 2,
                    'venting':  3,
                    'drying':   4,
                    'coolwind': 5,
                },
                'default': 1,
                'set_template': '{{ '
                                '["warmwind", 2] if value == 2 else '
                                '["venting", 0] if value == 3 else '
                                '["drying", 0] if value == 4 else '
                                '["coolwind", 0] if value == 5 else '
                                '["bh_off", 0] }}',
            },
            'action.3.1': {'setter': 'bh_mode', 'set_template': '{{ ["bh_off", 0] }}'},
            'prop.3.102': {'prop': 'bh_delayoff', 'setter': 'bath_4modes_cron_start'},
            'prop.4.1': {
                'prop': 'fan_speed_idx',
                'setter': 'set_gears_idx',
                'template': 'yeelink_bhf_light_v2_fan_levels',
                'set_template': '{{ [value - 1] }}',
            },
        },
    },
    'yeelink.bhf_light.v3': {
        'extend_model': 'yeelink.bhf_light.v2',
        'miio_specs': {
            'prop.2.3': {'prop': 'bh_mode', 'dict': {
                'bh_off':   5,
                'warmwind': 1,
                'venting':  2,
                'drying':   3,
                'coolwind': 4,
            }, 'default': 5},
        },
    },
    'yeelink.bhf_light.v5': {
        'miio_template': 'yeelink_bhf_light_v5_miio_props',
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {
                'prop': 'light_mode',
                'template': '{{ 2 if value == "nightlight" else 1 }}',
            },
            'prop.2.3': {'prop': 'bright', 'setter': True, 'set_template': '{{ [value,"smooth",500] }}'},
            'prop.3.1': {
                'prop': 'bh_mode',
                'setter': True,
                'template': '{{ '
                            '3 if "fastdefog" in value else '
                            '4 if "fastwarm" in value else '
                            '1 if "drying" in value else '
                            '2 if "defog" in value else '
                            '8 if "venting" in value else '
                            '7 if "coolwind" in value else '
                            '6 if "warmwind" in value else '
                            '5 if "bh_off" in value else '
                            '0 }}',
                'set_template': '{{ '
                                '["drying"] if value == 1 else '
                                '["defog"] if value == 2 else '
                                '["fastdefog"] if value == 3 else '
                                '["fastwarm"] if value == 4 else '
                                '["warmwind", 2] if value == 6 else '
                                '["coolwind", 3] if value == 7 else '
                                '["venting", 3] if value == 8 else '
                                '["windoff"] if "coolwind" in props.bh_mode else '
                                '["windoff"] if "warmwind" in props.bh_mode else '
                                '["ventingoff"] if "venting" in props.bh_mode else '
                                '["bh_off", 0] }}',
                'set_callback': set_callback_via_param_index(0),
            },
            'prop.3.2': {
                'prop': 'bh_mode', 'setter': True,
                'template': '{{ "warm" in value }}',
                'set_template': '{{ ["warmwind" if value else "windoff"] }}',
            },
            'prop.3.3': {
                'prop': 'bh_mode', 'setter': True,
                'template': '{{ "coolwind" in value }}',
                'set_template': '{{ ["coolwind" if value else "windoff"] }}',
            },
            'prop.3.4': {
                'prop': 'bh_mode', 'setter': True,
                'template': '{{ "venting" in value }}',
                'set_template': '{{ ["venting" if value else "ventingoff"] }}',
            },
            'prop.3.5': {'prop': 'aim_temp', 'setter': 'set_temp'},
            'prop.3.6': {'prop': 'temperature'},
            'prop.3.101': {
                'prop': 'fan_speed_idx',
                'setter': 'set_bh_mode',
                'template': 'yeelink_bhf_light_v5_fan_levels',
                'set_template': '{{ ['
                                'props.bh_mode,'
                                '1 if value <= 1 else '
                                '3 if "coolwind" in props.bh_mode else '
                                '3 if "venting" in props.bh_mode else '
                                '2] }}',
            },
            'prop.3.111': {
                'prop': 'warmwind_gear',
                'setter': 'set_bh_mode',
                'set_template': '{{ ["warmwind" if value else "windoff", value] }}',
            },
            'prop.3.112': {
                'prop': 'coolwind_gear',
                'setter': 'set_bh_mode',
                'set_template': '{{ ["coolwind" if value else "windoff", value] }}',
            },
            'prop.3.113': {
                'prop': 'venting_gear',
                'setter': 'set_bh_mode',
                'set_template': '{{ ["venting" if value else "ventingoff", value] }}',
            },
            'action.3.1': {'setter': 'bh_mode', 'set_template': '{{ ["bh_off", 0] }}'},
        },
    },
    'yeelink.bhf_light.v6': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {
                'prop': 'light_mode',
                'setter': True,
                'template': '{{ 2 if value == "nightlight" else 1 }}',
                'set_template': '{{ {'
                                '"method":"set_ps",'
                                '"params":"on" if value == 2 else "off",'
                                '} }}',
            },
            'prop.2.3': {'prop': 'bright', 'setter': True, 'set_template': '{{ [value,"smooth",500] }}'},
            'prop.3.1': {
                'prop': 'bh_mode',
                'setter': True,
                'template': '{{ '
                            '7 if "fastdefog" in value else '
                            '6 if "fastwarm" in value else '
                            '1 if "coolwind" in value else '
                            '2 if "warmwind" in value else '
                            '3 if "venting" in value else '
                            '4 if "drying" in value else '
                            '5 if "defog" in value else '
                            '0 }}',
                'set_template': '{{ '
                                '["coolwind", 3] if value == 1 else '
                                '["warmwind", 2] if value == 2 else '
                                '["venting", 3] if value == 3 else '
                                '["drying"] if value == 4 else '
                                '["defog"] if value == 5 else '
                                '["fastwarm"] if value == 6 else '
                                '["fastdefog"] if value == 7 else '
                                '["windoff"] if "coolwind" in props.bh_mode else '
                                '["windoff"] if "warmwind" in props.bh_mode else '
                                '["ventingoff"] if "venting" in props.bh_mode else '
                                '["bh_off", 0] }}',
                'set_callback': set_callback_via_param_index(0),
            },
            'prop.3.2': {'prop': 'aim_temp', 'setter': 'set_temp'},
            'prop.3.3': {'prop': 'temperature'},
            'prop.3.101': {
                'prop': 'fan_speed_idx',
                'setter': 'set_bh_mode',
                'template': 'yeelink_bhf_light_v5_fan_levels',
                'set_template': '{{ ['
                                'props.bh_mode,'
                                '1 if value <= 1 else '
                                '3 if "coolwind" in props.bh_mode else '
                                '3 if "venting" in props.bh_mode else '
                                '2] }}',
            },
            'prop.3.111': {
                'prop': 'warmwind_gear',
                'setter': 'set_bh_mode',
                'set_template': '{{ ["warmwind" if value else "windoff", value] }}',
            },
            'prop.3.112': {
                'prop': 'coolwind_gear',
                'setter': 'set_bh_mode',
                'set_template': '{{ ["coolwind" if value else "windoff", value] }}',
            },
            'prop.3.113': {
                'prop': 'venting_gear',
                'setter': 'set_bh_mode',
                'set_template': '{{ ["venting" if value else "ventingoff", value] }}',
            },
            'action.3.1': {'setter': 'bh_mode', 'set_template': '{{ ["bh_off", 0] }}'},
        },
    },

    'yeelink.light.bslamp1': {
        'extend_model': 'yeelink.light.color1',
        'miio_specs': {
            'prop.2.6': {'prop': 'sat'},
        },
    },
    'yeelink.light.bslamp2': {
        'extend_model': 'yeelink.light.color2',
        'miio_specs': {
            'prop.2.6': {'prop': 'sat'},
        },
    },
    'yeelink.light.bslamp3': {
        'extend_model': 'yeelink.light.color2',
        'miio_specs': {
            'prop.2.4': {'prop': 'color_mode'},
            'prop.2.5': {'prop': 'rgb', 'setter': True},
        },
    },
    'yeelink.light.color1': {
        'extend_model': 'yeelink.light.color2',
        'miio_specs': {
            'prop.2.3': {'prop': 'rgb', 'setter': True},
            'prop.2.4': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': '{{ [value,"smooth",500] }}'},
        },
    },
    'yeelink.light.color2': {
        'miio_specs': {
            'prop.2.1': {
                'prop': 'power',
                'setter': True,
                'format': 'onoff',
                'set_template': '{{ ["on" if value else "off","smooth",500] }}',
            },
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': '{{ [value,"smooth",500] }}'},
            'prop.2.4': {'prop': 'rgb', 'setter': True},
            'prop.2.5': {'prop': 'color_mode'},
            'prop.2.101': {'prop': 'nl_br', 'setter': True},
            'prop.2.102': {
                'prop': 'delayoff',
                'setter': 'set_scene',
                'set_template': '{{ ["auto_delay_off",props.bright|default(100)|int,value] }}',
            },
        },
    },
    'yeelink.light.color3': 'yeelink.light.color2',
    'yeelink.light.color4': 'yeelink.light.color2',
    'yeelink.light.color5': 'yeelink.light.color2',
    'yeelink.light.color7': 'yeelink.light.color2',
    'yeelink.light.color8': 'yeelink.light.color2',
    'yeelink.light.ceiling1': {
        'extend_model': 'yeelink.light.ceiling2',
        'miio_specs': {
            'prop.2.4': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': '{{ [value,"smooth",500] }}'},
        },
    },
    'yeelink.light.ceiling2': {
        'miio_specs': {
            'prop.2.1': {
                'prop': 'power',
                'setter': True,
                'format': 'onoff',
                'set_template': '{{ ["on" if value else "off","smooth",500] }}',
            },
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {
                'prop': 'nl_br',
                'setter': 'set_ps',
                'template': '{{ 2 if value|int else 1 }}',
                'set_template': '{{ ["nightlight","on" if value == 2 else "off"] }}',
            },
            'prop.2.102': {
                'prop': 'delayoff',
                'setter': 'set_scene',
                'set_template': '{{ ["auto_delay_off",props.bright|default(100)|int,value] }}',
            },
        },
    },
    'yeelink.light.ceiling3': 'yeelink.light.ceiling1',
    'yeelink.light.ceiling4': {
        'extend_model': 'yeelink.light.ceiling1',
        'miio_specs': {
            'prop.200.201': {'prop': 'bg_power', 'setter': 'bg_set_power', 'format': 'onoff'},
            'prop.200.202': {'prop': 'bg_bright', 'setter': 'bg_set_bright'},
            'prop.200.203': {'prop': 'bg_ct', 'setter': 'bg_set_ct_abx', 'set_template': '{{ [value,"smooth",500] }}'},
            'prop.200.204': {'prop': 'bg_rgb', 'setter': 'bg_set_rgb'},
        },
    },
    'yeelink.light.ceiling5': {
        'extend_model': 'yeelink.light.ceiling1',
        'miio_specs': {
            'prop.2.5': {'prop': 'smart_switch'},  # set_ps ['cfg_smart_switch', '1']
        },
    },
    'yeelink.light.ceiling6': {
        'extend_model': 'yeelink.mirror.bm1',
        'miio_props': ['nl_br'],
        'miio_specs': {
            'prop.2.2': {
                'prop': 'bright',
                'setter': True,
                'template': '{% set nlb = props.nl_br|default(0)|int(0) %}{{ nlb if nlb else value }}',
            },
            'prop.2.4': {
                'prop': 'active_mode',
                'setter': 'set_ps',
                'template': '{{ 2 if value|int else 1 }}',
                'set_template': '{{ ["nightlight","on" if value == 2 else "off"] }}',
            },
        },
    },
    'yeelink.light.ceiling7': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling8': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling9': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling10': {
        'extend_model': 'yeelink.light.ceiling6',
        'miio_specs': {
            'prop.200.201': {'prop': 'bg_power', 'setter': 'bg_set_power', 'format': 'onoff'},
            'prop.200.202': {'prop': 'bg_bright', 'setter': 'bg_set_bright'},
            'prop.200.203': {'prop': 'bg_ct', 'setter': 'bg_set_ct_abx', 'set_template': '{{ [value,"smooth",500] }}'},
            'prop.200.204': {'prop': 'bg_rgb', 'setter': 'bg_set_rgb'},
        },
    },
    'yeelink.light.ceiling11': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling12': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling13': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling14': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling15': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling16': {
        'extend_model': 'yeelink.light.ceiling2',
        'miio_specs': {
            'prop.2.3': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': '{{ [value,"smooth",500] }}'},
        },
    },
    'yeelink.light.ceiling17': 'yeelink.light.ceiling16',
    'yeelink.light.ceiling18': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling19': 'yeelink.light.ceiling10',
    'yeelink.light.ceiling20': 'yeelink.light.ceiling10',
    'yeelink.light.ceiling21': {
        'extend_model': 'yeelink.light.ceiling22',
        'miio_specs': {
            'prop.2.4': {
                'prop': 'nl_br',
                'setter': 'set_ps',
                'template': '{{ 1 if value|int else 0 }}',
                'set_template': '{{ ["nightlight","on" if value == 1 else "off"] }}',
            },
        },
    },
    'yeelink.light.ceiling22': {
        'extend_model': 'yeelink.light.ceiling6',
        'miio_specs': {
            'prop.2.5': {'prop': 'smart_switch'},
        },
    },
    'yeelink.light.ceiling23': 'yeelink.light.ceiling22',
    'yeelink.light.ceiling24': 'yeelink.light.ceiling16',
    'yeelink.light.ceil27': {
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': ['power', 'active_mode', 'bright', 'ct', 'nl_br'],
                'values': True,
            },
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {
                'prop': 'active_mode',
                'setter': 'set_ps',
                'set_template': '{{ ["nightlight","on" if value == 1 else "off"] }}',
            },
            'prop.2.3': {
                'prop': 'bright',
                'setter': True,
                'template': '{% set nlb = props.nl_br|default(0)|int(0) %}'
                            '{{ nlb if props.active_mode|int(0) == 1 else value }}',
            },
            'prop.2.5': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': '{{ [value,"smooth",500] }}'},
        },
    },
    'yeelink.light.lamp1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': '{{ [value,"smooth",500] }}'},
            'prop.2.4': {'prop': 'color_mode'},
        },
    },
    'yeelink.light.lamp2': 'yeelink.light.ceiling16',
    'yeelink.light.lamp3': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
        },
    },
    'yeelink.light.lamp4': {
        'extend_model': 'yeelink.light.ceiling6',
        'miio_specs': {
            'prop.2.4': {'prop': None},
        },
    },
    'yeelink.light.lamp5': 'yeelink.light.lamp3',
    'yeelink.light.lamp7': 'yeelink.light.ceiling16',
    'yeelink.light.lamp9': 'yeelink.light.ceiling6',
    'yeelink.light.lamp10': 'yeelink.light.bslamp3',
    'yeelink.light.mono1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.3.1': {'prop': 'color_mode', 'setter': True},
        },
    },
    'yeelink.light.panel1': 'yeelink.light.ceiling2',
    'yeelink.light.panel3': 'yeelink.light.ceiling2',
    'yeelink.light.strip1': 'yeelink.light.color1',
    'yeelink.light.strip2': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {'prop': 'rgb', 'setter': True},
        },
    },
    'yeelink.light.strip4': 'yeelink.light.ceiling16',
    'yeelink.light.strip6': 'yeelink.light.strip2',
    'yeelink.light.strip8': 'yeelink.light.strip2',
    'yeelink.ven_fan.vf1': {
        'miio_specs': {
            'prop.2.1': {
                'prop': 'bh_mode',
                'setter': True,
                'template': '{{ value in ["coolwind"] }}',
                'set_template': '{{ ["coolwind" if value else "bh_off"] }}',
            },
            'prop.2.2': {'prop': 'gears', 'setter': 'set_gears_idx', 'dict': {
                0: 1,  # Low
                1: 2,  # High
            }, 'default': 1},
            'prop.2.3': {
                'prop': 'swing_action',
                'setter': 'set_swing',
                'template': '{{ value in ["swing"] }}',
                'set_template': '{{ ["swing" if value else "stop"] }}',
            },
        },
    },
    'yeelink.mirror.bm1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': '{{ [value,"smooth",500] }}'},
            'prop.2.102': {
                'prop': 'delayoff',
                'setter': 'set_scene',
                'set_template': '{{ ["auto_delay_off",props.bright|default(100)|int,value] }}',
            },
        },
    },
    'yeelink.ven_fan.vf3': {
        'extend_model': 'yeelink.ven_fan.vf5',
        'miio_specs': {
            'prop.2.3': {
                'prop': 'swing_action',
                'setter': 'set_swing',
                'template': '{{ value in ["swing"] }}',
                'set_template': '{{ ["swing" if value else "stop"] }}',
            },
        },
    },
    'yeelink.ven_fan.vf5': {
        'miio_specs': {
            'prop.2.1': {
                'prop': 'bh_mode',
                'setter': True,
                'template': '{{ value in ["coolwind"] }}',
                'set_template': '{{ ["coolwind" if value else "bh_off"] }}',
            },
            'prop.2.2': {'prop': 'gears', 'setter': 'set_gears_idx', 'dict': {
                0: 1,  # Low
                1: 2,  # High
            }, 'default': 1},
            'prop.2.4': {'prop': 'delayoff'},
            'prop.3.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.3.2': {
                'prop': 'nl_br',
                'setter': 'set_ps',
                'template': '{{ 2 if value|int else 1 }}',
                'set_template': '{{ ["nightlight","on" if value == 2 else "off"] }}',
            },
            'prop.3.3': {'prop': 'bright', 'setter': True},
        },
    },

    'yunmi.waterpuri.lx5': {
        'chunk_properties': 1,
        'miio_props': ['run_status', 'f1_totalflow', 'f1_totaltime', 'f2_totalflow', 'f2_totaltime'],
        'entity_attrs': ['run_status', 'f1_totalflow', 'f1_totaltime', 'f2_totalflow', 'f2_totaltime'],
        'miio_specs': {
            'prop.2.1': {'prop': 'temperature'},
            'prop.2.101': {'prop': 'rinse'},
            'prop.2.102': {'prop': 'lightMode', 'setter': True},
            'prop.2.103': {'prop': 'tds_warn_thd', 'setter': True},
            'prop.2.111': {
                'prop': 'f1_totaltime',
                'template': '{{ (100 - 100 * props.f1_usedtime / value) | round(1) }}',
            },
            'prop.2.112': {
                'prop': 'f2_totaltime',
                'template': '{{ (100 - 100 * props.f2_usedtime / value) | round(1) }}',
            },
            'prop.3.1': {'prop': 'tds_in'},
            'prop.3.2': {'prop': 'tds_out'},
            'prop.4.1': {'prop': 'f1_usedtime'},
            'prop.4.2': {'prop': 'f1_usedflow'},
            'prop.5.1': {'prop': 'f2_usedtime'},
            'prop.5.2': {'prop': 'f2_usedflow'},
        },
    },
    'yunmi.waterpuri.lx7': 'yunmi.waterpuri.lx5',
    'yunmi.waterpuri.lx9': {
        'extend_model': 'yunmi.waterpuri.lx5',
        'without_props': True,
        'miio_commands': [
            {
                'method': 'get_prop',
                'params': ['all'],
                'values': [
                    'run_status',
                    'f1_totalflow', 'f1_totaltime', 'f1_usedflow', 'f1_usedtime',
                    'f2_totalflow', 'f2_totaltime', 'f2_usedflow', 'f2_usedtime',
                    'tds_in', 'tds_out', 'rinse', 'temperature', 'tds_warn_thd',
                    'f3_totalflow', 'f3_totaltime', 'f3_usedflow', 'f3_usedtime',
                ],
            },
            {
                'method': 'get_prop',
                'params': ['lightMode'],
                'values': True,
            },
        ],
        'entity_attrs': [
            'run_status',
            'f1_totalflow', 'f1_totaltime',
            'f2_totalflow', 'f2_totaltime',
            'f3_totalflow', 'f3_totaltime',
        ],
        'miio_specs': {
            'prop.2.1': {'prop': 'tds_in'},
            'prop.2.2': {'prop': 'tds_out'},
            'prop.2.113': {
                'prop': 'f3_totaltime',
                'template': '{{ (100 - 100 * props.f3_usedtime / value) | round(1) }}',
            },
            'prop.3.1': {'prop': 'temperature'},
            'prop.5.1': {'prop': 'f3_usedtime'},
            'prop.5.2': {'prop': 'f3_usedflow'},
            'prop.6.1': {'prop': 'f2_usedtime'},
            'prop.6.2': {'prop': 'f2_usedflow'},
        },
    },
    'yunmi.waterpuri.lx11': {
        'extend_model': 'yunmi.waterpuri.lx9',
        'miio_specs': {
            'prop.2.1': {'prop': 'f1_usedtime'},
            'prop.2.2': {'prop': 'f1_usedflow'},
            'prop.2.113': {
                'prop': 'f3_totaltime',
                'template': '{{ (100 - 100 * props.f3_usedtime / value) | round(1) }}',
            },
            'prop.3.1': {'prop': 'f2_usedtime'},
            'prop.3.2': {'prop': 'f2_usedflow'},
            'prop.4.1': {'prop': 'f3_usedtime'},
            'prop.4.2': {'prop': 'f3_usedflow'},
            'prop.5.1': {'prop': 'tds_in'},
            'prop.5.2': {'prop': 'tds_out'},
            'prop.6.1': {'prop': 'temperature'},
        },
    },

    'yyunyi.wopener.yypy24': {
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'status', 'template': '{{ value|int + 1 }}'},
            'prop.2.2': {'prop': 'progress', 'setter': 'setProgress'},
            'prop.2.3': {'prop': 'speed', 'setter': 'setSpeed'},
            'prop.2.4': {
                'prop': 'status',
                'setter': 'setStatus',
                'template': '{{ value|int + 1 }}',
                'set_template': '{{ [value|int - 1] }}',
            },
            'prop.2.5': {
                'prop': 'mode',
                'setter': 'setMode',
                'template': '{{ value|int + 1 }}',
                'set_template': '{{ [value|int - 1] }}',
            },
            'prop.3.1': {'prop': 'alarm', 'setter': 'setAlarm', 'set_template': '{{ [value|int] }}'},
            'prop.4.1': {'prop': 'child_lock', 'setter': 'setChildLock', 'set_template': '{{ [value|int] }}'},
            'prop.2.102': {'prop': 'direction', 'setter': 'setDirection', 'set_template': '{{ [value|int] }}'},
            'prop.2.103': {'prop': 'clamp_strength', 'setter': 'setClampStrength'},
        },
    },

    'zhimi.aircondition.ma1': {
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'mode', 'dict': {
                'automode':   0,
                'cooling':    1,
                'arefaction': 2,
                'heat':       3,
                'wind':       4,
            }, 'default': 0},
            'prop.2.3': {
                'prop': 'st_temp_dec',
                'setter': 'set_temperature',
                'template': '{{ value|default(0,true)/10.0 }}',
                'set_template': '{{ (value*10)|int(0) }}',
            },
            'prop.2.4': {'prop': 'ptc', 'setter': True, 'format': 'onoff'},
            'prop.2.5': {'prop': 'silent', 'setter': True, 'format': 'onoff'},
            'prop.3.1': {'prop': 'speed_level', 'setter': 'set_spd_level', 'dict': {
                0: 1,
                1: 2,
                2: 3,
                3: 4,
                4: 5,
                5: 0,  # auto
            }},
            'prop.3.2': {'prop': 'vertical_swing', 'setter': 'set_vertical', 'format': 'onoff'},
            'prop.3.3': {'prop': 'vertical_rt', 'setter': 'set_ver_pos'},
            'prop.4.1': {'prop': 'temp_dec', 'template': '{{ value|default(0,true)/10.0 }}'},
            'prop.5.1': {
                'prop': 'volume_level',
                'setter': 'set_volume_sw',
                'set_template': '{{ [5 if value else 0] }}',
            },
            'prop.6.1': {'prop': 'lcd_level', 'setter': 'set_lcd', 'set_template': '{{ [5 if value else 0] }}'},
            'prop.6.2': {'prop': 'lcd_level', 'setter': 'set_lcd'},
        },
    },
    'zhimi.aircondition.ma2': 'zhimi.aircondition.ma1',
    'zhimi.aircondition.ma3': 'zhimi.aircondition.ma1',
    'zhimi.aircondition.ma4': 'zhimi.aircondition.ma1',
    'zhimi.aircondition.za1': 'zhimi.aircondition.ma1',

    'zhimi.airmonitor.v1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'aqi'},
            'prop.3.1': {'prop': 'battery'},
            'prop.3.2': {'prop': 'usb_state', 'dict': {
                'on':  1,  # Charging
                'off': 2,  # Not Charging
            }, 'default': 2},
            'prop.4.1': {'prop': 'time_state', 'setter': True, 'format': 'onoff'},
        },
    },

    'zhimi.airfresh.va2': {
        'miio_props': ['average_aqi', 'motor1_speed', 'use_time'],
        'entity_attrs': ['average_aqi', 'motor1_speed', 'use_time'],
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'mode', 'setter': True, 'dict': {
                'auto':     0,
                'silent':   1,
                'interval': 2,
                'low':      3,
                'middle':   4,
                'strong':   5,
            }, 'default': 0},
            'prop.3.1': {'prop': 'humidity'},
            'prop.3.2': {'prop': 'aqi'},
            'prop.3.3': {'prop': 'temp_dec', 'template': '{{ value|default(0,true)/10.0 }}'},
            'prop.3.4': {'prop': 'co2'},
            'prop.4.1': {'prop': 'f1_hour_used'},
            'prop.5.1': {'prop': 'child_lock', 'setter': True, 'format': 'onoff'},
            'prop.6.1': {'prop': 'buzzer', 'setter': True, 'format': 'onoff'},
            'prop.7.1': {'prop': 'led_level', 'setter': True},
        },
    },
    'zhimi.airfresh.va4': {
        'extend_model': 'zhimi.airfresh.va2',
        'miio_props': ['average_aqi', 'use_time'],
        'entity_attrs': ['average_aqi', 'use_time'],
        'miio_specs': {
            'prop.2.3': {'prop': 'mode', 'setter': True, 'dict': {
                'interval': 0,
                'silent':   1,
                'low':      2,
                'middle':   3,
                'strong':   4,
                'auto':     5,
            }, 'default': 5},
            'prop.2.4': {'prop': 'ptc_state', 'setter': True, 'format': 'onoff'},
            'prop.3.1': {'prop': 'aqi'},
            'prop.3.2': {'prop': 'co2'},
            'prop.3.3': {'prop': 'temp_dec'},
            'prop.3.4': {'prop': 'humidity'},
            'prop.3.101': {'prop': 'motor1_speed'},
            'prop.5.1': {'prop': 'led_level', 'setter': True},
            'prop.6.1': {'prop': 'child_lock', 'setter': True, 'format': 'onoff'},
            'prop.7.1': {'prop': 'buzzer', 'setter': True, 'format': 'onoff'},
        },
    },
    'zhimi.airpurifier._base': {
        # https://github.com/rytilahti/python-miio/blob/master/miio/integrations/airpurifier/zhimi/airpurifier.py
        'chunk_properties': 15,
        'miio_props': ['bright', 'motor1_speed', 'motor2_speed', 'purify_volume'],
        'entity_attrs': ['aqi', 'bright', 'motor1_speed', 'motor2_speed', 'purify_volume'],
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'mode', 'setter': True, 'dict': {
                'auto':   0,
                'silent': 1,
                'low':    1,
                'medium': 2,
                'strong': 3,
                'high':   3,
            }, 'default': 0},
            'prop.3.1': {'prop': 'aqi'},
            'prop.4.1': {'prop': 'filter1_life'},
            'prop.5.1': {'prop': 'led', 'setter': True, 'format': 'onoff'},
            'prop.6.1': {'prop': 'buzzer', 'setter': True, 'format': 'onoff'},
            'prop.2.101': {'prop': 'bright'},  # illumination
            'prop.2.102': {'prop': 'motor1_speed'},
        },
    },
    'zhimi.airpurifier.m1': {
        'extend_model': 'zhimi.airpurifier.v3',
        'miio_specs': {
            'prop.2.2': {'prop': 'mode', 'setter': True, 'dict': {
                'auto':     0,
                'silent':   1,
                'favorite': 2,
            }, 'default': 0},
            'prop.3.1': {'prop': 'humidity'},
            'prop.3.2': {'prop': 'aqi'},
            'prop.3.3': {'prop': 'temp_dec', 'template': '{{ value|default(0,true)/10.0 }}'},
            'prop.4.2': {'prop': 'f1_hour_used'},
            'prop.5.2': {'prop': 'led_b', 'setter': True},
            'prop.8.1': {'prop': 'favorite_level', 'setter': 'set_level_favorite'},
        },
    },
    'zhimi.airpurifier.m2': 'zhimi.airpurifier.m1',
    'zhimi.airpurifier.ma2': 'zhimi.airpurifier.v6',
    'zhimi.airpurifier.mc1': {
        'extend_model': 'zhimi.airpurifier.v6',
        'miio_specs': {
            'prop.4.2': {
                'prop': 'f1_hour_used',
                'template': '{{ value/(props.filter1_life|default(0,true)/100)-value }}',
            },
        },
    },
    'zhimi.airpurifier.mc2': 'zhimi.airpurifier.mc1',
    'zhimi.airpurifier.sa2': {
        'extend_model': 'zhimi.airpurifier._base',
        'miio_specs': {
            'prop.2.2': {'prop': 'mode', 'setter': True, 'dict': {
                'auto':     0,
                'silent':   1,
                'favorite': 2,
                'low':      3,
                'medium':   4,
                'strong':   5,
                'high':     5,
            }, 'default': 0},
            'prop.2.3': {'prop': 'mode', 'setter': True, 'dict': {
                'auto':     0,
                'silent':   1,
                'favorite': 2,
                'idle':     3,
            }, 'default': 3},
            'prop.3.1': {'prop': 'humidity'},
            'prop.3.2': {'prop': 'aqi'},
            'prop.3.3': {'prop': 'temp_dec', 'template': '{{ value|default(0,true)/10.0 }}'},
            'prop.4.2': {'prop': 'f1_hour_used'},
            'prop.5.1': {'prop': 'filter2_life'},
            'prop.5.2': {'prop': 'f2_hour_used'},
            'prop.6.1': {'prop': 'led', 'setter': True, 'format': 'onoff'},
            'prop.6.2': {'prop': 'led_b', 'setter': True},
            'prop.7.1': {'prop': 'volume', 'setter': True, 'set_template': '{{ [100 if value else 0] }}'},
            'prop.8.1': {'prop': 'child_lock', 'setter': True, 'format': 'onoff'},
            'prop.9.1': {'prop': 'favorite_level', 'setter': 'set_level_favorite'},
        },
    },
    'zhimi.airpurifier.v1': {
        'extend_model': 'zhimi.airpurifier._base',
        'miio_specs': {
            'prop.2.3': {'prop': 'mode', 'setter': True, 'dict': {
                'auto':   0,
                'silent': 1,  # Sleep
                'strong': 2,
                'idle':   3,
            }, 'default': 0},
            'prop.5.2': {
                'prop': 'led_b',
                'setter': True,
                'dict': {
                    0: 15,  # Bright
                    1: 10,  # Dim
                    2: 5,   # Off
                },
                'default': 0,
                'set_template': '{{ ['
                                '0 if value > 10 else '
                                '1 if value > 5 else '
                                '2] }}',
            },
        },
    },
    'zhimi.airpurifier.v2': {
        'extend_model': 'zhimi.airpurifier._base',
        'miio_specs': {
            'prop.4.2': {
                'prop': 'f1_hour_used',
                'template': '{{ value/(props.filter1_life|default(0,true)/100)-value }}',
            },
            'prop.7.1': {'prop': 'child_lock', 'setter': True, 'format': 'onoff'},
        },
    },
    'zhimi.airpurifier.v3': {
        'extend_model': 'zhimi.airpurifier.v2',
        'miio_specs': {
            'prop.2.3': {'prop': 'mode', 'setter': True, 'dict': {
                'auto':   0,
                'silent': 1,
                'strong': 2,
                'high':   2,
                'idle':   3,
            }, 'default': 3},
        },
    },
    'zhimi.airpurifier.v5': 'zhimi.airpurifier.v2',
    'zhimi.airpurifier.v6': {
        'extend_model': 'zhimi.airpurifier.m1',
        'miio_specs': {
            'prop.2.3': {'prop': 'mode', 'setter': True, 'dict': {
                'auto':     0,
                'silent':   1,
                'favorite': 2,
            }, 'default': 0},
            'prop.6.1': {'prop': 'volume', 'setter': True, 'set_template': '{{ [100 if value else 0] }}'},
        },
    },
    'zhimi.airpurifier.v7': {
        'extend_model': 'zhimi.airpurifier.m1',
        'miio_specs': {
            'prop.5.1': {'prop': 'child_lock', 'setter': True, 'format': 'onoff'},
            'prop.6.1': {'prop': 'volume', 'setter': True, 'set_template': '{{ [100 if value else 0] }}'},
            'prop.7.1': {'prop': 'led', 'setter': True, 'format': 'onoff'},
            'prop.2.103': {'prop': 'favorite_level', 'setter': 'set_level_favorite'},
            'prop.2.104': {'prop': 'act_det', 'setter': True, 'format': 'onoff'},
        },
    },

    'zhimi.fan.sa1': {
        # https://github.com/rytilahti/python-miio/blob/9bc6b65ce846707db7e83d403dd2c71d4e6bfa31/miio/fan.py#L321-L322
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {
                'prop': 'speed_level',
                'setter': True,
                'template': '{% set lvl = props.natural_level|default(value,true)|int(0) %}'
                            '{{ '
                            'lvl if max == 100 else '
                            '1 if lvl <= 25 else '
                            '2 if lvl <= 50 else '
                            '3 if lvl <= 75 else '
                            '4 }}',
                'set_template': '{% set nlv = props.natural_level|default(0)|int(0) %}'
                                '{{ {'
                                '"method": "set_natural_level" if nlv else "set_speed_level",'
                                '"params": [value|int(0) * (1 if max == 100 else 25)],'
                                '} }}',
            },
            'prop.2.3': {'prop': 'angle_enable', 'setter': True, 'format': 'onoff'},
            'prop.2.4': {'prop': 'angle', 'setter': True},
            'prop.2.5': {
                'prop': 'natural_level',
                'setter': True,
                'template': '{{ 1 if value|int(0) > 0 else 2 }}',
                'set_template': '{{ [value|int(0) * 25] }}',
            },
            'prop.3.1': {'prop': 'child_lock', 'setter': True, 'format': 'onoff'},
        },
    },
    'zhimi.fan.v2': {
        'extend_model': 'zhimi.fan.sa1',
        'chunk_properties': 15,
        'miio_specs': {
            'prop.2.5': {
                'prop': 'natural_level',
                'setter': True,
                'template': '{{ 1 if value|int(0) > 0 else 0 }}',
                'set_template': '{{ [value|int(0) * 25] }}',
            },
            'prop.4.1': {'prop': 'battery'},
            'prop.4.2': {'prop': 'bat_charge', 'template': '{{ 2 if value == "complete" else 1 }}'},
        },
    },
    'zhimi.fan.v3': 'zhimi.fan.v2',
    'zhimi.fan.za1': 'zhimi.fan.sa1',
    'zhimi.fan.za3': {
        'extend_model': 'zhimi.fan.sa1',
        'miio_specs': {
            'prop.2.5': {
                'prop': 'natural_level',
                'setter': True,
                'template': '{{ 1 if value|int(0) > 0 else 0 }}',
                'set_template': '{{ [value|int(0) * 25] }}',
            },
            'prop.2.6': {
                'prop': 'speed_level',
                'setter': True,
                'template': '{{ props.natural_level|default(value,true)|int(0) }}',
                'set_template': '{% set nlv = props.natural_level|default(0)|int(0) %}'
                                '{{ {'
                                '"method": "set_natural_level" if nlv else "set_speed_level",'
                                '"params": [value|int(0)],'
                                '} }}',
            },
            'prop.4.1': {
                'prop': 'buzzer',
                'setter': True,
                'template': '{{ value|int(0) > 0 }}',
                'set_template': '{{ [1 if value else 0] }}',
            },
            'prop.5.1': {
                'prop': 'led_b',
                'setter': True,
                'template': '{{ value|int(0) > 0 }}',
                'set_template': '{{ [1 if value else 0] }}',
            },
        },
    },
    'zhimi.fan.za4': 'zhimi.fan.za3',

    'zhimi.humidifier.ca1': {
        'extend_model': 'zhimi.humidifier.v1',
        # https://github.com/rytilahti/python-miio/blob/9bc6b65ce846707db7e83d403dd2c71d4e6bfa31/miio/airhumidifier.py#L297-L302
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.3': {'prop': 'depth'},
        },
    },
    'zhimi.humidifier.cb1': {
        'extend_model': 'zhimi.humidifier.ca1',
        'miio_specs': {
            'prop.3.2': {'prop': 'temperature'},
        },
    },
    'zhimi.humidifier.cb2': 'zhimi.humidifier.cb1',
    'zhimi.humidifier.v1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'mode', 'setter': True, 'dict': {
                'auto':   0,
                'silent': 1,
                'medium': 2,
                'high':   3,
                'strong': 3,
            }, 'default': 0},
            'prop.3.1': {'prop': 'humidity'},
            'prop.3.2': {'prop': 'temp_dec', 'template': '{{ value / 10.0 }}'},
            'prop.4.1': {'prop': 'buzzer', 'setter': True, 'format': 'onoff'},
            'prop.5.1': {'prop': 'child_lock', 'setter': True, 'format': 'onoff'},
        },
    },
    'qmi.powerstrip.v1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
        },
    },
    'zimi.powerstrip.v2': {
        'miio_props': ['current', 'mode', 'power_price'],
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'temperature'},
            'prop.3.1': {'prop': 'power_consume_rate'},
            'prop.4.1': {'prop': 'wifi_led'},
        },
    },
}
