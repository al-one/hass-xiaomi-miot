MIIO_TO_MIOT_SPECS = {

    'chuangmi.plug.m1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'temperature'},
            'prop.3.1': {'prop': 'wifi_led'},
        },
    },
    'chuangmi.plug.m3': 'chuangmi.plug.m1',
    'chuangmi.plug.v1': {
        'miio_specs': {
            'prop.2.1': {'prop': 'on'},
            'prop.3.1': {'prop': 'wifi_led'},
        },
    },
    'chuangmi.plug.v3': {
        'miio_specs': {
            'prop.2.1': {'prop': 'on'},
            'prop.3.1': {'prop': 'usb_on'},
            'prop.2.2': {'prop': 'temperature'},
            'prop.4.1': {'prop': 'wifi_led'},
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
       
    'lumi.acpartner.mcn02': {
        # ['power', 'mode', 'tar_temp', 'fan_level', 'ver_swing', 'load_power']
        # ['on',    'dry',   16,        'small_fan', 'off',        84.0]
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'mode', 'setter': True, 'dict': {
                'auto':   0,  # run mode
                'cool':   1,
                'dry':   2,
                'heat':   3,
                'wind':   4,
            }, 'default': 0},
            'prop.2.3': {'prop': 'tar_temp', 'setter': True},
            'prop.3.1': {'prop': 'fan_level', 'setter': True, 'dict': {
                'auto_fan':   0,  # fan-level
                'small_fan':   1,
                'medium_fan':   2,
                'large_fan':   3,
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
                'on': 2,
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
                'off':   1,  # run status
                'standby':   2,
                'run':   3,
                'delay':   4,
                'pause':   5,
                'fault':   6,
                'eoc':   7,
            }},
            'prop.2.3': {'prop': 'cycle', 'setter': True, 'dict': {
                'dailywash':   1,  # mode
                'quick':   2,
                'delicate':   3,
                'down':   4,
                'heavy':   5,
                'userdefine':   6,
                'rinse':   7,
                'spin':   8,
                'cotton':   9,
                'synthetic':   10,
                'shirt':   11,
                'boiling':   12,
                'wool':   13,
                'drumclean':   14,
                'babycare':   15,
                'intensive':   16,
                'jacket':   17,
                'washdry':   18,
                'underwear':   19,
                'dry':   20,
                'dryairwash':   21,
                'washdryquick':   22,
            }, 'default': 1},
            'prop.2.4': {'prop': 'time_remain', 'setter': True},
            'prop.2.5': {'prop': 'speed', 'setter': True, 'set_template': '{{ value ~ "rpm" }}', 'template': '{{ value | regex_replace("rpm","") | int }}'},
            'prop.2.6': {'prop': 'temp','setter': True, 'set_template': '{{ [value | string if value else "cool"] }}', 'template': '{{ value | int(0) }}'},
            'prop.2.7': {'prop': 'water_level', 'setter': True, 'dict': {
                'high':   1,  # water_level status
                'middle':   2,
                'low':   3,
            }, 'default': 3},
            'prop.2.8': {'prop': 'rinse_time', 'setter': True, 'set_template': '{{ [value | string] }}', 'template': '{{ value | int }}'},
            'prop.2.9': {'prop': 'dry_set', 'setter': True, 'dict':{
                'moist':   1, #dry level status
                'normal':   2,
                'extra':   3,
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

    'xjx.toilet.relax': {
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
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
            'prop.2.3': {'prop': 'ct', 'setter': 'set_ct_abx', 'set_template': "{{ [value,'smooth',500] }}"},
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
