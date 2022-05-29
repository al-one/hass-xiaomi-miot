DEVICE_CUSTOMIZES = {

    'ateai.mosq.dakuo': {
        'switch_properties': 'dakuo_mosq_dispeller.status',
        'select_properties': 'workmode',
    },

    'bofu.curtain.bfmh': {
        'select_properties': 'motor_control',
    },

    'careli.fryer.*': {
        'button_actions': 'start_cook,pause,cancel_cooking',
        'exclude_miot_services': 'custom',
    },
    'cgllc.airm.cgdn1': {
        'exclude_miot_services': 'mac,settings',
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
    'chunmi.ysj.*': {
        'sensor_properties': 'water_dispenser.status,filter_life_level,home_temp,clean_precent',
        'switch_properties': 'winter_mode,cold_keep,cup_check',
        'select_properties': 'lock_temp,cold_mode,default_mode',
        'number_properties': 'boil_point,oled_close_time',
    },
    'cuco.light.sl4': {
        'switch_properties': 'swich',
        'select_properties': 'scene.mode,change_type',
        'number_properties': 'change_speed',
    },
    'cuco.light.sl4a': {
        'switch_properties': 'swich',
        'select_properties': 'scene.mode,change_type',
        'number_properties': 'change_speed',
    },
    'cuco.plug.co1': {
        'exclude_miot_services': 'setting,cycle',
    },
    'cuco.plug.cp1': {
        'chunk_properties': 1,
        'exclude_miot_services': 'indicator_light',
    },
    'cuco.plug.cp1m': {
        'chunk_properties': 1,
        'sensor_properties': 'power,voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '2.2',
    },
    'cuco.plug.cp2': {
        'chunk_properties': 1,
        'sensor_properties': 'power,voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '2.2',
        'miot_mapping': {
            'switch.on': {'siid': 2, 'piid': 1},
            'switch.electric_current': {'siid': 2, 'piid': 4},
            'switch.countdown_time': {'siid': 2, 'piid': 5},
            'switch.power': {'siid': 3, 'piid': 2},
            'indicator_light.on': {'siid': 3, 'piid': 1},
        },
    },
    'cuco.plug.cp2a': {
        'main_miot_services': 'switch-2',
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
    'cuco.plug.cp5pro:voltage': {
        'value_ratio': 1,
    },
    'cuco.plug.sp5': {
        'main_miot_services': 'switch-2',
        'exclude_miot_services': 'custome,physical_controls_locked,indicator_light',
    },
    'cuco.plug.*': {
        'main_miot_services': 'switch-2',
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
    'deerma.humidifier.jsq5': {
        'chunk_properties': 4,
    },
    'deerma.humidifier.*': {
        'chunk_properties': 6,
        'exclude_miot_services': 'custom',
    },
    'deye.derh.u20a3': {
        'target_humidity_ratio': 9.0909,
    },
    'dmaker.fan.*': {
        'select_properties': 'horizontal_angle',
        'number_properties': 'off_delay_time',
    },
    'dreame.vacuum.*': {
        'sensor_properties': 'vacuum.status',
        'exclude_miot_services': 'consumable,annoy,remote,time',
    },
    'fawad.airrtc.*': {
        'exclude_miot_services': 'thermostat_vrf',
    },
    'fengmi.projector.*': {
        'auto_cloud': True,
        'number_properties': 'speaker.volume',
    },
    'galime.curtain.*': {
        'auto_position_reverse': True,
        'select_properties': 'speed_control',
    },
    'hfjh.fishbowl.v1': {
        'light_services': 'light',
    },
    'hmpace.bracelet.*': {
        'sensor_properties': 'current_step_count,current_distance',
    },
    'hyd.airer.lyjpro': {
        'cover_position_mapping': {},
    },
    'hyd.airer.*': {
        'switch_properties': 'uv',
        'select_properties': 'mode,dryer',
        'number_properties': 'drying_time',
        'disable_target_position': True,
        'cover_position_mapping': {
            0: 50,
            1: 100,
            2: 0,
        },
    },
    'ijai.vacuum.*': {
        'sensor_properties': 'vacuum.status',
        'exclude_miot_services': 'order',
        'exclude_miot_properties': 'zone_points,restrict_points,target_point',
    },
    'ijomoo.toilet.zs320': {
        'state_property': 'toilet_jomoo.seat_status',
        'binary_sensor_properties': 'seat_ring,cover_plate',
        'sensor_properties': 'fault,work_status',
        'switch_properties': 'flushing,small_flushing',
        'select_properties': 'work_mode,hip_water_gage,woman_water_gage,hip_nozzle_position,woman_nozzle_pos,'
                             'seat_temperature,wind_temperature,water_temperature,auto_mode',
    },
    'leshi.light.wy0b01': {
        'chunk_properties': 1,
        'exclude_miot_services': 'remote,default,scene',
    },
    'leshi.light.wyfan': {
        'chunk_properties': 3,
    },
    'leshow.humidifier.jsq1': {
        'miot_type': 'urn:miot-spec-v2:device:humidifier:0000A00E:leshow-jsq1:2',
        'sensor_properties': 'humidifier.water_level',
        'switch_properties': 'alarm,warm_wind_turn,turn_ovp,dry_turn,turn_off_dry_turn',
        'number_properties': 'screen_brightness,tsms_turn_off',
    },
    'lumi.acpartner.mcn02:electric_power': {
        'value_ratio': 1,
    },
    'lumi.acpartner.mcn04': {
        'chunk_properties': 7,
        'miio_cloud_props': [],
    },
    'lumi.acpartner.*': {
        'sensor_attributes': 'electric_power,power_cost_today,power_cost_month',
        'miio_cloud_props': 'ac_power,load_power',
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
    'lumi.airer.acn01': {
        'select_properties': 'dry_mode',
        'motor_reverse': False,
        'position_reverse': True,
        'target2current_position': True,
    },
    'lumi.ctrl_ln2.aq1': {
        'exclude_miot_services': 'power_consumption',  # issues/426
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
    'lumi.sensor_gas.mcn02': {
        'chunk_properties': 1,
        'sensor_properties': 'status',
        'exclude_miot_services': 'gas_sensor_control',
    },
    'lumi.sensor_motion.*': {
        'interval_seconds': 15,
        'motion_timeout': 60,
    },
    'lumi.sensor_magnet.*': {
        'reverse_state': False,
        'interval_seconds': 15,
    },
    'lumi.sensor_wleak.*': {
        'time_start_offset': -86400 * 365,
    },
    'lumi.switch.*': {
        'cloud_delay_update': 10,
    },
    'mmgg.feeder.petfeeder': {
        'state_property': 'pet_food_left_level',
        'button_actions': 'reset_desiccant_life',
        'sensor_properties': 'feed_today,desiccant_left_time,cleantime',
        'switch_properties': 'feedstatus',
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
    'philips.light.strip3': {
        'switch_properties': 'mitv_rhythm,acousto_optic_rhythm',
        'select_properties': 'rhythm_sensitivity,rhythm_animation',
        'number_properties': 'dvalue,diy_id',
        'button_actions': 'toggle_rhythm',
    },
    'pwzn.light.apple': {
        'light_services': 'light_ct',
        'switch_properties': 'enable',
        'select_properties': 'mode,rgb_order',
        'number_properties': 'numleds,pixel_per_step,fade_delay,step_delay,stair_travel_time',
    },
    'roborock.vacuum.*': {
        'sensor_attributes': 'props:clean_area,props:clean_time',
        'sensor_properties': 'vacuum.status',
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
        'sensor_properties': 'vacuum.status',
    },
    'rockrobo.vacuum.*:props:clean_area': {
        'value_ratio': 0.000001,
        'unit_of_measurement': '㎡',
    },
    'rockrobo.vacuum.*:props:clean_time': {
        'value_ratio': 0.016666,
        'unit_of_measurement': 'min',
    },
    'roidmi.vacuum.*': {
        'exclude_miot_services': 'custom',
    },
    'roome.bhf_light.*': {
        'sensor_attributes': 'temp,currenttemp',
        'select_attributes': 'main_state,main_light,night_light,heat,vent,dry,natural_wind,delay_wind',
    },
    'smith.waterpuri.cxr800': {
        'chunk_properties': 1,
        'state_property': 'chanitex_wp_gs.rsysstate',
        'sensor_properties': 'rwaterconsumption,rfilterwaterlifei,rfilterwaterlifeii,rfilterwaterlifeiii',
    },
    'shuii.humidifier.jsq002': {
        'brightness_for_on': 3,
        'brightness_for_off': 1,
    },
    'suittc.airrtc.wk168': {
        'switch_properties': 'on',
    },
    'viomi.vacuum.*': {
        'sensor_attributes': 'miio.s_area,miio.s_time',
        'sensor_properties': 'vacuum.status,main_brush_life,side_brush_life,hypa_life,mop_life',
    },
    'viomi.vacuum.*:miio.s_area': {
        'unit_of_measurement': '㎡',
    },
    'viomi.vacuum.*:miio.s_time': {
        'unit_of_measurement': 'min',
    },
    'viomi.washer.*': {
        'exclude_miot_services': 'key_press',
    },
    'wise.wifispeaker.x7': {
        'switch_properties': 'key_one,key_two,key_three,key_four,key_five,key_six,key_seven,key_eight,key_nine,'
                             'key_ten,key_eleven,key_twelve,key_thirteen,key_fourteen,key_fifteen,key_sixteen',
    },
    'xiaomi.aircondition.mt6': {
        'exclude_miot_services': 'iot_linkage,machine_state',
    },
    'xiaomi.tv.*': {
        'auto_cloud': True,
        'number_properties': 'speaker.volume',
    },
    'xiaomi.tvbox.*': {
        'auto_cloud': True,
        'number_properties': 'speaker.volume',
    },
    'xiaomi.watch.*': {
        'sensor_properties': 'current_step_count,current_distance',
    },
    'yeelink.bhf_light.v5': {
        'select_properties': 'heat_mode,cold_mode,vent_mode',
    },
    'yeelink.bhf_light.v6': {
        'select_properties': 'heat_mode,cold_mode,vent_mode',
    },
    'yeelink.light.fancl5': {
        'number_properties': 'fan_speed_std,fan_speed_rec,dl_brightness,nl_brightness',
    },
    'yeelink.light.nl1': {
        'use_ble_object': True,
        'motion_timeout': 120,
        'interval_seconds': 15,
        'sensor_attributes': 'no_motion_seconds',
    },
    'yeelink.light.stripa': {
        'chunk_properties': 2,
    },
    'yeelink.light.*': {
        'main_miot_services': 'light-2',
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
    'yunmi.waterpuri.lx5': {
        'number_properties': 'tds_warn_thd',
        'sensor_properties': 'rinse',
        'switch_properties': 'light_mode',
    },
    'yyunyi.wopener.yypy24': {
        'switch_properties': 'motor_reverse',
        'select_properties': 'mode',
        'number_properties': 'speed_level,clamp_strength',
        'target2current_position': True,
    },
    'zhimi.airfresh.*': {
        'switch_properties': 'heater,alarm',
    },
    'zhimi.airpurifier.*': {
        'sensor_properties': 'illumination,motor_speed',
        'number_properties': 'favorite_level,favorite_fan_level',
        # https://github.com/rytilahti/python-miio/blob/31c5d740d403c6f45f1e7e0d4a8a6276684a8ecd/miio/integrations/airpurifier/zhimi/airpurifier_miot.py#L13
        'exclude_miot_services': 'button,motor_speed,filter_time,rfid,others',
        'exclude_miot_properties': 'average_aqi_cnt,aqi_zone,sensor_state,aqi_goodh,aqi_runstate,aqi_state',
    },
    'zhimi.airpurifier.za1': {
        'brightness_for_on': 0,
        'brightness_for_off': 2,
    },
    'zhimi.airpurifier.za2': {
        'brightness_for_on': 0,
        'brightness_for_off': 2,
    },
    'zhimi.heater.nb1': {
        'brightness_for_on': 0,
        'brightness_for_off': 2,
    },
    'zhimi.humidifier.*': {
        'sensor_properties': 'water_level,actual_speed',
        'switch_properties': 'alarm,other.clean,humidifier.dry',
        'select_properties': 'screen.brightness',
        'number_properties': 'speed_level',
    },
    'zimi.mosq.*': {
        'light_services': 'light_indicator',
    },
    'zimi.plug.zncz01': {
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'sensor_properties': 'electric_power',
        'switch_properties': 'power_protect.on,full_power_off',
        'select_properties': 'enable_upload_power',
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
    'zinguo.switch.b5m': {
        'main_miot_services': 'switch-2',
        'sensor_attributes': 'temperature',
        'switch_properties': 'heating,blow,ventilation',
        'select_properties': 'link',
        'light_services': 'light',
    },

    '*.aircondition.*': {
        'fan_services': 'air_fresh',
    },
    '*.airer.*': {
        'position_reverse': True,
        'sensor_properties': 'left_time',
        'switch_properties': 'dryer,uv',
        'fan_properties': 'drying_level',
    },
    '*.airrtc.*': {
        'switch_properties': 'air_conditioner.on',
    },
    '*.airpurifier.*': {
        'switch_properties': 'air_purifier.on',
        'sensor_properties': 'relative_humidity,pm2_5_density,temperature,filter_life_level',
    },
    '*.bhf_light.*': {
        'main_miot_services': 'ptc_bath_heater',
    },
    '*.blanket.*': {
        'select_properties': 'mode,heat_level,water_level',
    },
    '*.camera.*': {
        'miot_cloud_action': True,
    },
    '*.cateye.*': {
        'use_motion_stream': True,
    },
    '*.cooker.*': {
        'sensor_properties': 'temperature,left_time',
        'switch_properties': 'cooker.on',
        'button_actions': 'start_cook,pause,cancel_cooking',
    },
    '*.desk.*': {
        'button_properties': 'motor_control,reset',
        'switch_properties': 'on',
        'select_properties': 'mode,desk_control',
        'number_properties': 'altitude,target_height,stand_height,sit_height,target_position',
    },
    '*.door.*': {},
    '*.f_washer.*': {
        'sensor_properties': 'left_time,water',
        'switch_properties': 'on',
        'number_select_properties': 'wash_mode,wash_time,target_water_level,water_level',
    },
    '*.fan.*': {
        'number_properties': 'off_delay_time',
        'switch_properties': 'fan_init_power_opt',
    },
    '*.fishbowl.*': {
        'sensor_properties': 'temperature',
        'switch_properties': 'water_pump,automatic_feeding,heating',
        'number_properties': 'target_temperature,pump_flux,target_feeding_measure,'
                             'ambient_light_custom.stream,ambient_light_custom.speed',
    },
    '*.heater.*': {
        'switch_properties': 'heater.on',
        'number_properties': 'countdown_time',
    },
    '*.ihcooker.*': {
        'sensor_properties': 'temperature,left_time',
        'button_actions': 'start_cook,pause,cancel_cooking',
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
    '*.mosq.*': {
        'sensor_properties': 'repellent_left_level,liquid_left',
        'select_properties': 'mode',
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
    '*.steriliser.*': {
        'sensor_properties': 'left_time,working_time',
        'switch_properties': 'on,engaged',
        'select_properties': 'mode',
        'number_properties': 'target_time',
    },
    '*.toothbrush.*': {
        'miio_cloud_props': 'event.16',
        'miio_cloud_props_template': 'ble_toothbrush_events',
        'sensor_attributes': 'event,score,timestamp',
    },
    '*.tow_w.*': {
        'sensor_properties': 'temperature',
        'select_properties': 'mode',
        'number_properties': 'target_temperature',
    },
    '*.treadmill.*': {
        'button_actions': 'start_work,pause,stop_working',
        'sensor_properties': 'current_distance,current_step_count,current_calorie_consumption,'
                             'left_distance,left_time,working_time',
        'number_properties': 'target_distance,target_time',
        'select_properties': 'mode',
        'number_select_properties': 'speed_level',
    },
    '*.walkingpad.*': {
        'sensor_properties': 'current_distance,current_step_count,current_calorie_consumption,'
                             'left_distance,left_time,working_time',
        'number_properties': 'target_distance,target_time',
        'select_properties': 'mode',
        'number_select_properties': 'speed_level',
    },
    '*.washer.*': {
        'button_actions': 'start_wash,pause',
    },
    '*.waterheater.*': {
        'sensor_properties': 'water_velocity',
        'switch_properties': 'water_heater.on,preheating,cruise_press',
    },

}

DEVICE_CUSTOMIZES.update({
    '*.door.*': DEVICE_CUSTOMIZES.get('*.lock.*') or {},
})
