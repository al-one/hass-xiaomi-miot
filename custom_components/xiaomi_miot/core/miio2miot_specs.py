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

    'rockrobo.vacuum.v1': {
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
            'prop.3.2': {'prop': 'charging', 'template': '{{ 1 if props.state in [8] else 2 }}'},
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

    'yeelink.bhf_light.v2': {
        'miio_specs': {
            'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
            'prop.2.2': {'prop': 'bright', 'setter': True},
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
