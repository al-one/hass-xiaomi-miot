DEVICE_CUSTOMIZES = {

    'cgllc.airm.cgdn1': {
        'chunk_properties': 9,
    },
    'chuangmi.plug.212a01': {
        'chunk_properties': 7,
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'micloud_statistics': [
            {
                'type': 'stat_day_v3',
                'key': 'prop.5.1',
                'day': 32,
                'limit': 31,
                'attribute': None,
                'template': 'micloud_statistics_power_cost',
            },
        ],
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
        'miio_prop_cal_day_power_cost_template': 'chuangmi_plug_v3_power_cost',
    },
    'chuangmi.plug.*': {
        'sensor_properties': 'temperature',
    },
    'chuangmi.plug.*:electric_power': {
        'value_ratio': 0.01,
        'state_class': 'measurement',
        'device_class': 'power',
        'unit_of_measurement': 'W',
    },
    'chuangmi.plug.*:power_consumption': {
        'value_ratio': 0.001,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'chuangmi.plug.*:power_cost_today': {
        'value_ratio': 0.0001,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'chuangmi.plug.*:power_cost_month': {
        'value_ratio': 0.0001,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'chuangmi.plug.*:prop_cal_day.power_cost:today': {
        'value_ratio': 0.001,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'chuangmi.plug.*:prop_cal_day.power_cost:month': {
        'value_ratio': 0.001,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
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
    'lumi.acpartner.mcn02': {
        'miio_cloud_props': 'load_power',
    },
    'lumi.acpartner.mcn04': {
        'chunk_properties': 7,
    },
    'lumi.acpartner.*': {
        'sensor_attributes': 'electric_power,power_cost_today,power_cost_month',
        'miio_cloud_props': 'ac_power',
        'miio_cloud_props_template': 'lumi_acpartner_electric_power',
        'micloud_statistics': [
            {
                'type': 'stat_day',
                'key': 'powerCost',
                'day': 32,
                'limit': 31,
                'attribute': None,
                'template': 'micloud_statistics_power_cost',
            },
        ],
    },
    'lumi.acpartner.*:electric_power': {
        'state_class': 'measurement',
        'device_class': 'power',
        'unit_of_measurement': 'W',
    },
    'lumi.acpartner.*:power_cost_today': {
        'value_ratio': 0.1,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'lumi.acpartner.*:power_cost_month': {
        'value_ratio': 0.1,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'lumi.ctrl_neutral1.*': {
        'cloud_delay_update': 10,
    },
    'lumi.ctrl_neutral2.*': {
        'cloud_delay_update': 10,
    },
    'lumi.motion.bmgl01': {
        'use_ble_object': True,
    },
    'lumi.motion.*': {
        'interval_seconds': 15,
        'motion_timeout': 60,
    },
    'lumi.sensor_motion.*': {
        'interval_seconds': 15,
        'motion_timeout': 60,
    },
    'lumi.sensor_magnet.*': {
        'interval_seconds': 15,
    },
    'lumi.sensor_wleak.*': {
        'time_start_offset': -86400 * 365,
    },
    'lumi.switch.*': {
        'cloud_delay_update': 10,
    },
    'miaomiaoce.sensor_ht.t1': {
        'miot_mapping': {
            'temperature-2-1': {'siid': 2, 'piid': 1},
            'relative_humidity-2-2': {'siid': 2, 'piid': 2},
            # 'battery.battery_level': {'siid': 3, 'piid': 1},  # -704002000
        },
    },
    'midr.rv_mirror.*': {
        'miio_cloud_props': 'Status,Position',
        'miio_cloud_props_template': 'midr_rv_mirror_cloud_props',
    },
    'mxiang.cateye.*': {
        'miio_cloud_props': 'battery_level,is_can_open_video',
        'miio_cloud_records': 'event.human_visit_details:1',
        'miio_cloud_props_template': 'mxiang_cateye_cloud_props',
        'miio_event_human_visit_details_template': 'mxiang_cateye_human_visit_details',
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
    'yeelink.switch.sw1': {
        'miot_mapping': {
            'switch1.on':          {'siid': 2, 'piid': 1},
            'switch1.default':     {'siid': 2, 'piid': 2},
            'switch1.off_delay':   {'siid': 2, 'piid': 3},
            'switch2.on':          {'siid': 3, 'piid': 1},
            'switch2.default':     {'siid': 3, 'piid': 2},
            'switch2.off_delay':   {'siid': 3, 'piid': 3},
            'extension.interlock': {'siid': 4, 'piid': 1},
            'extension.flash':     {'siid': 4, 'piid': 2},
            'extension.rc_list':   {'siid': 4, 'piid': 3},
        },
    },
    'zimi.plug.zncz01': {
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'micloud_statistics': [
            {
                'type': 'stat_day_v3',
                'key': '3.2',
                'day': 32,
                'limit': 31,
                'attribute': None,
                'template': 'micloud_statistics_power_cost',
            },
        ],
    },
    'zimi.plug.*:electric_power': {
        'value_ratio': 0.01,
        'state_class': 'measurement',
        'device_class': 'power',
        'unit_of_measurement': 'W',
    },
    'zimi.plug.*:power_cost_today': {
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'zimi.plug.*:power_cost_month': {
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'zimi.powerstrip.v2': {
        'sensor_attributes': 'electric_power,store.powerCost:today,store.powerCost:month',
        'sensor_miio_commands': {
            'get_prop': {
                'params': ['power_consume_rate'],
                'values': ['electric_power'],
            },
        },
        'miio_cloud_records': 'store.powerCost:31:day',
        'miio_store_powerCost_template': "{%- set val = (result.0 | default({})).get('value','[0]') %}"
                                         "{%- set day = now().day %}"
                                         "{%- set vls = (val | from_json)[0-day:] %}"
                                         "{%- set dat = namespace(today=0,month=0) %}"
                                         "{%- for v in vls %}"
                                         "{%-   set v = (v | string).split(',') %}"
                                         "{%-   if v[0] | default(0) | int(0) > 86400 %}"
                                         "{%-     set dat.today = v[1] | default(0) | round(3) %}"
                                         "{%-     set dat.month = dat.month + dat.today %}"
                                         "{%-   endif %}"
                                         "{%- endfor %}"
                                         "{{ {"
                                         "'today': dat.today,"
                                         "'month': dat.month | round(3),"
                                         "} }}",
    },
    'zimi.powerstrip.*:electric_power': {
        'state_class': 'measurement',
        'device_class': 'power',
        'unit_of_measurement': 'W',
    },
    'zimi.powerstrip.*:store.powerCost:today': {
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'zimi.powerstrip.*:store.powerCost:month': {
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },

    '*.airer.*': {
        'sensor_properties': 'left_time',
        'switch_properties': 'dryer,uv',
        'fan_properties': 'drying_level',
    },
    '*.camera.*': {
        'miot_cloud_action': True,
    },
    '*.cateye.*': {
        'use_motion_stream': True,
    },
    '*.cooker.*': {
        'sensor_properties': 'temperature,left_time',
        'switch_properties': 'cooker.on,auto_keep_warm',
    },
    '*.door.*': {},
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
    '*.s_lamp.*': {
        'sensor_properties': 'left_time',
        'switch_properties': 'uv,radar_on,lighting.on',
        'number_properties': 'target_time',
    },
    '*.walkingpad.*': {
        'sensor_properties': 'current_distance,current_step_count,current_calorie_consumption,'
                             'left_distance,left_time,working_time',
        'number_properties': 'target_distance,target_time',
        'select_properties': 'mode,speed_level',
    },

}

DEVICE_CUSTOMIZES.update({
    '*.door.*': DEVICE_CUSTOMIZES.get('*.lock.*') or {},
})
