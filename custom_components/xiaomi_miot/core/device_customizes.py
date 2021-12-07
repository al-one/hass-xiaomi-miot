DEVICE_CUSTOMIZES = {

    'cgllc.airm.cgdn1': {
        'chunk_properties': 9,
    },
    'chuangmi.camera.v6': {
        'use_alarm_playlist': True,
    },
    'chuangmi.plug.212a01': {
        'chunk_properties': 7,
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': 'prop.5.1',
    },
    'chuangmi.plug.v3': {
        'sensor_attributes': 'electric_power,prop_cal_day.power_cost:today,prop_cal_day.power_cost:month',
        'miio_commands': {
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
        'value_ratio': 0.000001,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'chuangmi.plug.*:power_cost_month': {
        'value_ratio': 0.000001,
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
        'sensor_properties': 'power,voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '2.2',
    },
    'cuco.plug.cp2': {
        'sensor_properties': 'power,voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '2.2',
    },
    'cuco.plug.cp4': {
        'sensor_properties': 'power,voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '2.2',
    },
    'cuco.plug.cp4am': {
        'sensor_properties': 'power,voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '2.2',
    },
    'cuco.plug.cp4m': {
        'sensor_properties': 'power,voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '2.2',
    },
    'cuco.plug.cp5pro': {
        'sensor_properties': 'voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '10.1',
    },
    'cuco.plug.cp5pro:power_cost_today': {
        'value_ratio': 1,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'cuco.plug.cp5pro:power_cost_month': {
        'value_ratio': 1,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'cuco.plug.*:electric_current': {
        'state_class': 'measurement',
        'device_class': 'current',
        'unit_of_measurement': 'mA',
    },
    'cuco.plug.*:power': {
        'value_ratio': 0.1,
        'state_class': 'measurement',
        'device_class': 'power',
        'unit_of_measurement': 'W',
    },
    'cuco.plug.*:power_cost_today': {
        'value_ratio': 0.001,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'cuco.plug.*:power_cost_month': {
        'value_ratio': 0.001,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'cuco.plug.*:voltage': {
        'value_ratio': 0.1,
        'state_class': 'measurement',
        'device_class': 'voltage',
        'unit_of_measurement': 'V',
    },
    'deerma.humidifier.jsq3': {
        'chunk_properties': 6,
    },
    'hmpace.bracelet.*': {
        'sensor_properties': 'current_step_count,current_distance',
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
        'stat_power_cost_type': 'stat_day',
        'stat_power_cost_key': 'powerCost',
    },
    'lumi.acpartner.*:electric_power': {
        'state_class': 'measurement',
        'device_class': 'power',
        'unit_of_measurement': 'W',
    },
    'lumi.acpartner.*:power_cost_today': {
        'value_ratio': 0.001,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'lumi.acpartner.*:power_cost_month': {
        'value_ratio': 0.001,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'lumi.aircondition.acn05': {
        'sensor_attributes': 'power_cost_today',
        'stat_power_cost_key': '12.1',
    },
    'lumi.aircondition.*:electric_power': {
        'state_class': 'measurement',
        'device_class': 'power',
        'unit_of_measurement': 'W',
    },
    'lumi.aircondition.*:power_consumption': {
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'lumi.aircondition.*:power_cost_today': {
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'lumi.aircondition.*:power_cost_month': {
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
        'sensor_attributes': 'trigger_at',
        'binary_sensor_attributes': 'light_strong',
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
    'mmgg.feeder.petfeeder': {
        'sensor_attributes': 'feed_today',
        'miio_commands': {
            'getprops': [
                'food_status', 'feed_plan', 'door_result', 'feed_today', 'clean_days', 'outlet_status',
                'dryer_days', 'weight_level', 'wifi_led', 'key_lock', 'country_code',
            ],
            # 'getfeedplan1': [],
            # 'getfeedplan2': [],
        },
        'miot_local_mapping': {
            'feeding.measure': {'siid': 2, 'piid': 1},
        },
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
    'roborock.vacuum.*': {
        'sensor_attributes': 'props:clean_area,props:clean_time',
        'miio_commands': {
            'get_status': ['props'],
            'get_consumable': ['consumables'],
        },
    },
    'roborock.vacuum.*:props:clean_area': {
        'value_ratio': 0.000001,
        'unit_of_measurement': '㎡',
    },
    'roborock.vacuum.*:props:clean_time': {
        'value_ratio': 0.016666,
        'unit_of_measurement': 'min',
    },
    'rockrobo.vacuum.*': {
        'sensor_attributes': 'props:clean_area,props:clean_time',
        'miio_commands': {
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
    'suittc.airrtc.wk168': {
        'switch_properties': 'on',
    },
    'viomi.vacuum.*': {
        'sensor_attributes': 'miio.s_area,miio.s_time',
        'miio_properties': 'run_state,mode,err_state,battary_life,box_type,mop_type,s_time,s_area,'
                           'suction_grade,water_grade,remember_map,has_map,is_mop,has_newmap',
    },
    'viomi.waterheater.e1': {
        'miio_properties': 'washStatus,velocity,waterTemp,targetTemp,errStatus,'
                           'hotWater,needClean,modeType,appointStart,appointEnd',
    },
    'wise.wifispeaker.x7': {
        'switch_properties': 'key_one,key_two,key_three,key_four,key_five,key_six,key_seven,key_eight,key_nine,'
                             'key_ten,key_eleven,key_twelve,key_thirteen,key_fourteen,key_fifteen,key_sixteen',
    },
    'xiaomi.tv.*': {
        'number_properties': 'speaker.volume',
    },
    'xiaomi.watch.*': {
        'sensor_properties': 'current_step_count,current_distance',
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
        'stat_power_cost_key': '3.2',
    },
    'zimi.plug.*:electric_power': {
        'value_ratio': 0.01,
        'state_class': 'measurement',
        'device_class': 'power',
        'unit_of_measurement': 'W',
    },
    'zimi.plug.*:power_cost_today': {
        'value_ratio': 0.01,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'zimi.plug.*:power_cost_month': {
        'value_ratio': 0.01,
        'state_class': 'total_increasing',
        'device_class': 'energy',
        'unit_of_measurement': 'kWh',
    },
    'zimi.powerstrip.v2': {
        'sensor_attributes': 'electric_power,store.powerCost:today,store.powerCost:month',
        'miio_commands': {
            'get_prop': {
                'params': ['power_consume_rate'],
                'values': ['electric_power'],
            },
        },
        'miio_cloud_records': 'store.powerCost:31:day',
        'miio_store_powerCost_template': 'zimi_powerstrip_v2_power_cost',
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
    '*.airrtc.*': {
        'switch_properties': 'air_conditioner.on',
    },
    '*.airpurifier.*': {
        'switch_properties': 'air_purifier.on',
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
    '*.fan.*': {
        'number_properties': 'off_delay_time',
        'switch_properties': 'fan_init_power_opt',
    },
    '*.heater.*': {
        'switch_properties': 'heater.on',
        'number_properties': 'countdown_time',
    },
    '*.light.*': {
        'number_properties': 'off_delay_time',
        'switch_properties': 'init_power_opt,fan_init_power_opt',
    },
    '*.lock.*': {
        'sensor_attributes': 'door_state,lock_action,lock_key_id,timestamp',
        'binary_sensor_attributes': 'armed_state',
        'miio_cloud_props': 'event.6,event.7,event.8,event.11',
        'miio_cloud_props_template': 'ble_lock_events',
    },
    '*.lock.*:timestamp': {
        'device_class': 'timestamp',
    },
    '*.microwave.*': {
        'sensor_properties': 'left_time,heat_level,cook_time',
    },
    '*.motion.*:light_strong': {
        'device_class': 'light',
    },
    '*.motion.*:trigger_at': {
        'device_class': 'timestamp',
    },
    '*.oven.*': {
        'sensor_properties': 'temperature,left_time,cook_time,working_time',
        'number_properties': 'target_temperature',
        'switch_properties': 'oven.on',
    },
    '*.s_lamp.*': {
        'sensor_properties': 'left_time',
        'switch_properties': 'uv,radar_on,lighting.on',
        'number_properties': 'target_time',
    },
    '*.sensor_smoke.*': {
        'binary_sensor_attributes': 'smoke_status',
        'miio_cloud_props': '4117',
        'miio_cloud_props_template': 'ble_sensor_smoke',
    },
    '*.sensor_smoke.*:smoke_status': {
        'device_class': 'smoke',
    },
    '*.walkingpad.*': {
        'sensor_properties': 'current_distance,current_step_count,current_calorie_consumption,'
                             'left_distance,left_time,working_time',
        'number_properties': 'target_distance,target_time',
        'select_properties': 'mode',
        'number_select_properties': 'speed_level',
    },

}

DEVICE_CUSTOMIZES.update({
    '*.door.*': DEVICE_CUSTOMIZES.get('*.lock.*') or {},
})
