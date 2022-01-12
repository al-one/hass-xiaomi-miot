MIIO_TO_MIOT_SPECS = {

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

    'chuangmi.plug.hmi205': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'temperature'},
        },
    },
    'chuangmi.plug.hmi206': 'chuangmi.plug.hmi205',
    'chuangmi.plug.hmi208': {
        'extend_model': 'chuangmi.plug.hmi205',
        'miio_specs': {
            'prop.3.1': {
                'prop': 'usb_on',
                'setter': True,
                'set_template': '{{ {"method": "set_usb_on" if value else "set_usb_off"} }}',
            },
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
            'prop.3.1': {'prop': 'wifi_led', 'setter': True, 'format': 'onoff'},
        },
    },
    'chuangmi.plug.v3': {
        'extend_model': 'chuangmi.plug.hmi208',
        'miio_specs': {
            'prop.2.1': {'prop': 'on', 'setter': 'set_power', 'format': 'onoff'},
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
            'prop.2.101': {'prop': 'menu'},
            'prop.2.102': {'prop': 't_left'},
            'action.2.1': {'setter': 'cancel_cooking'},
        },
    },
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
            'prop.2.2': {'prop': 'flip', 'template': "{{ 0 if value in ['off'] else 180 }}"},
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
                'format': 'onoff',
                'setter': 'control_device',
                'set_template': '{{ ["start_hotdry",90] if value else ["stop_hotdry",0] }}',
            },
            'prop.2.101': {
                'prop': 'dry_status','dict': {
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

    'mijia.camera.v3': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'flip', 'template': "{{ 0 if value in ['off'] else 180 }}"},
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
                'set_template': '{{ value ~ "rpm" }}',
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
    'minij.washer.v14': 'minij.washer.v5',

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

    'philips.light.bulb': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {'prop': 'snm', 'setter': 'apply_fixed_scene'},
            'prop.2.4': {'prop': 'cct', 'setter': True},
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

    'rockrobo.vacuum.v1': {
        'extend_model': 'roborock.vacuum.t6',
        'miio_specs': {
            'prop.3.2': {'prop': 'charging', 'template': '{{ 1 if props.state in [8] else 2 }}'},
        },
    },

    'roborock.vacuum.t6': {
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
        ],
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
            'prop.2.2': {'prop': 'fan_power'},
            'prop.3.1': {'prop': 'battery'},
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
            'prop.2.1': {'prop': 'power', 'setter': True, 'set_template': "{{ [1 if value else 0] }}"},
            'prop.3.1': {'prop': 'bright_value', 'setter': True, 'set_template': "{{ [1 if value else 0] }}"},
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
    'viomi.vacuum.v7': {
        'miio_specs': {
            'prop.2.1': {'prop': 'suction_grade', 'dict': {
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
        },
    },
    'viomi.waterheater.e1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'targetTemp', 'setter': 'set_temp', 'set_template': '{{ value|int }}'},
            'prop.2.2': {'prop': 'waterTemp'},
            'prop.2.3': {'prop': 'washStatus'},
            'prop.2.4': {
                'prop': 'washStatus',
                'setter': 'set_power',
                'template': '{{ value != 0 }}',
                'set_template': '{{ value|int }}',
            },
            'prop.2.5': {'prop': None},  # water-level
            'prop.2.6': {'prop': 'modeType', 'setter': 'set_mode'},
        },
    },

    'xjx.toilet.pro': {
        'miio_specs': {
            'prop.2.1': {'prop': 'seating'},
        },
    },
    'xjx.toilet.relax': {
        'extend_model': 'xjx.toilet.pro',
        'miio_specs': {
            'prop.2.1': {'prop': 'seating'},
            'prop.2.2': {'prop': 'status_bubbleshield', 'setter': 'set_bubble', 'set_template': '{{ value|int }}'},
            'prop.3.1': {'prop': 'status_seatheat', 'setter': 'work_seatheat', 'set_template': '{{ value|int }}'},
            'prop.3.2': {'prop': 'seat_temp', 'setter': 'set_seat_temp'},
            'prop.4.1': {'prop': 'status_led', 'setter': 'work_night_led', 'set_template': '{{ value|int }}'},
        },
    },

    'yeelink.bhf_light.v2': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True, 'set_template': '{{ [value,"smooth",500] }}'},
            'prop.3.1': {'prop': 'bh_mode', 'dict': {
                'bh_off':   1,  # stop_bath_heater
                'warmwind': 2,
                'venting':  3,
                'drying':   4,
                'coolwind': 5,
            }, 'default': 1},
            'prop.4.1': {'prop': 'fan_speed_idx', 'template': 'yeelink_bhf_light_v2_fan_levels'},
        },
    },
    'yeelink.bhf_light.v5': {
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
                'dict': {
                    'drying':    1,
                    'defog':     2,
                    'fastdefog': 3,
                    'fastwarm':  4,
                    'bh_off':    5,
                    'warmwind':  6,
                },
                'default': 5,
                'template': '{{ '
                            '3 if "fastdefog" in value else '
                            '4 if "fastwarm" in value else '
                            '1 if "drying" in value else '
                            '2 if "defog" in value else '
                            '6 if "warmwind" in value else '
                            '5 }}',
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
            'prop.2.4': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': "{{ [value,'smooth',500] }}"},
            'prop.2.101': {'prop': 'nl_br', 'setter': True},
            'prop.200.201': {'prop': 'delayoff'},
        },
    },
    'yeelink.light.color2': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': "{{ [value,'smooth',500] }}"},
            'prop.2.4': {'prop': 'rgb', 'setter': True},
            'prop.2.5': {'prop': 'color_mode'},
        },
    },
    'yeelink.light.color3': 'yeelink.light.color2',
    'yeelink.light.color4': 'yeelink.light.color2',
    'yeelink.light.ceiling1': {
        'extend_model': 'yeelink.light.ceiling2',
        'miio_specs': {
            'prop.2.4': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': "{{ [value,'smooth',500] }}"},
        },
    },
    'yeelink.light.ceiling2': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {
                'prop': 'nl_br',
                'setter': 'set_ps',
                'template': '{{ 2 if value|int else 1 }}',
                'set_template': "{{ ['nightlight','on' if value == 2 else 'off'] }}",
            },
        },
    },
    'yeelink.light.ceiling3': 'yeelink.light.ceiling1',
    'yeelink.light.ceiling4': 'yeelink.light.ceiling1',
    'yeelink.light.ceiling5': {
        'extend_model': 'yeelink.light.ceiling1',
        'miio_specs': {
            'prop.2.5': {'prop': 'smart_switch'},  # set_ps ['cfg_smart_switch', '1']
        },
    },
    'yeelink.light.ceiling6': {
        'extend_model': 'yeelink.mirror.bm1',
        'miio_specs': {
            'prop.2.4': {
                'prop': 'nl_br',
                'setter': 'set_ps',
                'template': '{{ 2 if value|int else 1 }}',
                'set_template': "{{ ['nightlight','on' if value == 2 else 'off'] }}",
            },
        },
    },
    'yeelink.light.ceiling7': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling8': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling9': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling10': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling11': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling12': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling13': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling14': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling15': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling16': {
        'extend_model': 'yeelink.light.ceiling2',
        'miio_specs': {
            'prop.2.3': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': "{{ [value,'smooth',500] }}"},
        },
    },
    'yeelink.light.ceiling17': 'yeelink.light.ceiling16',
    'yeelink.light.ceiling18': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling19': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling20': 'yeelink.light.ceiling6',
    'yeelink.light.ceiling21': {
        'extend_model': 'yeelink.light.ceiling6',
        'miio_specs': {
            'prop.2.5': {'prop': 'smart_switch'},
        },
    },
    'yeelink.light.ceiling22': 'yeelink.light.ceiling21',
    'yeelink.light.ceiling23': 'yeelink.light.ceiling21',
    'yeelink.light.ceiling24': 'yeelink.light.ceiling16',
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
                'template': "{{ value in ['coolwind'] }}",
                'set_template': "{{ ['coolwind' if value else 'bh_off'] }}",
            },
            'prop.2.2': {'prop': 'gears', 'setter': 'set_gears_idx', 'dict': {
                0: 1,  # Low
                1: 2,  # High
            }, 'default': 1},
            'prop.2.3': {
                'prop': 'swing_action',
                'setter': 'set_swing',
                'template': "{{ value in ['swing'] }}",
                'set_template': "{{ ['swing' if value else 'stop'] }}",
            },
        },
    },
    'yeelink.mirror.bm1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': "{{ [value,'smooth',500] }}"},
        },
    },
    'yeelink.ven_fan.vf3': {
        'extend_model': 'yeelink.ven_fan.vf5',
        'miio_specs': {
            'prop.2.3': {
                'prop': 'swing_action',
                'setter': 'set_swing',
                'template': "{{ value in ['swing'] }}",
                'set_template': "{{ ['swing' if value else 'stop'] }}",
            },
        },
    },
    'yeelink.ven_fan.vf5': {
        'miio_specs': {
            'prop.2.1': {
                'prop': 'bh_mode',
                'setter': True,
                'template': "{{ value in ['coolwind'] }}",
                'set_template': "{{ ['coolwind' if value else 'bh_off'] }}",
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
                'set_template': "{{ ['nightlight','on' if value == 2 else 'off'] }}",
            },
            'prop.3.3': {'prop': 'bright', 'setter': True},
        },
    },

    'zhimi.airmonitor.v1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'aqi'},
            'prop.3.1': {'prop': 'battery'},
            'prop.3.2': {'prop': 'usb_state', 'dict': {
                "on": 1,  # Charging
                "off": 2,  # Not Charging
            }, 'default': 2},
            'prop.4.1': {'prop': 'time_state', 'setter': True, 'format': 'onoff'},
        },
    },
    'zhimi.fan.sa1': {
        'chunk_properties': 1,
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {
                'prop': 'speed_level',
                'setter': True,
                'template': '{% set lvl = props.natural_level|default(value,true)|int(0) %}'
                            '{{ '
                            '1 if lvl <= 25 else '
                            '2 if lvl <= 50 else '
                            '3 if lvl <= 75 else '
                            '4 }}',
                'set_template': '{% set nlv = props.natural_level|default(0)|int(0) %}'
                                '{{ {'
                                '"method": "set_natural_level" if nlv else "set_speed_level",'
                                '"params": [value|int(0) * 25],'
                                '} }}',
            },
            'prop.2.3': {'prop': 'angle_enable', 'setter': True, 'format': 'onoff'},
            'prop.2.4': {'prop': 'angle', 'setter': True},
            'prop.2.5': {
                'prop': 'natural_level',
                'setter': True,
                'template': '{{ 1 if value|int(0) > 0 else 2 }}',
                'set_template': '{{ value|int(0) * 25 }}',
            },
            'prop.3.1': {'prop': 'child_lock', 'setter': True, 'format': 'onoff'},
        },
    },
    'zhimi.fan.v2': {
        'extend_model': 'zhimi.fan.sa1',
        'miio_specs': {
            'prop.2.5': {
                'prop': 'natural_level',
                'setter': True,
                'template': '{{ 1 if value|int(0) > 0 else 0 }}',
                'set_template': '{{ value * 25 }}',
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
                'set_template': '{{ value|int(0) * 25 }}',
            },
            'prop.4.1': {
                'prop': 'buzzer',
                'setter': True,
                'template': '{{ value|int(0) > 0 }}',
                'set_template': '{{ 1 if value else 0 }}',
            },
            'prop.5.1': {
                'prop': 'led_b',
                'setter': True,
                'template': '{{ value|int(0) > 0 }}',
                'set_template': '{{ 1 if value else 0 }}',
            },
        },
    },
    'zhimi.fan.za4': 'zhimi.fan.za3',

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
