from .converters import *

CHUNK_1 = {
    'chunk_properties': 1,
}

ENERGY_KWH = {
    'state_class': 'total_increasing',
    'device_class': 'energy',
    'unit_of_measurement': 'kWh',
}

DEVICE_CUSTOMIZES = {
    '090615.aircondition.ktf': {
        'current_temp_property': 'setmode.roomtemp',
    },
    '090615.curtain.wsdml1': {
        'switch_properties': 'on,wake_up_mode',
        'select_properties': 'curtain-2.mode-5,default_open_position',
        'number_properties': 'curtain-2.mode-10,default_close_position',
    },
    '090615.curtain.*': {
        'auto_cloud': True,
        'chunk_properties': 1,
        'exclude_miot_properties': 'motor_control',
    },
    '090615.plug.plus01': {
        'chunk_properties': 1,
        'exclude_miot_properties': 'fault,mode,name,status,temperature',
    },

    'aice.motor.kzmu3': {
        'switch_properties': 'on',
        'button_properties': 'motor_control',
    },
    'aimore.light.cw3201': {
        'switch_properties': 'flex_switch',
        'select_properties': 'default_power_on_state',
        'number_properties': 'jianbian,countdown',
    },
    'ainice.motion.bt': {
        'miot_type': 'urn:miot-spec-v2:device:motion-sensor:0000A014:ainice-bt:2',
        'state_property': 'motion_sensor.motion_status',
        'interval_seconds': 5,
        'binary_sensor_properties': 'online_status,ble_near,bt_status',
        'sensor_properties': 'motion_state',
        'switch_properties': 'gesture_enabled,gesture_switch',
        'select_properties': 'bt_level',
        'number_properties': 'offline_timeout,motion_timeout,online_level,offline_level,online_duration,'
                             'offline_duration,ble_in_threshold,ble_out_threshold,ble_far_timeout',
    },
    'ainice.sensor_occupy.3b': {
        'state_property': 'occupancy_sensor.current_occupied',
        'interval_seconds': 90,
        'parallel_updates': 1,
        'binary_sensor_properties': 'current_occupied,a_occupied,b_occupied,c_occupied,d_occupied,e_occupied',
        'sensor_properties': 'total_occupied,illumination',
        'switch_properties': 'radar_switch,count_switch',
        'select_properties': 'map_index,traction',
        'button_actions': 'reboot',
        'select_actions': 'reset_target',
        'exclude_miot_properties': 'zone_param,target_param,duration_param,time_param,'
                                   'map_read,map_write,radar_duration',
        'chunk_coordinators': [
            {'interval': 3, 'props': 'current_occupied,a_occupied,b_occupied,c_occupied,d_occupied,e_occupied'},
            {'interval': 5, 'props': 'total_occupied,illumination'},
        ],
    },
    'ainice.sensor_occupy.3b:current_occupied': {
        'with_properties': 'has_someone_duration,no_one_duration,total_occupied',
        'device_class': 'occupancy',
    },
    'ainice.sensor_occupy.3b:a_occupied': {
        'with_properties': 'a_someone_duration,a_noone_duration',
        'device_class': 'occupancy',
    },
    'ainice.sensor_occupy.3b:b_occupied': {
        'with_properties': 'b_someone_duration,b_noone_duration',
        'device_class': 'occupancy',
    },
    'ainice.sensor_occupy.3b:c_occupied': {
        'with_properties': 'c_someone_duration,c_noone_duration',
        'device_class': 'occupancy',
    },
    'ainice.sensor_occupy.3b:d_occupied': {
        'with_properties': 'd_someone_duration,d_noone_duration',
        'device_class': 'occupancy',
    },
    'ainice.sensor_occupy.3b:e_occupied': {
        'with_properties': 'e_someone_duration,e_noone_duration',
        'device_class': 'occupancy',
    },
    'ainice.sensor_occupy.bt': {
        'interval_seconds': 60,
        'parallel_updates': 1,
        'switch_properties': 'indicator_switch,bt_pair_switch',
        'select_properties': 'bt_power_level',
        'scanner_properties': 'online_status',
        'select_actions': 'send_magic_package',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'online_status'},
        ],
    },
    'ainice.sensor_occupy.bt:online_status': {
        'with_properties': 'online_duration,offline_duration,offline_interval,online_mode,bt_capture_mode,binding_info',
    },
    'ainice.sensor_occupy.pr': {
        'state_property': 'occupancy_sensor.occupancy_status',
        'interval_seconds': 10,
        'sensor_properties': 'no_one_duration,has_someone_duration,zone_param',
        'switch_properties': 'radar_switch,bluetooth_switch,count_switch',
        'select_properties': 'sensitivity,direction,position',
        'number_properties': 'hold_duration',
        'button_actions': 'reboot',
        'exclude_miot_properties': 'cmd_request,cmd_response',
    },
    'air.fan.ca23ad9': {
        'unreadable_properties': True,  # issues/1097
    },
    'ateai.mosq.dakuo': {
        'switch_properties': 'dakuo_mosq_dispeller.status',
        'select_properties': 'workmode',
    },
    'aupu.bhf_light.s368m': {
        'ignore_fan_switch': True,
        'switch_properties': 'fan_control.on,onoff.on,blow,ventilation,dryer',
        'select_properties': 'mode',
    },

    'babai.curtain.190812': CHUNK_1,
    'babai.curtain.at5810': CHUNK_1,
    'babai.curtain.bb82cb': CHUNK_1,
    'babai.curtain.bb82mj': CHUNK_1,
    'babai.curtain.cmb5': CHUNK_1,
    'babai.curtain.lsxf83': CHUNK_1,
    'babai.curtain.m515e': CHUNK_1,
    'babai.curtain.mtx850': CHUNK_1,
    'babai.curtain.yilc3': CHUNK_1,
    'bkrobo.chair.*': {
        'sensor_properties': 'sit_state,power_state,recharge',
        'switch_properties': 'on,setcheck',
        'select_properties': 'fillair_in_waist,alarm_set,model',
        'number_properties': 'preferred_waist,pressure_default',
    },
    'bofu.curtain.bfmh': {
        'select_properties': 'motor_control',
    },

    'careli.fryer.*': {
        'interval_seconds': 120,
        'button_actions': 'air_fryer.start_cook,pause,cancel_cooking,resume_cook',
        'sensor_properties': 'status,fault,left_time,appoint_time_left',
        'switch_properties': 'auto_keep_warm,current_keep_warm,preheat,turn_pot_cfg,turn_pot_config',
        'select_properties': 'mode,food_quanty,preheat_switch,turn_pot,texture,target_cooking_measure',
        'number_properties': 'target_time,target_temperature,appoint_time,reservation_left_time,cooking_weight',
        'exclude_miot_properties': 'recipe_id,recipe_name,recipe_sync',
        'chunk_coordinators': [
            {'interval': 20, 'props': 'status,target_time,target_temperature,left_time'},
            {'interval': 35, 'props': 'fault,mode,appoint_time,reservation_left_time'},
        ],
    },
    'cgllc.airm.cgdn1': {
        'exclude_miot_services': 'mac,settings',
    },
    'cgllc.airm.cgdn1:voltage': {
        'value_ratio': 0.001,
        'state_class': 'measurement',
        'device_class': 'voltage',
        'unit_of_measurement': 'V',
    },
    'cgllc.airm.cgd1st': {
        'exclude_miot_services': 'mac,settings',
    },
    'cgllc.airm.cgd1st:voltage': {
        'value_ratio': 0.001,
        'state_class': 'measurement',
        'device_class': 'voltage',
        'unit_of_measurement': 'V',
    },
    'cgllc.airm.cgs2': {
        'sensor_properties': 'noise_decibel',
    },
    'cgllc.motion.cgpr1': {
        'sensor_properties': 'illumination,no_motion_duration',
    },
    'chuangmi.camera.051a01': {
        'switch_properties': 'on,time_watermark,motion_tracking,motion_detection,wdr_mode,glimmer_full_color,'
                             'face_switch,babycry_switch,pet_switch,gesture_switch,cruise_switch,smart_care_switch,'
                             'key_call_switch',
    },
    'chuangmi.camera.v6': {
        'use_alarm_playlist': True,
    },
    'chuangmi.plug.212a01': {
        'chunk_properties': 7,
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': 'prop.5.1',
    },
    'chuangmi.plug.212a01:electric-current': {
        'unit_of_measurement': 'mA',
    },
    'chuangmi.plug.212a01:voltage': {
        'unit_of_measurement': 'V',
    },
    'chuangmi.plug.v1': {
        'miot_type': 'urn:miot-spec-v2:device:outlet:0000A002:chuangmi-v1:1',
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
        **ENERGY_KWH,
        'value_ratio': 0.001,
    },
    'chuangmi.plug.*:power_cost_today': {
        **ENERGY_KWH,
        'value_ratio': 0.000001,
    },
    'chuangmi.plug.*:power_cost_month': {
        **ENERGY_KWH,
        'value_ratio': 0.000001,
    },
    'chuangmi.plug.*:prop_cal_day.power_cost:today': {
        **ENERGY_KWH,
        'value_ratio': 0.001,
    },
    'chuangmi.plug.*:prop_cal_day.power_cost:month': {
        **ENERGY_KWH,
        'value_ratio': 0.001,
    },
    'chunmi.ihcooker.v2': {
        'sensor_properties': 'left_time,working_time,temperature,target_temperature,fire_gears,phase,'
                             'cook_time,appoint_time,pause_time,step_time,error_code,recpe_type',
        'switch_properties': 'induction_cooker.on,buzzer_mark',
        'number_properties': 'heat_level',
        'button_actions': 'cancel_cooking,pause',
        'select_actions': 'start_cook',
    },
    'chunmi.health_pot.a1': {
        'select_actions': 'start_cook',
    },
    'chunmi.health_pot.cmpa1': {
        'select_actions': 'start_cook',
    },
    'chunmi.health_pot.zwza1': {
        'select_actions': 'start_cook',
    },
    'chunmi.microwave.n23l01': {
        'button_actions': 'pause',
    },
    'chunmi.ysj.*': {
        'sensor_properties': 'water_dispenser.status,filter_life_level,home_temp,clean_precent',
        'switch_properties': 'winter_mode,cold_keep,cup_check',
        'select_properties': 'lock_temp,cold_mode,default_mode',
        'number_properties': 'boil_point,oled_close_time',
    },
    'cubee.airrtc.*': {
        **CHUNK_1,
        'switch_properties': 'childlock',
        'select_properties': 'tempactivate,tempcomp',
        'exclude_miot_properties': 'fault,sensortype,maxsettemp,minsettemp',
    },
    'cuco.acpartner.cp6': {
        'switch_properties': 'air_conditioner.on',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '7.1',
    },
    'cuco.acpartner.cp6:power_cost_today': ENERGY_KWH,
    'cuco.acpartner.cp6:power_cost_month': ENERGY_KWH,
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
        **CHUNK_1,
        'exclude_miot_services': 'setting,cycle',
    },
    'cuco.plug.cp1': {
        **CHUNK_1,
        'exclude_miot_services': 'indicator_light',
    },
    'cuco.plug.cp1d': {
        **CHUNK_1,
        'exclude_miot_services': 'indicator_light',
    },
    'cuco.plug.cp1m': {
        **CHUNK_1,
        'exclude_miot_services': 'setting,cyc',  # issues/836
        'exclude_miot_properties': 'power_consumption,voltage,electric_current',
        'sensor_properties': 'power,voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '2.2',
    },
    'cuco.plug.cp1m:power_cost_today': {'value_ratio': 0.001},
    'cuco.plug.cp1m:power_cost_month': {'value_ratio': 0.001},
    'cuco.plug.cp1md': {
        **CHUNK_1,
        'sensor_properties': 'power,voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '2.2',
        'miot_mapping': {
            'switch.on': {'siid': 2, 'piid': 1},
            'switch.voltage': {'siid': 2, 'piid': 3},
            'switch.electric_current': {'siid': 2, 'piid': 4},
            'switch.power': {'siid': 4, 'piid': 2},
            'physical_controls_locked': {'siid': 6, 'piid': 1},
        },
    },
    'cuco.plug.cp1md:power': {
        'value_ratio': 1,
    },
    'cuco.plug.cp1md:power_cost_today': {'value_ratio': 0.001},
    'cuco.plug.cp1md:power_cost_month': {'value_ratio': 0.001},
    'cuco.plug.cp2': {
        **CHUNK_1,
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
    'cuco.plug.cp2:power_cost_today': {'value_ratio': 0.01},
    'cuco.plug.cp2:power_cost_month': {'value_ratio': 0.01},
    'cuco.plug.cp2a': {
        **CHUNK_1,
        'miot_type': 'urn:miot-spec-v2:device:outlet:0000A002:cuco-cp2a:2',
    },
    'cuco.plug.cp2d': {
        **CHUNK_1,
        'exclude_miot_services': 'indicator_light,physical_controls_locked,other_setting',
        'exclude_miot_properties': 'power_consumption,electric_current,voltage',
        'sensor_properties': 'electric_power',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_type': 'stat_day_v3',
        'stat_power_cost_key': '3.1',
    },
    'cuco.plug.cp2d:power_cost_today': {'value_ratio': 0.01},
    'cuco.plug.cp2d:power_cost_month': {'value_ratio': 0.01},
    'cuco.plug.cp4': {
        'sensor_properties': 'power,voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '2.2',
    },
    'cuco.plug.cp4:power_cost_today': {'value_ratio': 0.001},
    'cuco.plug.cp4:power_cost_month': {'value_ratio': 0.001},
    'cuco.plug.cp4am': {
        'sensor_properties': 'power,voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '2.2',
    },
    'cuco.plug.cp4am:power_cost_today': {'value_ratio': 0.001},
    'cuco.plug.cp4am:power_cost_month': {'value_ratio': 0.001},
    'cuco.plug.cp4m': {
        'sensor_properties': 'power,voltage,electric_current',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '2.2',
    },
    'cuco.plug.cp4m:power_cost_today': {'value_ratio': 0.001},
    'cuco.plug.cp4m:power_cost_month': {'value_ratio': 0.001},
    'cuco.plug.cp5d': {
        **CHUNK_1,
        'interval_seconds': 120,
        'exclude_miot_services': 'custome',
        'exclude_miot_properties': 'indicator_light.mode,start_time,end_time',
    },
    'cuco.plug.cp5prd': {
        'exclude_miot_services': 'device_setting,use_ele_alert',
        'exclude_miot_properties': 'power_consumption,electric_current,voltage,temperature_high_ai,temperature_high_ci,'
                                   'indicator_light.mode,start_time,end_time,data_values',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '10.1',
    },
    'cuco.plug.cp5prd:power_cost_today': {'value_ratio': 1},
    'cuco.plug.cp5prd:power_cost_month': {'value_ratio': 1},
    'cuco.plug.cp5pro': {
        'exclude_miot_services': 'power_consumption,device_setting,use_ele_alert',  # issues/763
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '10.1',
    },
    'cuco.plug.cp5pro:power_cost_today': {'value_ratio': 1},
    'cuco.plug.cp5pro:power_cost_month': {'value_ratio': 1},
    'cuco.plug.p8amd': {
        'switch_properties': 'usb_switch.on,light,light.mode',
        'select_properties': 'default_power_on_state',
    },
    'cuco.plug.sp5': {
        **CHUNK_1,
        'interval_seconds': 120,
        'exclude_miot_services': 'custome',
        'exclude_miot_properties': 'indicator_light.mode,start_time,end_time',
    },
    'cuco.plug.v2eur': {
        'sensor_properties': 'electric_power',
        'switch_properties': 'charging_protection.on,max_power_limit.on,cycle.status,delay.delay',
        'number_properties': 'charging_protection.power,protect_time,max_power_limit.power',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '11.1',
    },
    'cuco.plug.v2eur:power_cost_today': {'value_ratio': 0.01},
    'cuco.plug.v2eur:power_cost_month': {'value_ratio': 0.01},
    'cuco.plug.v3': {
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '11.1',
    },
    'cuco.plug.v3:electric_power': {'unit_of_measurement': 'W'},
    'cuco.plug.v3:power_cost_today': {'value_ratio': 0.01},
    'cuco.plug.v3:power_cost_month': {'value_ratio': 0.01},
    'cuco.plug.wp5m': {
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '3.1',
        'chunk_properties': 1,
    },
    'cuco.plug.wp5m:electric_power': {'unit_of_measurement': 'W'},
    'cuco.plug.wp5m:power_cost_today': {'value_ratio': 0.01},
    'cuco.plug.wp5m:power_cost_month': {'value_ratio': 0.01},
    'cuco.plug.wp12': {
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '11.1'
    },
    'cuco.plug.wp12:power_cost_today': {'value_ratio': 1},
    'cuco.plug.wp12:power_cost_month': {'value_ratio': 1},
    'cuco.plug.*': {
        'interval_seconds': 60,
        'parallel_updates': 3,
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
    'cuco.plug.*:power_cost_today': ENERGY_KWH,
    'cuco.plug.*:power_cost_month': ENERGY_KWH,
    'cuco.plug.*:voltage': {
        'value_ratio': 0.1,
        'state_class': 'measurement',
        'device_class': 'voltage',
        'unit_of_measurement': 'V',
    },
    'cuco.switch.cs1': CHUNK_1,
    'cuco.switch.cs1d': CHUNK_1,
    'cuco.switch.cs2': CHUNK_1,
    'cuco.switch.cs2d': CHUNK_1,
    'cuco.switch.cs3': CHUNK_1,
    'cuco.switch.cs3d': CHUNK_1,
    'cuco.switch.*': {
        'interval_seconds': 180,
        'sensor_properties': 'temperature',
        'switch_properties': 'setting.switch,switch_main.on',
        'select_properties': 'wireless_switch.on,left_switch,middle_switch,right_switch',
        'configuration_entities': 'setting.switch,left_switch,middle_switch,right_switch,wireless_switch.on',
        'diagnostic_entities': 'temperature',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'switch.on'},
        ],
    },
    'cykj.hood.jyj22': {
        'sensor_properties': 'left_stove_level,right_stove_level,left_stove_timer,right_stove_timer,timer_mode',
        'switch_properties': 'prop.2.9,hood_stove_switch,timer_alert_switch,low_power_alert,pose_recog_switch,'
                             'start_period_notify,pm_fresh_notify,auto_lighton_start,clean_notify,pm_notify_on',
        'select_properties': 'clean_period',
        'number_properties': 'prop.2.5,off_delay_time,start_period_set,pm_thresold,pm_fresh_time,pm_fresh_valueset,'
                             'turn_off_screen',
    },
    'cykj.hood.jyj22:battery': {
        'state_class': '',
    },
    'cykj.hood.jyj22:battery_level': {
        'state_class': '',
    },

    'dawn.toilet.02': {
        'button_actions': 'stop_working,fangai,fanquan,paopaowei,chongshui,tunxi,fuxi,honggan,zijie',
        'switch_properties': 'on,auto_flush,foot_sensing,moistening_wall,auto_clamshell',
        'select_properties': 'target_temperature,washing_strength,nozzle_position,sensing_distance',
    },
    'deerma.humidifier.jsq2w': {
        'exclude_miot_services': None,
    },
    'deerma.humidifier.jsq3': {
        'exclude_miot_services': 'custom',
    },
    'deerma.humidifier.jsq4': {
        'exclude_miot_services': None,
    },
    'deerma.humidifier.jsq5': {
        'chunk_properties': 4,
        'exclude_miot_services': None,
    },
    'deerma.humidifier.jsqs': {
        'exclude_miot_services': None,
        'binary_sensor_properties': 'fault',
        'sensor_properties': 'filter_life_level',
    },
    'deerma.humidifier.*': {
        'chunk_properties': 6,
        'exclude_miot_properties': 'humi_sensor_fault,temp_sensor_fault,overwet_protect,overtop_humidity',
        'binary_sensor_properties': 'water_shortage_fault,the_tank_filed',
        'sensor_properties': 'fault',
        'switch_properties': 'alarm',
    },
    'degree.lunar.smh013': {
        'exclude_miot_properties': 'search_report,set_sleep_time,user_info,user_info_down,set_sleep_time_down,'
                                   'fast_update_switch,linkage_sleepstage,linkage_warning,gen_report,'
                                   'search_report_today',
        'sensor_properties': 'realtime_heart_rate,realtime_breath_rate,realtime_sleepstage',
        'switch_properties': 'fast_update_switch',
    },
    'devcea.light.ls2307': {
        'interval_seconds': 60,
        'exclude_miot_properties': 'update,colorful_set',
        'switch_properties': 'flex_switch,ac_status,power_on_state,custom_sleep_aid,custom_weak_up',
        'select_properties': 'ambient_light.mode',
        'number_properties': 'default_brightness,default_temperature,sleep_aid_time,wake_up_time,'
                             'gradient_duration_on,gradient_duration_of,gradient_duration_aj,ambient_light.color',
    },
    'deye.derh.u20a3': {
        'target_humidity_ratio': 9.0909,
    },
    'dmaker.airfresh.a1': {
        'sensor_properties': 'filter_life_level',
        'switch_properties': 'heater,alarm',
        'select_properties': 'fan_level',
    },
    'dmaker.airfresh.t2017': {
        'sensor_properties': 'filter_life_level',
        'switch_properties': 'heater,screen.on,alarm',
        'select_properties': 'heat_level,fan_level',
    },
    'dmaker.airp.*': {
        'switch_properties': 'air_purifier.on,anion',
        'number_select_properties': 'horizontal_swing_included_angle',
        'button_actions': 'loop_mode',
    },
    'dmaker.airpurifier.f20': {
        'sensor_properties': 'moto_control',
    },
    'dmaker.airpurifier.*': {
        'switch_properties': 'air_purifier.on,screen.on,alarm',
        'number_properties': 'favorite_speed,moto_hz',
    },
    'dmaker.fan.1e': {
        'button_actions': 'toggle_mode,loop_gear',
        'number_properties': 'off_delay_time,speed_level',
    },
    'dmaker.fan.p5': {
        'percentage_property': 'prop.2.6',
    },
    'dmaker.fan.p5c': {
        'percentage_property': 'speed_level',
        'button_actions': 'turn_left,turn_right,toggle_mode,loop_gear',
        'number_properties': 'off_delay_time',
    },
    'dmaker.fan.p11': {
        'percentage_property': 'prop.2.6',  # issues/838
    },
    'dmaker.fan.p15': {
        'percentage_property': 'prop.2.6',
    },
    'dmaker.fan.p23': {
        'percentage_property': 'speed_level',
        'button_actions': 'toggle,toggle_mode,loop_gear',
        'switch_properties': 'on,heating,horizontal_swing,symmetrical_swing,alarm',
        'select_properties': 'fan.mode,swing_lr_manual',
        'number_properties': 'target_temperature,left_angle,right_angle,off_delay_time',
    },
    'dmaker.fan.p28': {
        'switch_properties': 'alarm,horizontal_swing,vertical_swing,swing_all,off_to_center',
        'percentage_property': 'speed_level',
        'button_properties': 'swing_updown_manual,swing_lr_manual,back_to_center,start_left,start_right,start_up,start_down',
    },
    'dmaker.fan.p33': {
        'percentage_property': 'prop.2.6',
        'select_properties': 'motor_control',
        'open_texts': 'LEFT',
        'close_texts': 'RIGHT',
    },
    'dmaker.fan.p45': {
        'percentage_property': 'speed_level',
        'button_actions': 'turn_left,turn_right',
    },
    'dmaker.fan.*': {
        'switch_properties': 'alarm,horizontal_swing,vertical_swing',
        'number_select_properties': 'horizontal_swing_included_angle,horizontal_angle,'
                                    'vertical_swing_included_angle,vertical_angle',
        'number_properties': 'off_delay_time',
    },
    'dmaker.humidifier.p2': {
        'auto_cloud': True,
        'interval_seconds': 90,
        'chunk_coordinators': [
            {'interval': 30, 'props': 'humidifier.on,mode,target_humidity', 'notify': True},
        ],
    },
    'dmaker.humidifier.*': {
        'button_actions': 'loop_mode',
        'sensor_properties': 'fault,water_status,water_level,fan_dry_time',
        'switch_properties': 'over_wet_protect,screen.on',
        'number_properties': 'off_delay_time',
    },
    'dooya.curtain.c1': {
        'chunk_properties': 1,
        'sensor_properties': 'status',
        'switch_properties': 'mode',
    },
    'dooya.curtain.m1': {
        'chunk_properties': 1,
        'sensor_properties': 'status',
        'switch_properties': 'mode,motor_reverse',
    },
    'dooya.curtain.m7': CHUNK_1,
    'dooya.curtain.m7li': CHUNK_1,
    'dooya.curtain.*': {
        'auto_cloud': True,
        'exclude_miot_properties': 'fault',
        'switch_properties': 'motor_reverse',
    },
    'dreame.light.r2229': {
        'sensor_properties': 'interaction_gesture',
        'switch_properties': 'timer_delay_switch,interaction_switch,flow_switch,lighting_switch',
        'select_properties': 'personality',
        'number_properties': 'timer_delay_value',
        'descriptions_for_on': 'On,Opened,Opend',
    },
    'dreame.vacuum.p2008': {
        'miot_type': 'urn:miot-spec-v2:device:vacuum:0000A006:dreame-p2008:2',
    },
    'dreame.vacuum.*': {
        'sensor_properties': 'vacuum.status',
        'exclude_miot_services': 'consumable,annoy,remote,time',
        'exclude_miot_properties': 'delete_timer,clean_info,map_view,frame_info',
    },

    'era.diffuser.ws01': {
        'chunk_properties': 1,
        'select_properties': 'mode,fan_level,scene',
        'number_properties': 'worktime,sleeptime',
    },
    'era.ysj.b65': {
        'sensor_properties': 'status,current_water,filter_life_level',
        'select_properties': 'mode,filter_reset',
        'number_properties': 'out_water_volume,feidian',
    },

    'fawad.aircondition.3010': {
        'chunk_properties': 1,
        'exclude_miot_properties': 'device_info,ontime_dark,offtime_dark,monday_timer,tuesday_timer,wednesday_timer,'
                                   'thursday_timer,friday_timer,saturday_timer,sunday_timer',
        'switch_properties': 'air_conditioner.on,screen_lock_enable,beep_opration_enable,dark_night_display,'
                             'show_tempreture_poff,power_hold,fannostop',
        'select_properties': 'antifreeze_set,tempreture_delta,heat_type',
        'number_properties': 'count_down',
    },
    'fawad.airrtc.40011': {
        'chunk_properties': 1,
        'switch_properties': 'target_temper_eco,target_temper_out,target_temper_in,target_temper_sleep',
        'number_properties': 'hot_switch_status,screen_lock_enable,power_hold,schedule_enable,antifreeze_set',
        'exclude_miot_properties': 'timer_info,monday_timer,tuesday_timer,wednesday_timer,'
                                   'thursday_timer,friday_timer,saturday_timer',
    },
    'fawad.airrtc.*': {
        'exclude_miot_services': 'thermostat_vrf',
    },
    'fengmi.projector.*': {
        'auto_cloud': True,
        'number_properties': 'speaker.volume',
        'text_actions': 'message_router.post',
    },

    'galime.curtain.*': {
        'auto_position_reverse': True,
        'select_properties': 'speed_control',
    },
    'giot.bhf_light.v1ibhw': {
        'sensor_properties': 'custom.status',
        'switch_properties': 'heating,blow,ventilation,dryer,uv,horizontal_swing,night_light_switch',
        'exclude_miot_properties': 'setting,msga,msgb',
    },

    'hfjh.fishbowl.v1': {
        'light_services': 'light',
    },
    'hfjh.fishbowl.v2': {
        'switch_properties': 'water_pump,ledboard_time_switch,feed_time_switch,key_switch',
        'select_properties': 'ledboard_model',
        'number_properties': 'ledboard_brightness,ledboard_sun,ledboard_color,ledboard_stream,ledboard_speed,'
                             'pump_flux,feed_num',
        'select_actions': 'set_feed_single',
        'light_services': 'fish_tank',
        'power_property': 'fish_tank.on',
        'mode_property': 'ledboard_model',
        'brightness_property': 'ledboard_brightness',
        'color_property': 'ledboard_color',
    },
    'hfjh.fishbowl.m100': {
        'light_services': 'light',
        'sensor_properties': 'temperature,water_pump_status,filter_life_level,alarm.alarm',
        'switch_properties': 'water_pump,feed_protect_on,no_disturb,light_status_on,pump_status_on,temperature_warn_on',
        'select_properties': 'pump_flux,light_status_mode,light_status_flow,pump_status_flux,flow_speed_level',
        'number_properties': 'repeat_cycle,light_status_bright,temperature_warn_min,temperature_warn_max',
    },
    'hmpace.bracelet.*': {
        'sensor_properties': 'current_step_count,current_distance',
    },
    'htcx.alarm.dt210': {
        'state_property': 'comm_fault',
        'button_actions': 'reset,clear_e_quantity',
        'binary_sensor_properties': 'over_voltage_alarm,under_voltage_alarm,over_current_alarm,leakage_alarm,'
                                    'live_line_ot_alarm,null_line_ot_alarm',
        'sensor_properties': 'active_power,electric_quantity,voltage,electricity,residual_current,'
                             'live_line_temp,null_line_temp,line_frequency,phase_angle',
        'number_properties': 'overvolt_threshold,undervol_threshold,over_current_thresh,overcurrent_delay,'
                             'residual_current_thr,temp_threshold,data_cycle',
        'switch_properties': 'alarm_shielding,silent_mode,line_exchange',
    },
    'hyd.airer.lyjpro': {
        'position_reverse': True,
        'cover_position_mapping': {},
    },
    'hyd.airer.znlyj5': {
        'cover_position_mapping': {0: 50, 1: 0, 2: 100},
    },
    'hyd.airer.*': {
        'switch_properties': 'uv',
        'select_properties': 'mode,dryer',
        'number_properties': 'drying_time',
        'exclude_miot_properties': 'motor_control',
        'disable_target_position': True,
        'position_reverse': False,
        'cover_position_mapping': {
            0: 50,
            1: 100,
            2: 0,
        },
    },

    'ijai.vacuum.v1': {
        'exclude_miot_services': 'order',
        'exclude_miot_properties': 'zone_points,restrict_points,target_point',
        'sensor_properties': 'vacuum.status,main_brush_life,side_brush_life,hypa_life,mop_life,cleaning_area,'
                             'door_state,cloth_state,cleaning_time',
        'switch_properties': 'vacuum.on,repeat_state,alarm,pet_recognize,dirt_recognize,ai_recognize',
        'select_properties': 'mode,sweep_type,water_state,mop_route',
        'number_properties': 'alarm.volume',
    },
    'ijai.vacuum.v1:cleaning_area': {
        'unit_of_measurement': '㎡',
    },
    'ijai.vacuum.v1:alarm.volume': {
        'unit_of_measurement': ' ',
    },
    'ijai.vacuum.v1:cleaning_time': {
        'unit_of_measurement': 'min',
        'device_class': 'duration',
    },
    'ijai.vacuum.*': {
        'sensor_properties': 'vacuum.status,main_brush_life,side_brush_life,hypa_life,mop_life',
        'switch_properties': 'vacuum.on,repeat_state,alarm',
        'select_properties': 'mode,sweep_type,water_state',
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
    'iot.bed.upone': {
        'select_properties': 'mode,min_control,light_conrtol',
        'number_properties': 'light_bright',
    },
    'iot.plug.jdls1': {
        'chunk_properties': 1,
        'exclude_miot_services': 'indicator_light',
        'exclude_miot_properties': 'power_consumption',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_type': 'stat_day_v3',
        'stat_power_cost_key': '3.1',
    },
    'iot.plug.jdls1:power_cost_today': ENERGY_KWH,
    'iot.plug.jdls1:power_cost_month': ENERGY_KWH,
    'iot.switch.padw2p': {
        'sensor_properties': 'temperature,electric_power,electric_current,voltage',
        'select_properties': 'default_power_on_state',
        'switch_properties': 'screen.on,self_check,leak_switch,voice_switch',
        'number_properties': 'over_electric_set,lack_voltage_set,delay_set,close_temp_set,over_voltage_set,alert_temp_set',
        'stat_power_cost_type': 'stat_day_v3',
        'stat_power_cost_key': '3.1',
        'sensor_attributes': 'power_cost_today,power_cost_month',
    },
    'iot.switch.padw2p:power_cost_today': ENERGY_KWH,
    'iot.switch.padw2p:power_cost_month': ENERGY_KWH,
    'iot.switch.padwb1': {
        'sensor_properties': 'a_electric_current,a_power,a_voltage,a_temp,a_fault,'
                             'b_electric_current,b_power,b_voltage,b_temp,b_fault,'
                             'c_electric_current,c_power,c_voltage,c_temp,c_fault',
        'select_properties': 'default_power_on_state',
        'switch_properties': 'self_check,leak_switch,voice_switch',
        'number_properties': 'over_electric_set,lack_voltage_set,delay_set,close_temp_set,over_voltage_set,alert_temp_set',
        'stat_power_cost_type': 'stat_day_v3',
        'stat_power_cost_key': '3.1',
        'sensor_attributes': 'power_cost_today,power_cost_month',
    },
    'iot.switch.padwb1:power_cost_today': ENERGY_KWH,
    'iot.switch.padwb1:power_cost_month': ENERGY_KWH,
    'isa.camera.hlc7': {
        'select_properties': 'night_shot,recording_mode,detection_sensitivity',
        'switch_properties': 'on,time_watermark,motion_detection',
        'number_properties': 'image_rollover,alarm_interval',
    },
    'isleep.blanket.hs2001': CHUNK_1,
    'isleep.blanket.hs2201': CHUNK_1,
    'isleep.blanket.hs2205': CHUNK_1,
    'isleep.blanket.hs2401': CHUNK_1,
    'isleep.blanket.*': {
        'sensor_properties': 'fault,temperature,water_level',
        'select_properties': 'mode,sleep_level',
        'switch_properties': 'low_temperature,screen_switch,key_tone,automatic_shutdown,fast_heating',
        'number_properties': 'target_temperature,countdown_time',
    },
    'izq.sensor_occupy.24': {
        'interval_seconds': 15,
        'sensor_properties': 'illumination,distance,has_someone_duration,no_one_duration',
        'number_properties': 'no_one_determine_time',
    },
    'izq.sensor_occupy.solo': {
        'sensor_properties': 'occupancy_status,illumination',
        'number_properties': 'bio_sensitive',
        'switch_properties': 'indicator_light,shadow_tracking',
        'button_actions': 'led_toggle,find_device'
    },
    'izq.sensor_occupy.trio': {
        'sensor_properties': 'occupancy_status,illumination',
        'number_properties': 'bio_sensitive',
        'switch_properties': 'indicator_light,shadow_tracking',
        'button_actions': 'led_toggle,find_device'
    },
    'jyf.tow_w.ts03': {
        'auto_cloud': True,
        'interval_seconds': 120,
        'exclude_miot_properties': 'mode,fault',
        'chunk_coordinators': [
            {'interval': 30, 'props': 'on,target-temperature,temperature,left_time'},
        ],
    },
    'leishi.bhf_light.lsyb01': {
        'light_services': 'night_light',
        'switch_properties': 'heating,blow,ventilation,dryer',
        'select_properties': 'heat_level,fan_level',
        'button_actions': 'stop_working',
    },
    'leishi.light.*': {
        'exclude_miot_services': 'scenes,scene,scens,remote',
        'exclude_miot_properties': 'default.user_save,professional_setting.delay',
        'switch_properties': 'flex_switch,wind_reverse',
        'select_properties': 'default.default',
    },
    'leshi.light.wy0b01': {
        'chunk_properties': 1,
        'exclude_miot_services': 'remote,default,scene',
    },
    'leshi.light.wyfan': {
        'chunk_properties': 3,
    },
    'leshi.switch.v002': {
        'exclude_miot_services': 'scenes,remote',
    },
    'leshow.heater.bs1': {
        'current_temp_property': 'environment.temperature',
    },
    'leshow.humidifier.jsq1': {
        'miot_type': 'urn:miot-spec-v2:device:humidifier:0000A00E:leshow-jsq1:2',
        'sensor_properties': 'humidifier.water_level',
        'switch_properties': 'alarm,warm_wind_turn,turn_ovp,dry_turn,turn_off_dry_turn',
        'number_properties': 'screen_brightness,tsms_turn_off',
    },
    'linp.doorbell.g04': {
        'sensor_properties': 'pressed_key',
        'switch_properties': 'on',
        'select_properties': 'current_music,current_key',
        'number_properties': 'volume',
        'select_actions': 'play_music',
    },
    'linp.switch.s2dw3': {
        'button_actions': 'reboot',
        'switch_properties': 'screen.on,auto_screen_off,auto_screen_brightness,night_mode',
        'select_properties': 'mode,default_power_on_state,auto_screen_off_time,screen_switch,sensitivity',
        'number_properties': 'brightness',
        'text_properties': 'text_a,text_b,text_c,text_s',
        'light_services': 'vd_light_a,vd_light_b,vd_light_c',
    },
    'lumi.acpartner.mcn02': {
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'miio_cloud_props': [],
    },
    'lumi.acpartner.mcn02:electric_power': {
        'value_ratio': 1,
    },
    'lumi.acpartner.mcn04': {
        'auto_cloud': True,
        'interval_seconds': 60,
        'chunk_properties': 8,
        'sensor_properties': 'electric_power',
        'switch_properties': 'on,quick_cool_enable,indicator_light',
        'select_properties': 'fan_level,ac_mode',
        'miio_cloud_props': [],
        'stat_power_cost_type': 'stat_day_v3',
        'stat_power_cost_key': '7.1,7.3',
        'sensor_attributes': 'power_cost_today,power_cost_month,power_cost_today_2,power_cost_month_2',
        'configuration_entities': 'ac_mode,indicator_light',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,mode,target_temperature,fan_level,electric_power'},
        ],
    },
    'lumi.acpartner.mcn04:power_consumption': ENERGY_KWH,
    'lumi.acpartner.mcn04:power_cost_today': {'value_ratio': 1, **ENERGY_KWH},
    'lumi.acpartner.mcn04:power_cost_month': {'value_ratio': 1, **ENERGY_KWH},
    'lumi.acpartner.mcn04:power_cost_today_2': ENERGY_KWH,
    'lumi.acpartner.mcn04:power_cost_month_2': ENERGY_KWH,
    'lumi.acpartner.*': {
        'sensor_attributes': 'electric_power,power_cost_today,power_cost_month',
        'select_properties': 'fan_level',
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
        **ENERGY_KWH,
        'value_ratio': 0.001,
    },
    'lumi.acpartner.*:power_cost_month': {
        **ENERGY_KWH,
        'value_ratio': 0.001,
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
    'lumi.aircondition.*:power_consumption': ENERGY_KWH,
    'lumi.aircondition.*:power_cost_today': ENERGY_KWH,
    'lumi.aircondition.*:power_cost_month': ENERGY_KWH,
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
    'lumi.ctrl_neutral2.v1': {
        'cloud_delay_update': 10,
        'exclude_miot_properties': 'name,mode',
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
    'lumi.plug.v1': {
        'sensor_properties': 'electric_power',
        'select_properties': 'default_power_on_state',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_type': 'stat_day',
        'stat_power_cost_key': 'powerCost',
    },
    'lumi.plug.*:power_cost_today': {
        **ENERGY_KWH,
        'value_ratio': 0.001,
    },
    'lumi.plug.*:power_cost_month': {
        **ENERGY_KWH,
        'value_ratio': 0.001,
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
    'lumi.switch.acn032': {
        'sensor_properties': 'electric_power',
        'switch_properties': 'screen.on,mute,no_disturb',
        'select_properties': 'volume',
        'number_properties': 'brightness,auto_screen_off_time',
    },
    'lumi.switch.*': {
        'cloud_delay_update': 10,
    },
    'lxzn.switch.cbcsmj': {
        'sensor_properties': 'temperature,electric_power',
        'select_properties': 'default_power_on_state',
        'switch_properties': 'electric_alarm_set,heat_alert_set,overcurrent_set,overvoltage_set,undervoltage_set',
        'number_properties': 'electric_alarm,heat_alert,overcurrent_alarm,overvoltage_alarm,undervoltage_alarm',
    },

    'madv.cateye.mi3iot': {
        'binary_sensor_properties': 'madv_doorbell.motion_detection',
        'sensor_properties': 'battery_level',
        'switch_properties': 'eco,motion_detection,alarm,autoreply,fw_autoupgrade,vistpush,motionpush',
        'select_properties': 'night_shot,ringtone,alarm_interval,detection_sensitivity,motionpush_pushtype,videolength,'
                             'eco_code,ringer_music',
        'number_properties': 'videodelay,volume',
    },
    'miaomiaoce.sensor_ht.t1': {
        'exclude_miot_services': 'battery',  # -704002000
    },
    'miaomiaoce.sensor_ht.t6': {
        'exclude_miot_services': 'battery',
    },
    'mibx5.washer.*': {
        'sensor_properties': 'fault,left_time,door_state,run_status,power_consumption,water_consumption,clean_lefttime,'
                             'detergent_left_level,fabric_softener_left_level,water_temperature',
        'switch_properties': 'on,sleep_mode,steam_sterilization,high_water_switch,detergent_self_delivery,blue_oxygen,'
                             'child_protected_enabled,self_delivery_auto_turnoff,laundry_beads,one_click_wash,ai_mode,'
                             'disinfectant_mode,linkage_on',
        'select_properties': 'mode,soak_time,drying_level,drying_degree,reservation_wash_status,'
                             'detergent_self_delivery_level,softener_self_delivery_level',
        'number_select_properties': 'target_temperature,rinsh_times,spin_speed,wash_time,shake_time,drying_time,reservation_left_time',
        'button_actions': 'start_wash,stop_washing,pause,clean_start,clean_stop',
    },
    'midjd8.washer.*': {
        'select_properties': 'shake_time,soak_time',
        'switch_properties': 'high_water_switch,steam_sterilization,sleep_mode',
    },
    'midr.rv_mirror.*': {
        'binary_sensor_properties': 'driving_status',
        'miio_cloud_props': 'Status,Position',
        'miio_cloud_props_template': 'midr_rv_mirror_cloud_props',
    },
    'miir.aircondition.*': {
        'select_properties': 'ir_mode',
        'number_properties': 'ir_temperature',
        'button_actions': 'turn_on,turn_off,fan_speed_up,fan_speed_down,temperature_up,temperature_down',
    },
    'mijia.light.*': {
        'cloud_delay_update': 7,
    },
    'mike.bhf_light.2': {
        'switch_properties': 'heating,blow,ventilation,mode,horizontal_swing',
        'select_properties': None,
        'number_properties': None,
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,heating,blow,ventilation'},
        ],
    },
    'minij.washer.v20': {
        'descriptions_for_on': 'Busy,Delay,Run',
        'descriptions_for_off': 'Off,Standby,Idle,Pause,Paused,Completed,Fault,END,E6',
    },
    'mmgg.feeder.fi1': {
        'chunk_properties': 1,
        'button_actions': 'pet_food_out,resetclean,reset_desiccant_life',
        'binary_sensor_properties': 'outletstatus,doorstatus',
        'sensor_properties': 'fault,pet_food_left_level,outfood_num,cleantime,desiccant_left_time',
        'number_properties': 'key_stat,indicator_light.on',
        'exclude_miot_properties': 'outfood_id,contrycode,feddplan_string,factory_result,phon_time_zone'
                                   'feedplan_hour,feedplan_min,feedplan_unit,feedplan_stat,feedplan_id,getfeedplan_num',
    },
    'mmgg.feeder.fi1:pet_food_out': {
        'action_params': 1,
    },
    'mmgg.feeder.inland': {
        'chunk_properties': 1,
        'button_actions': 'pet_food_out,resetclean,reset_desiccant_life',
        'binary_sensor_properties': 'outletstatus,doorstatus',
        'sensor_properties': 'pet_food_left_level,outfood_num,foodstatus,desiccant_left_time,cleantime',
        'switch_properties': 'key_stat,indicator_light.on',
        'exclude_miot_properties': 'fault,outfood_id,contrycode,feddplan_string,factory_result,phon_time_zone,'
                                   'feedplan_hour,feedplan_min,feedplan_unit,feedplan_stat,feedplan_id,getfeedplan_num',
    },
    'mmgg.feeder.inland:pet_food_out': {
        'action_params': 1,
    },
    'mmgg.feeder.petfeeder': {
        'button_actions': 'pet_food_out,reset_desiccant_life',
        'sensor_properties': 'pet_food_left_level,feed_today,desiccant_left_time,cleantime',
        'switch_properties': 'feedstatus',
    },
    'mmgg.feeder.petfeeder:pet_food_out': {
        'action_params': 1,
    },
    'mmgg.litter_box.lbc1': {
        'binary_sensor_properties': 'warehouse_uninstall,cover_open,roller_uninstall,device_dump,'
                                    'cat_enter_state,cat_near_state,enter_time_too_long',
        'sensor_properties': 'usage_count,trash_can_status,cat_weight,toilet_time,cat_id,cleaning_times,'
                             'cat_litter_left_stat,cat_litter_left_level,warehouse_overweight,cat_toilet_flag,'
                             'deodorant_left_time,roller_overload_flag',
        'switch_properties': 'auto_cleanup,stool_mode,auto_screen_off,no_disturb',
        'select_properties': 'cat_litter_type',
        'number_properties': 'auto_clean_interval',
        'button_actions': 'start_clean,weight_calibrate,start_smooth_litter,start_dump_litter,cancer_clean,'
                          'reset_deodorant_life',
    },
    'mmgg.pet_waterer.wi11': {
        'binary_sensor_properties': 'no_water_flag,pump_block_flag,lid_up_flag',
        'button_actions': 'reset_filter_life,reset_clean_time',
        'sensor_properties': 'remain_clean_time,fault,filter_left_time,no_water_time',
        'select_properties': 'mode',
    },
    'mmgg.pet_waterer.wi11:no_water_flag': {
         'reverse_state': True,
    },
    'mmgg.pet_waterer.s1': {
        'binary_sensor_properties': 'no_water_flag,pump_block_flag,lid_up_flag',
        'button_actions': 'reset_filter_life,reset_clean_time',
        'sensor_properties': 'remain_clean_time,fault,filter_left_time,no_water_time',
        'select_properties': 'mode',
    },
    'mmgg.pet_waterer.s4': {
        'binary_sensor_properties': 'no_water_flag,pump_block_flag',
        'button_actions': 'reset_filter_life,reset_clean_time',
        'sensor_properties': 'remain_clean_time,fault,filter_left_time,no_water_time',
        'select_properties': 'mode',
    },
    'mrbond.airer.m1s': {
        'miot_type': 'urn:miot-spec-v2:device:airer:0000A00D:mrbond-m1pro:1',
    },
    'mrbond.airer.m53pro': {
        'position_reverse': False,
        'sensor_properties': 'fault,left_time',
        'select_properties': 'dryer,drying_level',
        'switch_properties': '',
        'chunk_properties': 1,
    },
    'mrbond.airer.*': {
        'parallel_updates': 1,
    },
    'msj.f_washer.m2': {
        'chunk_properties': 1,
        'button_actions': 'start_wash,pause,drain,pause_drain',
    },
    'mxiang.camera.mwc11': {
        'sensor_properties': 'battery',
        'switch_properties': 'on,time-watermark,wdr-mode,status-light,distortion-correct,'
                             'moved-push,human-detect,motion-detection',
        'select_properties': 'night-shot,video-auto-stop-time,resolution,power-freq-switch,'
                             'delay-recording,recording-time,alarm-interval,detection-sensitivity',
        'number_properties': 'image-rollover,rssi',
        'button_actions': 'restart',
    },
    'mxiang.cateye.*': {
        'miio_cloud_props': 'battery_level,is_can_open_video',
        'miio_cloud_records': 'event.human_visit_details:1',
        'miio_cloud_props_template': 'mxiang_cateye_cloud_props',
        'miio_event_human_visit_details_template': 'mxiang_cateye_human_visit_details',
    },

    'nineam.desk.hoo01': {
        'state_property': 'standing_desk.moving_status',
        'sensor_properties': 'current_height,fault',
        'switch_properties': 'on,lock_status',
        'select_properties': 'mode,desk_control',
        'number_properties': 'target_height,stand_height,sit_height,interval',
    },
    'novo.curtain.n21': {
        'chunk_properties': 1,
        'exclude_miot_properties': 'fault',
        'select_properties': 'motor_control',
    },
    'nwt.derh.wdh318efw1': {
        'binary_sensor_properties': 'tank_full',
    },
    'nwt.derh.wdh318efw1:tank_full': {
        'device_class': 'problem',
    },

    'opple.bhf_light.acmoto': {
        'exclude_miot_services': 'pair,wifisinr,class_sku,fan_motor',
        'exclude_miot_properties': 'fault',
        'light_services': 'aura_light',
        'number_properties': 'function_countdown.warm,function_countdown.blower,'
                             'function_countdown.breath,function_countdown,shutdown',
    },
    'opple.light.dcfan2': {
        'sensor_properties': 'temperature',
        'switch_properties': 'cycle_switch,mode_switch,switch,intelligent_speed,circle_air,bwind_rotate,'
                             'fan_countdown_switch',
        'select_properties': 'nursing_value,fan_level,buzzer_status',
        'number_properties': 'temp_set,fan_countdown_time',
        'percentage_property': 'fan_advance.speed',
    },
    'opple.light.yrtd': {
        'switch_properties': 'night_light,time_display,wake_up_at_night,voice',
        'select_properties': 'study_time',
        'number_properties': 'love_bright,love_color',
    },
    'ows.towel_w.mj1x0': {
        'sensor_properties': 'temperature',
        'select_properties': 'mode',
        'number_properties': 'target_temperature,dry_time',
    },

    'philips.light.aibed': {
        'sensor_properties': 'sleep_state,wakeup_state',
        'switch_properties': 'night_en,wristband_switch,awake_enable_first,awake_enable_second,awake_enable_third',
        'select_properties': 'mode_main,mode_light,mode_sleep,mode_scene',
        'number_properties': 'sleep_duration,music_preview,sleep_volume,sleep_startbri,scene_volume',
        'button_actions': 'brightness_up,brightness_down,cct_up,cct_down,stop_preview',
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
    'qdhkl.aircondition.b23': {
        'local_delay_update': 8,
        'cloud_delay_update': 8,
        'miot_type': 'urn:miot-spec-v2:device:air-conditioner:0000A004:qdhkl-b23:2',
    },
    'qjiang.acpartner.wb20': {
        'chunk_properties': 1,
        'sensor_properties': 'switch.temperature',
        'exclude_miot_services': 'air_condition_outlet_matching,matching_action',
        'exclude_miot_properties': 'fault',
    },
    'qmi.plug.psv3': {
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'sensor_properties': 'switch.temperature',
        'stat_power_cost_key': '3.1',
        'exclude_miot_services': 'simulation',
    },
    'qmi.plug.psv3:electric_current': {
        'value_ratio': 0.001,
        'unit_of_measurement': 'A',
    },
    'qmi.plug.psv3:voltage': {
        'value_ratio': 0.001,
        'unit_of_measurement': 'V',
    },
    'qmi.plug.psv3:power_consumption': ENERGY_KWH,
    'qmi.plug.psv3:power_cost_today': ENERGY_KWH,
    'qmi.plug.psv3:power_cost_month': ENERGY_KWH,
    'qmi.plug.tw02': {
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'sensor_properties': 'switch.temperature',
        'stat_power_cost_key': '4.1',
        'exclude_miot_services': 'simulation',
    },
    'qmi.plug.tw02:electric_power': {
        'unit_of_measurement': 'W',
    },
    'qmi.plug.tw02:electric_current': {
        'value_ratio': 0.001,
        'unit_of_measurement': 'A',
    },
    'qmi.plug.tw02:voltage': {
        'value_ratio': 1,
        'unit_of_measurement': 'V',
    },
    'qmi.plug.tw02:power_consumption': ENERGY_KWH,
    'qmi.plug.tw02:power_cost_today': ENERGY_KWH,
    'qmi.plug.tw02:power_cost_month': ENERGY_KWH,
    'qmi.plug.2a1c1': {
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'sensor_properties': 'switch.temperature',
        'stat_power_cost_key': '3.1',
    },
    'qmi.plug.2a1c1:electric_power': {
        'unit_of_measurement': 'W',
    },
    'qmi.plug.2a1c1:electric_current': {
        'value_ratio': 0.001,
        'unit_of_measurement': 'A',
    },
    'qmi.plug.2a1c1:voltage': {
        'value_ratio': 0.001,
        'unit_of_measurement': 'V',
    },
    'qmi.plug.2a1c1:power_consumption': ENERGY_KWH,
    'qmi.plug.2a1c1:power_cost_today': ENERGY_KWH,
    'qmi.plug.2a1c1:power_cost_month': ENERGY_KWH,
    'qmi.plug.*': {
        'sensor_properties': 'power_consumption',
    },
    'qushui.bed.001': CHUNK_1,
    'qushui.bed.*': {
        'chunk_properties': 1,
        'switch_properties': 'ai_on',
        'select_properties': 'mode,hardness,memory_one,memory_two,sleep_lock',
        'number_properties': 'lumbar_angle,backrest_angle,leg_rest_angle',
        'target_position_properties': 'lumbar_angle,backrest_angle,leg_rest_angle',
    },
    'qushui.blanket.mj1': {
        'chunk_properties': 1,
        'sensor_properties': 'fault,water_level,a_temperature,b_temperature',
        'switch_properties': 'alarm,antifreezing_switch,ab_sleep_switch,anti_scald_switch',
        'select_properties': 'mode',
        'number_properties': 'target_temperature,timer',
    },

    'rhj.sensor_occupy.l730a': {
        'sensor_properties': 'illumination,no_one_duration,has_someone_duration',
    },
    'rmt.bed.zhsbed': {
        'sensor_properties': 'fault',
        'select_properties': 'mode',
        'target_position_properties': 'backrest_angle,leg_rest_angle',
    },
    'roborock.vacuum.*': {
        'sensor_attributes': 'props:clean_area,props:clean_time',
        'sensor_properties': 'vacuum.status',
        'select_properties': 'water_level,mop_mode',
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
    'roidmi.vacuum.v60': {
        'interval_seconds': 180,
        'button_actions': 'start_sweep,stop_sweeping,find_robot,stop_find_charge,continue_sweep,start_dust,pause,'
                          'pause_find_charge,continue_find_charge,reset_filter_life,reset_brush_life',
        'sensor_properties': 'status,fault,clean_area,clean_time,filter_life_level,brush_life_level,sweep_mode',
        'switch_properties': 'mop,auto_boost,double_clean,edge_sweep,led_switch,lidar_collision,mute,'
                             'station_key,station_led,use_auto_area,map_memory',
        'select_properties': 'mode,sweep_type,work_station_freq,water_level,path_type',
        'number_properties': 'volume',
        'exclude_miot_services': None,
        'exclude_miot_properties': 'vacuum.on',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'status,clean_area,clean_time,mode,sweep_type,water_level', 'notify': True},
            {'interval': 60, 'props': 'mop,auto_boost,double_clean,edge_sweep,led_switch,lidar_collision,mute'},
            {'interval': 600, 'props': 'filter_life_level,filter_left_time,brush_life_level,brush_left_time'},
        ],
    },
    'roidmi.vacuum.*': {
        'exclude_miot_services': 'custom',
    },
    'roome.bhf_light.*': {
        'sensor_attributes': 'temp,currenttemp',
        'select_attributes': 'main_state,main_light,night_light,heat,vent,dry,natural_wind,delay_wind',
    },

    'smartj.curtain.sjdt82': CHUNK_1,
    'smith.blanket.cxma1': {
        'sensor_properties': 'fault,temperature',
        'select_properties': 'water_level,quilt_dry',
        'number_properties': 'target_temperature,countdown_time',
    },
    'smith.waterpuri.cxr800': {
        'chunk_properties': 1,
        'state_property': 'chanitex_wp_gs.rsysstate',
        'sensor_properties': 'tds_in,tds_out,rwaterconsumption,rfilterwaterlifei,rfilterwaterlifeii,rfilterwaterlifeiii',
    },
    'shuii.humidifier.jsq002': {
        'brightness_for_on': 3,
        'brightness_for_off': 1,
    },
    'suittc.airrtc.wk168': {
        'sensor_properties': 'temperature',
        'switch_properties': 'on',
        'turn_on_hvac': 'heat',
    },

    'topwit.bhf_light.rz01': {
        'sensor_properties': 'temperature',
        'switch_properties': 'heating,blow,ventilation',
        'number_properties': 'ventilation_cnt_down',
    },

    'uvfive.steriliser.maine': CHUNK_1,
    
    'viomi.airer.xy108': {
        'switch_properties': 'dryer',
    },
    'viomi.airer.*': {
        'sensor_properties': 'status',
        'switch_properties': '',
        'select_properties': 'dryer,swing_mode',
        'number_properties': 'drying_time',
        'position_reverse': False,
        'cover_position_mapping': {
            0: 50,   # Normal
            1: 100,  # Rising-limit
            2: 0,    # Descent-limit
        },
    },
    'viomi.fridge.m1': {
        'sensor_properties': 'fridge.temperature',
    },
    'viomi.hood.v1': {
        'number_properties': 'off_delay_time',
        'miio_properties': [
            'cruise', 'link', 'holiday', 'leftBtn', 'rightBtn', 'batLife',
            'workRemind', 'offLight', 'offTime', 'isBound', 'isLink',
        ],
    },
    'viomi.hood.v5': {
        'interval_seconds': 120,
        'sensor_properties': 'battery_life,left_status,right_status',
        'switch_properties': 'off_delay,stove_bind,light_on,power_on_light,power_off_light,clean_remine_on,'
                             'cruise_on,holiday_on,gestures',
        'select_properties': 'holiday_cycle,holiday_duration',
        'number_properties': 'off_delay_time,countdown_time,clean_remine_time',
        'chunk_coordinators': [
            {'interval': 30, 'props': 'on,fan_level,left_status,right_status,off_delay_time,countdown_time'},
        ],
    },

    'viomi.vacuum.v18': {
        'sensor_properties': 'vacuum.status,fault,door_state,mop_state,hypa_life,hypa_hours,'
                             'main_brush_life,main_brush_hours,side_brush_life,side_brush_hours,'
                             'clean_area,clean_use_time,mop_life,mop_hours',
        'switch_properties': 'repeat_state,remember_state,dust_collection',
        'select_properties': 'vacuum.sweep_type,vacuum.wdr_mode,water_grade,viomi_vacuum.mop_route',
        'number_properties': 'mute',
        'exclude_miot_services': 'order,map,voice',
        'exclude_miot_properties': 'direction,stream_address,zone_points,restrict_points,clean_room_mode,'
                                   'consumable_index,clean_room_oper,clean_room_ids,cur_map_url,cur_map_id,'
                                   'time_zone,has_map,has_newmap,cur_lang',
    },
    'viomi.vacuum.v18:clean_use_time': {
        'device_class': 'duration',
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
    'viomi.waterheater.e1': {
        'unreadable_properties': True,  # issues/1707
    },
    'viomi.waterheater.m1': {
        'sensor_properties': 'water_heater.status,water_level,temperature_tips,'
                             'input_water_temp,water_pump_volt,remaining_time',
        'switch_properties': 'on,hot_water_recirculation,heat_preservation,jog_function,pressure_boost.status,'
                             'cloud_preheater,in_cloud_timer,reminder,enhanced',
        'select_properties': 'light_off_time,effective,model',
        'number_properties': 'target_temperature,boost_value',
    },

    'wfxx.motor.mxrf': {
        'switch_properties': 'key_set_flag',
        'select_properties': 'key_num',
    },
    'wfxx.motor.ycmkq': {
        'switch_properties': 'key_set_flag,reset',
        'select_properties': 'keyone_sta,keytwo_sta,keythree_sta,keyfour_sta',
    },
    'wise.wifispeaker.x7': {
        'switch_properties': 'key_one,key_two,key_three,key_four,key_five,key_six,key_seven,key_eight,key_nine,'
                             'key_ten,key_eleven,key_twelve,key_thirteen,key_fourteen,key_fifteen,key_sixteen',
    },

    'xiaomi.airc.r34r00': {
        'sensor_properties': 'power_consumption',
    },
    'xiaomi.airc.r24r00': {
        'sensor_properties': 'power_consumption',
    },
    'xiaomi.airc.r09h00': {
        'sensor_properties': 'outdoor_temp,mosquito_life,filter_life_level,power_consumption',
        'switch_properties': 'on,eco,heater,dryer,sleep_mode,vertical_swing,un_straight_blowing,favorite_on,alarm',
        'select_properties': 'vertical_angle,favorite_type,brightness,room_size',
        'number_properties': 'target_temperature,target_humidity,fan_percent',
    },
    'xiaomi.airc.*:power_consumption': ENERGY_KWH,
    'xiaomi.aircondition.m9': {
        'exclude_miot_services': 'machine_state,flag_bit,single_smart_scene',
        'exclude_miot_properties': 'enhance.timer,humidity_range',
    },
    'xiaomi.aircondition.ma1': {
        'miot_type': 'urn:miot-spec-v2:device:air-conditioner:0000A004:xiaomi-ma1:4',
    },
    'xiaomi.aircondition.ma2': {
        'miot_type': 'urn:miot-spec-v2:device:air-conditioner:0000A004:xiaomi-ma2:3',
    },
    'xiaomi.aircondition.ma4': {
        'miot_type': 'urn:miot-spec-v2:device:air-conditioner:0000A004:xiaomi-ma4:2',
    },
    'xiaomi.aircondition.mc9': {
        'exclude_miot_services': 'machine_state,flag_bit',
        'exclude_miot_properties': 'enhance.timer',
    },
    'xiaomi.aircondition.mt0': {
        'exclude_miot_services': 'iot_linkage,machine_state,screen_show',
        'exclude_miot_properties': 'enhance.timer,humidity_range,filter_core_rest,sleep_diy_sign',
    },
    'xiaomi.aircondition.mt6': {
        'select_properties': 'fan_level,horizontal_angle,vertical_angle',
        'number_properties': 'target_humidity,fan_percent',
        'exclude_miot_services': 'iot_linkage,machine_state,screen_show',
        'exclude_miot_properties': 'enhance.timer,humidity_range,filter_core_rest,sleep_diy_sign',
    },
    'xiaomi.aircondition.*': {
        'exclude_miot_services': 'iot_linkage,machine_state,flag_bit',
        'exclude_miot_properties': 'enhance.timer',
    },
    'xiaomi.airp.cpa4': {
        'button_actions': 'toggle,reset_filter_life',
        'sensor_properties': 'filter_life_level',
        'switch_properties': 'alarm',
        'select_properties': 'brightness,aqi_updata_heartbeat',
        'number_properties': 'favorite_level',
        'speed_property': 'favorite_level',
        'exclude_miot_services': None,
        'exclude_miot_properties': 'country_code,filter_used_time_dbg',
    },
    'xiaomi.airp.mp4': {
        'switch_properties': 'anion,alarm',
        'light_services': 'screen',
        'brightness_for_on': 0,
        'brightness_for_off': 2,
        'exclude_miot_services': 'rfid',
    },
    'xiaomi.airp.va4': {
        'sensor_properties': 'relative_humidity,air_quality,pm2_5_density,temperature,hcho_density,filter_life_level',
        'switch_properties': 'on,anion,uv,alarm',
        'select_properties': 'air_purifier_favorite.fan_level',
        'number_properties': 'aqi_updata_heartbeat',
        'button_actions': 'reset_filter_life',
        'light_services': 'screen',
        'brightness_for_on': 0,
        'brightness_for_off': 2,
        'exclude_miot_services': 'rfid,custom_service,filter_debug',
    },
    'xiaomi.airp.*': {
        'exclude_miot_services': 'custom_service',
    },
    'xiaomi.blanket.mj2': {
        'chunk_properties': 1,
        'exclude_miot_properties': 'fault,sleep_setting',
        'switch_properties': 'alarm,indicator_light.on,antifreezing_switch,anti_scald_switch',
        'number_properties': 'target_temperature,countdown_time',
        'select_properties': 'water_level',
    },
    'xiaomi.controller.86v1': {
        'switch_properties': 'mute,sleep_mode,auto_screen_off,auto_screen_brightness,touch_sound,key_name_display',
        'select_properties': 'mode,mibrain_level,mico_level,display_state,wallpaper',
        'number_properties': 'speaker.volume,brightness,theme',
        'button_actions': 'homepage,light',
        'text_actions': 'play_text,execute_text_directive',
    },
    'xiaomi.blanket.mj1': {
        'chunk_properties': 1,
        'switch_properties': 'anti_scald_switch,ab_sleep_switch,auto_screen_off',
        'select_properties': 'mode,heat_level',
        'number_properties': 'a_countdown,b_countdown',
    },
    'xiaomi.fryer.maf07d': {
        'interval_seconds': 120,
        'button_actions': 'air_fryer.start_cook,pause,cancel_cooking,resume_cook',
        'sensor_properties': 'status,fault,left_time',
        'switch_properties': 'auto_keep_warm,current_keep_warm,turn_pot_config',
        'select_properties': 'mode,turn_pot,texture,target_cooking_measure',
        'number_properties': 'target_time,target_temperature,reservation_left_time,cooking_weight',
        'exclude_miot_properties': 'recipe_id,recipe_name,recipe_sync',
        'chunk_coordinators': [
            {'interval': 20, 'props': 'status,target_time,target_temperature,left_time'},
            {'interval': 35, 'props': 'fault,mode,reservation_left_time,cooking_weight'},
        ],
    },
    'xiaomi.derh.lite': {
        'chunk_properties': 1,
        'sensor_properties': 'fault,delay_remain_time',
        'switch_properties': 'alarm,delay',
        'select_properties': 'indicator_light.mode',
        'number_properties': 'delay_time',
    },
    'xiaomi.esteamer.mes01': {
        'sensor_properties': 'left_time,keep_warm_left_time',
        'switch_properties': 'auto_keep_warm',
        'select_properties': 'mode',
        'number_properties': 'target_temperature,target_time,reservation_left_time,keep_warm_time',
        'button_actions': 'start_cook,pause,cancel_cooking,resume_cook',
    },
    'xiaomi.fan.p51': {
        'button_actions': 'turn_left,turn_right,toggle,toggle_mode,loop_gear',
        'switch_properties': 'delay',
        'select_properties': 'horizontal_swing_included_angle',
        'number_properties': 'delay_time',
        'percentage_property': 'prop.2.6',
    },
    'xiaomi.feeder.iv2001': {
        'button_actions': 'pet_food_out,reset_desiccant_life,weigh_manual_calibrate',
        'number_properties':'target_feeding_measure,food-intake-rate',
        'sensor_properties': 'pet_food_left_level,status,eaten_food_measure,desiccant_left_level,desiccant_left_time',
        'switch_properties': 'add-meal-state,food-intake-state,schedule-state,compensate_switch,prevent_accumulation',
        'select_properties': 'set-screen-display',
    },
    'xiaomi.feeder.pi2001': {
        'chunk_properties': 1,
        'button_actions': 'pet_food_out,reset_desiccant_life,weigh_manual_calibrate',
        'number_properties':'target_feeding_measure',
        'sensor_properties': 'pet_food_left_level,fault,eaten_food_measure,desiccant_left_level,desiccant_left_time',
        'switch_properties': 'compensate_switch,prevent_accumulation',
    },
    'xiaomi.feeder.*:eaten_food_measure': {
        'state_class': 'measurement',
        'unit_of_measurement': 'g',
    },
    'xiaomi.feeder.*:pet_food_out': {
        'action_params': 1,
    },
    'xiaomi.health_pot.p1': {
        'select_actions': 'start_cook',
    },
    'xiaomi.heater.ma8': {
        'button_actions': 'toggle',
    },
    'xiaomi.humidifier.airmx': {
        'button_actions': 'toggle,reset_filter_life',
        'sensor_properties': 'water_level,air_dry_remain_time,remain_time,filter_life_level',
        'switch_properties': 'overwet_protect,automatic_air_drying,delay,alarm,auto_alarm_off,clean.on,descale.on'
                             'indicator_light.on,auto_lights_off,wash_water_tank',
        'select_properties': 'indicator_light.brightness',
        'number_properties': 'delay_time',
    },
    'xiaomi.humidifier.p1200': {
        'button_actions': 'loop_mode,reset_filter_life',
        'select_properties': 'screen.brightness',
        'sensor_properties': 'clean_time,fan_dry_time,fault,water_level,water_status',
        'switch_properties': 'alarm,dry_switch,over_wet_protect,screen.on',
        'number_properties': 'off_delay_time',
    },
    'xiaomi.plug.mcn003': {
        'button_actions': 'toggle',
        'sensor_properties': 'fault,electric_power',
        'select_properties': 'default_power_on_state',
        'stat_power_cost_key': '3.1',
    },
    'xiaomi.plug.mcn003:power_cost_today': ENERGY_KWH,
    'xiaomi.plug.mcn003:power_cost_month': ENERGY_KWH,
    'xiaomi.tv.*': {
        'auto_cloud': True,
        'switch_properties': 'is_on',
        'number_properties': 'speaker.volume',
        'text_actions': 'message_router.post',
    },
    'xiaomi.tvbox.*': {
        'auto_cloud': True,
        'number_properties': 'speaker.volume',
    },
    'xiaomi.vacuum.b108gl': {
        'interval_seconds': 120,
        'sensor_properties': 'status,fault,cleaning_area,cleaning_time,charging_state,status_extend,'
                             'brush_life_level,filter_life_level',
        'binary_sensor_properties': 'mop_status',
        'switch_properties': 'edge_swing_tail_sweep,carpet_discriminate,carpet_boost,alarm,dnd_switch,'
                             'carpet_avoidance,carpet_display,sweep_break_switch',
        'select_properties': 'sweep_mop_type,sweep_type,clean_times,suction_level,mop_water_output_level,mode,'
                             'edge_sweep_frequency,carpet_cleaning_method',
        'number_properties': 'volume',
        'button_actions': 'start_sweep,stop_sweeping,start_only_sweep,start_mop,start_sweep_mop,stop_and_gocharge,'
                          'pause_sweeping,continue_sweep,find_vacuum,start_charge,reset_brush_life,reset_filter_life',
        'exclude_miot_services': 'vacuum_map',
        'configuration_entities': 'edge_swing_tail_sweep,carpet_discriminate,carpet_boost,alarm,dnd_switch,'
                                  'carpet_avoidance,carpet_display,sweep_break_switch,edge_sweep_frequency,'
                                  'carpet_cleaning_method,reset_brush_life,reset_filter_life',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'status,mop_status,cleaning_area,cleaning_time,charging_state', 'notify': True},
            {'interval': 15, 'props': 'sweep_mop_type,sweep_type,mode,clean_times,suction_level'},
        ],
    },
    'xiaomi.vacuum.b108gl:cleaning_area': {
        'value_ratio': 0.01,
        'unit_of_measurement': '㎡',
    },
    'xiaomi.vacuum.b108gl:cleaning_time': {
        'value_ratio': 0.016666,
        'device_class': 'duration',
        'unit_of_measurement': 'min',
    },
    'xiaomi.vacuum.c107': {
        'interval_seconds': 120,
        'exclude_miot_services': 'vacuum_map,custom,ai_small_pictures,voice_management',
        'exclude_miot_properties': 'vacuum_frameware_version,restricted_sweep_areas,restricted_walls,room_information,'
                                   'order_clean,map_complete_dialog,carpet_deep_cleaning,carpet_discriminate,'
                                   'water_check_list,sweep_ai_object,sweep_furniture,carpet_object,vacuum_route,'
                                   'fault_ids,plugin_info_remind,enable_time_period,current_no_disturb,sweep_route,'
                                   'current_physical_control_lock,current_no_disturb,obstacle_avoidance_strategy',
        'binary_sensor_properties': 'mop_status',
        'sensor_properties': 'status,cleaning_area,cleaning_time,water_check_status,battery_level,charging_state,'
                             'mop_life_level,brush_life_level,filter_life_level,detergent_left_level,'
                             'dust_bag_life_level',
        'switch_properties': 'enable_mop_wash,sweep_break_switch,auto_dust_arrest,ai_cleaning,hot_water_mop_wash,'
                             'auto_mop_dry,auto_water_change,use_detergent,mop_auto_lift,carpet_boost,carpet_avoidance,'
                             'sweep_ai_detection,dirt_detection,object_detection,room_detection,solid_dirt_detection,'
                             'floor_material_detection,liquid_dirt_detection,defecation_detection,cut_hair_config,'
                             'edge_swing_tail_sweep,detergent_self_delivery,ai_managed_cleaning',
        'select_properties': 'mode,sweep_mop_type,sweep_type,clean_times,mop_water_output_level,drying_time,alarm'
                             'water_output_for_washing_mop,dust_arrest_frequency,edge_sweep_frequency,'
                             'carpet_cleaning_method,detergent_self_delivery_level',
        'number_properties': 'volume',
        'button_actions': 'start_sweep,start_only_sweep,start_mop,start_sweep_mop,start_custom_sweep,start_dry,'
                          'pause_sweeping,continue_sweep,stop_and_gocharge,start_charge,start_mop_wash,start_cut_hair,'
                          'enter_remote,exit_remote,stop_mop_wash,back_mop_wash,stop_dry,stop_cut_hair,identify,'
                          'reset_mop_life,reset_brush_life,reset_filter_life,reset_detergent_management_level,'
                          'reset_dust_bag_life',
        'select_actions': 'remote_control',
        'configuration_entities': 'ai_cleaning,ai_managed_cleaning,use_detergent,defecation_detection,cut_hair_config,'
                                  'solid_dirt_detection,floor_material_detection,room_detection,liquid_dirt_detection,'
                                  'mop_auto_lift,carpet_boost,carpet_avoidance,carpet_cleaning_method,object_detection,'
                                  'dirt_detection,sweep_ai_detection,hot_water_mop_wash,physical_control_locked,volume,'
                                  'auto_water_change,auto_mop_dry,auto_dust_arrest,dust_arrest_frequency,'
                                  'vacuum.detergent_self_delivery,detergent_self_delivery_level',
        'diagnostic_entities': 'voltage,water_check_status',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'status,cleaning_area,cleaning_time,charging_state', 'notify': True},
            {'interval': 15, 'props': 'mode,sweep_mop_type,sweep_type,clean_times'},
        ],
    },
    'xiaomi.vacuum.d109gl': {
        'interval_seconds': 120,
        'exclude_miot_services': 'vacuum_map,custom,voice_management',
        'binary_sensor_properties': 'mop_status,sleep_status',
        'sensor_properties': 'status,cleaning_area,cleaning_time,mop_life_level,brush_life_level,filter_life_level,'
                             'dust_bag_life_level',
        'switch_properties': 'carpet_boost,carpet_avoidance,carpet_display,sweep_break_switch,enable_mop_wash,'
                             'auto_dust_arrest,auto_mop_dry,auto_water_change,use_detergent,detergent_self_delivery,'
                             'detergent_depletion_reminder,carpet_deep_cleaning,carpet_discriminate,sweep_carpet_first,'
                             'mop_outer_swing,alarm,no_disturb',
        'select_properties': 'sweep_mop_type,sweep_type,clean_times,mode,mop_water_output_level,frequency_mop_wash,'
                             'water_output_for_washing_mop,drying_time,dust_arrest_frequency,carpet_cleaning_method,'
                             'sweep_route,obstacle_avoidance_strategy,mop_outer_swing_frequency,worry_free_clean_mode,'
                             'auto_dust_arrest_power_level,wash_mop_water_temperature',
        'number_properties': 'frequency_mop_wash_by_time,volume',
        'button_actions': 'start_sweep,stop_sweeping,stop_and_gocharge,start_only_sweep,start_mop,start_sweep_mop,'
                          'pause_sweeping,continue_sweep,start_dust_arrest,start_mop_wash,start_dry,start_eject,'
                          'stop_mop_wash,stop_dry,back_mop_wash,start_charge,identify,'
                          'reset_mop_life,reset_brush_life,reset_filter_life,reset_dust_bag_life',
        'configuration_entities': 'carpet_boost,carpet_avoidance,carpet_display,sweep_break_switch,enable_mop_wash,'
                                  'frequency_mop_wash,water_output_for_washing_mop,use_detergent,detergent_self_delivery,'
                                  'detergent_depletion_reminder,carpet_cleaning_method,obstacle_avoidance_strategy,'
                                  'carpet_deep_cleaning,carpet_discriminate,sweep_carpet_first,mop_outer_swing,'
                                  'mop_outer_swing_frequency,frequency_mop_wash_by_time,auto_dust_arrest_power_level,'
                                  'reset_mop_life,reset_brush_life,reset_filter_life,reset_dust_bag_life',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'status,cleaning_area,cleaning_time,charging_state', 'notify': True},
            {'interval': 15, 'props': 'mode,sweep_mop_type,sweep_type,clean_times'},
        ],
    },
    'xiaomi.watch.*': {
        'sensor_properties': 'current_step_count,current_distance',
    },
    'xiaomi.waterheater.yms2': {
        'sensor_properties': 'water_heater.status,water_level,temperature_tips,'
                             'input_water_temp,water_pump_volt,remaining_time',
        'switch_properties': 'on,hot_water_recirculation,heat_preservation,jog_function,pressure_boost.status,'
                             'cloud_preheater,in_cloud_timer,reminder,enhanced',
        'select_properties': 'light_off_time,effective,model',
        'number_properties': 'target_temperature,boost_value',
    },
    'xiaomi.wifispeaker.*': {
        'switch_properties': 'on,sleep_mode,no_disturb',
        'button_actions': 'wake_up,play_music,tv_switchon,stop_alarm',
        'text_actions': 'play_text,execute_text_directive',
    },
    'xiaomi.wifispeaker.l04m:wake_up': {'action_params': ''},
    'xiaomi.wifispeaker.l06a:wake_up': {'action_params': ''},
    'xiaomi.wifispeaker.l09a:wake_up': {'action_params': ''},
    'xiaomi.wifispeaker.lx04:wake_up': {'action_params': ''},
    'xiaomi.wifispeaker.x08a:wake_up': {'action_params': ''},
    'xjx.toilet.relax': {
        'button_actions': 'flush_on',
    },
    'xjx.toilet.relaxp': {
        'sensor_properties': 'status',
        'switch_properties': 'status_seatheat,status_led,auto_led,switch_bubble,status_seat,status_cover,'
                             'auto_seat_close,auto_cover_close,status_selfclean',
        'select_properties': 'seat_temp',
        'button_actions': 'stop_working,flush_work,start_foam,clean_work',
    },
    'xwhzp.diffuser.xwxfj': {
        'sensor_properties': 'fragrance_liquid_left_level',
        'switch_properties': 'anion',
        'select_properties': 'mode',
        'number_properties': 'fragrance_out_time,countdown_time,countdown,scent_mix_level,brightness,color',
    },

    'yeelink.curtain.crc2': CHUNK_1,
    'yeelink.curtain.ctmt1': CHUNK_1,
    'yeelink.curtain.ctmt2': CHUNK_1,
    'yeelink.bhf_light.v5': {
        'select_properties': 'heat_mode,cold_mode,vent_mode',
    },
    'yeelink.bhf_light.v6': {
        'select_properties': 'heat_mode,cold_mode,vent_mode',
    },
    'yeelink.bhf_light.v10': {
        'chunk_properties': 1,
        'exclude_miot_services': 'yl_bath_heater',
        'exclude_miot_properties': 'ptc_bath_heater.mode',
    },
    'yeelink.bhf_light.v11': {
        'exclude_miot_services': 'yl_bath_heater',
    },
    'yeelink.bhf_light.v13': {
        'miot_type': 'urn:miot-spec-v2:device:bath-heater:0000A028:yeelink-v13:1',
    },
    'yeelink.bhf_light.*': {
        'switch_properties': 'heating,blow,ventilation',
    },
    'yeelink.light.dn2grp': {
        'cloud_delay_update': 7,
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
    'yeelink.light.virtual': {
        'cloud_delay_update': 7,
    },
    'yeelink.light.*': {
        'switch_properties': 'bg_on',
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
    'yunmi.kettle.*': {
        'button_actions': 'stop_work',
        'binary_sensor_properties': 'kettle_lifting',
        'sensor_properties': 'warming_time',
        'switch_properties': 'auto_keep_warm,keep_warm_reminder,custom_knob_temp,'
                             'lift_remember_temp,boiling_reminder,no_disturb',
        'select_properties': 'target_mode',
        'number_properties': 'keep_warm_temperature,keep_warm_time',
        'exclude_miot_services': 'knob_setting,local_timing',
    },
    'yunmi.waterpuri.*': {
        'number_properties': 'tds_warn_thd',
        'sensor_properties': 'tds_in,tds_out,temperature,rinse,filter_remaining',
        'switch_properties': 'light_mode',
    },
    'yunmi.waterpuri.s20': {
        'sensor_properties': 'tds_in,tds_out,water_purifier.temperature,current_team,flow_in,flow_out',
        'switch_properties': 'child_lock',
    },
    'yyunyi.wopener.yypy24': {
        'switch_properties': 'motor_reverse',
        'select_properties': 'mode',
        'number_properties': 'speed_level,clamp_strength',
        'target2current_position': True,
    },
    'yunmi.ysj.*': {
        'switch_properties': 'icing,child_lock,drink_remind,switch_button,buzzer_enable',
        'number_properties': 'store_timeout',
    },

    'zhimi.aircondition.v1': {
        'switch_properties': 'heater,sleep_mode,horizontal_swing,vertical_swing',
        'number_properties': 'vertical_angle,volume,brightness',
        'brightness_for_on': 5,
        'brightness_for_off': 0,
    },
    'zhimi.airfresh.*': {
        'switch_properties': 'heater,alarm',
    },
    'zhimi.airfresh.ua1': {
        'exclude_miot_services': 'custom_serveice',
        'brightness_for_on': 100,
        'brightness_for_off': 1,
    },
    'zhimi.airfresh.va4': {
        'sensor_properties': 'motor_speed',
        'brightness_for_on': 0,
        'brightness_for_off': 2,
    },
    'zhimi.airp.cpa4': {
        'chunk_properties': 1,
        'number_properties': 'favorite_level',
        'exclude_miot_properties': 'country_code',
    },
    'zhimi.airp.mb4a': {
        'number_properties': 'favorite_speed',
    },
    'zhimi.airp.mb5': {
        'sensor_properties': 'moto_speed_rpm,filter_used_debug',
        'switch_properties': 'anion,alarm',
        'select_properties': 'brightness,temperature_display_unit',
        'number_properties': 'favorite_speed,favorite_level',
    },
    'zhimi.airp.mb5a': {
        'sensor_properties': 'moto_speed_rpm,filter_used_debug',
        'switch_properties': 'anion,alarm',
        'select_properties': 'brightness,temperature_display_unit',
        'number_properties': 'favorite_speed,favorite_level',
    },
    'zhimi.airp.meb1:pm10_density': {
        'unit_of_measurement': 'µg/m³',
    },
    'zhimi.airp.sa4': {
        'switch_properties': 'alarm',
        'number_properties': 'air_purifier_favorite.fan_level,aqi_updata_heartbeat',
        'light_services': 'screen',
        'brightness_for_on': 0,
        'brightness_for_off': 2,
        'button_actions': 'reset_filter_life',
    },
    'zhimi.airp.rma3': {
        'sensor_properties': 'moto_speed_rpm',
        'switch_properties': 'alarm',
        'select_properties': 'brightness',
        'number_properties': 'air_purifier_favorite.fan_level',
    },
    'zhimi.airp.vb4:pm10_density': {
        'unit_of_measurement': 'µg/m³',
    },
    'zhimi.airpurifier.*': {
        'speed_property': 'favorite_level,favorite_fan_level',
        'number_properties': 'favorite_level,favorite_fan_level',
        'sensor_properties': 'illumination,motor_speed',
        # https://github.com/rytilahti/python-miio/blob/31c5d740d403c6f45f1e7e0d4a8a6276684a8ecd/miio/integrations/airpurifier/zhimi/airpurifier_miot.py#L13
        'exclude_miot_services': 'button,filter_time,rfid,others',
        'exclude_miot_properties': 'average_aqi_cnt,aqi_zone,sensor_state,aqi_goodh,aqi_runstate,aqi_state,'
                                   'motor_strong,motor_high,motor_med,motor_med_l,motor_low,motor_silent,'
                                   'motor_favorite,motor_set_speed',
    },
    'zhimi.airpurifier.ma2:filter_life_level': {
        'state_class': 'measurement',
    },
    'zhimi.airpurifier.mb4': {
        'sensor_properties': 'moto_speed_rpm',
        'switch_properties': 'alarm',
        'number_properties': 'favorite_speed,aqi_updata_heartbeat,brightness',
    },
    'zhimi.airpurifier.vb2:temperature': {
        'state_class': 'measurement',
        'unit_of_measurement': '°C',
    },
    'zhimi.airpurifier.za1': {
        'brightness_for_on': 0,
        'brightness_for_off': 2,
    },
    'zhimi.airpurifier.za2': {
        'brightness_for_on': 0,
        'brightness_for_off': 2,
    },
    'zhimi.fan.fb1': {
        'switch_properties': 'alarm,horizontal_swing,vertical_swing,oscillating,h_swing_back,v_swing_back,brightness',
        'number_properties': 'timing',
        'percentage_property': 'stepless_fan_level',
        'select_properties': 'mode,horizontal_angle,vertical_angle',
        'button_properties': 'h_swing_step_move,v_swing_step_move'
    },
    'zhimi.fan.za3': {
        'miot_type': 'urn:miot-spec-v2:device:fan:0000A005:zhimi-za3:3',
        'number_select_properties': 'fan_level',
    },
    'zhimi.fan.za4': {
        'miot_type': 'urn:miot-spec-v2:device:fan:0000A005:zhimi-za4:3',
        'number_select_properties': 'fan_level',
    },
    'zhimi.fan.*': {
        'switch_properties': 'anion,alarm,horizontal_swing,vertical_swing',
        'number_properties': 'horizontal_angle,vertical_angle,off_delay',
    },
    'zhimi.heater.na1': {
        'switch_properties': 'return_to_middle,alarm',
        'number_properties': 'countdown_time',
    },
    'zhimi.heater.nb1': {
        'brightness_for_on': 0,
        'brightness_for_off': 2,
    },
    'zhimi.humidifier.ca4:water_level': {
        'value_ratio': 100 / 120,
    },
    'zhimi.humidifier.cb1:water_level': {
        'state_class': 'measurement',
        'unit_of_measurement': '%',
    },
    'zhimi.humidifier.*': {
        'sensor_properties': 'water_level,actual_speed',
        'switch_properties': 'alarm,other.clean,humidifier.dry',
        'select_properties': 'screen.brightness',
        'number_properties': 'speed_level',
    },
    'zhimi.toilet.*': {
        'sensor_properties': 'status,cover_circle_status,current_water_temp,current_seat_temp,flush_status,'
                             'radar_sensor_status',
        'switch_properties': 'pir_switch,leave_auto_flushing,off_seat_close_cover',
        'select_properties': 'water_temperature,wind_temperature',
        'button_actions': 'flushing,open_cover_circle,close_cover_circle,stoving,hip_washing,women_washing,'
                          'move_back_and_forth,hot_cold_massage,nozzle_cleaning',
    },
    'zimi.mosq.v2:light_indicator.on': {
        'reverse_state': True,
    },
    'zimi.mosq.*': {
        'switch_properties': 'light_indicator.on',
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
        **ENERGY_KWH,
        'value_ratio': 0.01,
    },
    'zimi.plug.*:power_cost_month': {
        **ENERGY_KWH,
        'value_ratio': 0.01,
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
    'zimi.powerstrip.*:store.powerCost:today': ENERGY_KWH,
    'zimi.powerstrip.*:store.powerCost:month': ENERGY_KWH,
    'zimi.waterheater.h01': {
        'sensor_properties': 'water_heater.status,water_level,temperature_tips,'
                             'input_water_temp,water_pump_volt,remaining_time',
        'switch_properties': 'on,hot_water_recirculation,heat_preservation,jog_function,pressure_boost.status,'
                             'cloud_preheater,in_cloud_timer,water_trigger,reminder,enhanced',
        'select_properties': 'effective,model',
        'number_properties': 'target_temperature,light_off_time,children_mode_temp,comfort_mode_temp,adult_mode_temp,'
                             'kitchen_mode_temp,pet_mode_temp,custom_time,boost_value',
    },
    'zinguo.switch.b5m': {
        'sensor_properties': 'temperature',
        'switch_properties': 'heating,blow,ventilation',
        'select_properties': 'link',
        'light_services': 'light',
    },

    '*.aircondition.*': {
        'sensor_properties': 'electricity.electricity',
        'switch_properties': 'air_conditioner.on,uv,heater,eco,dryer,sleep_mode,soft_wind,'
                             'horizontal_swing,vertical_swing,alarm.alarm',
        'select_properties': 'fan_level',
        'number_properties': 'target_humidity',
        'fan_services': 'air_fresh',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,mode,target_temperature,fan_level'},
        ],
    },
    '*.airer.*': {
        'interval_seconds': 60,
        'position_reverse': True,
        'sensor_properties': 'left_time',
        'switch_properties': 'dryer,uv',
        'select_properties': 'drying_level',
        'chunk_coordinators': [
            {'interval': 15, 'props': 'status,current_position,target_position,dryer,drying_level'},
        ],
    },
    '*.airrtc.*': {
        'switch_properties': 'air_conditioner.on',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,mode,target_temperature,fan_level'},
        ],
    },
    '*.airpurifier.*': {
        'switch_properties': 'air_purifier.on,alarm.alarm,anion,uv',
        'sensor_properties': 'relative_humidity,pm2_5_density,temperature,filter_life_level',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,mode,fan_level'},
        ],
    },
    '*.bhf_light.*': {
        'sensor_properties': 'temperature',
        'switch_properties': 'heating,blow,ventilation,dryer',
        'select_properties': 'mode',
        'number_properties': 'target_temperature,off_delay_time',
        'button_actions': 'stop_working',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,mode,target_temperature,fan_level'},
        ],
    },
    '*.blanket.*': {
        'sensor_properties': 'temperature',
        'select_properties': 'mode,heat_level,water_level',
        'number_properties': 'target_temperature',
    },
    '*.camera.*': {
        'miot_cloud_action': True,
        'sensor_properties': 'memory_card_management.status,storage_free_space,storage_used_space',
        'select_properties': 'night_shot,recording_mode,detection_sensitivity',
        'switch_properties': 'on,time_watermark,motion_tracking,motion_detection,wdr_mode,glimmer_full_color',
        'number_properties': 'image_rollover,alarm_interval',
    },
    '*.cateye.*': {
        'use_motion_stream': True,
    },
    '*.chair.*': {
        'binary_sensor_properties': 'seating_state',
        'switch_properties': 'on',
        'select_properties': 'mode',
    },
    '*.cooker.*': {
        'sensor_properties': 'temperature,left_time',
        'switch_properties': 'on,auto_keep_warm',
        'button_actions': 'pause,cancel_cooking',
        'select_actions': 'start_cook',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,status'},
        ],
    },
    '*.curtain.*': {
        'interval_seconds': 60,
        'switch_properties': 'motor_reverse',
        'select_properties': 'mode',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'status,current_position,target_position'},
        ],
    },
    '*.derh.*': {
        'select_properties': 'fan_level',
    },
    '*.desk.*': {
        'button_properties': 'motor_control,reset',
        'switch_properties': 'on',
        'select_properties': 'mode,desk_control',
        'number_properties': 'altitude,target_height,stand_height,sit_height,target_position',
    },
    '*.dishwasher.*': {
        'sensor_properties': 'temperature,left_time,door_state,soft_water_salt,tds',
        'switch_properties': 'on,dryer,auto_dryer',
        'select_properties': 'mode',
        'button_actions': 'start_wash,pause,stop_washing',
    },
    '*.door.*': {},
    '*.dry.*': {
        'sensor_properties': 'temperature,left_time',
        'switch_properties': 'on,uv',
        'select_properties': 'mode,drying_level',
        'number_properties': 'drying_time,delaytime',
        'button_actions': 'start_drying,pause',
    },
    '*.dryer.*': {},
    '*.f_washer.*': {
        'sensor_properties': 'left_time,water',
        'switch_properties': 'on',
        'number_select_properties': 'wash_mode,wash_time,target_water_level,water_level',
    },
    '*.fan.*': {
        'button_actions': 'turn_left,turn_right',
        'number_properties': 'off_delay_time',
        'switch_properties': 'fan_init_power_opt',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,mode,fan_level'},
        ],
    },
    '*.fishbowl.*': {
        'select_actions': 'pet_food_out',
        'sensor_properties': 'temperature,tds_in,tds_out',
        'switch_properties': 'water_pump,automatic_feeding,heating',
        'number_properties': 'target_temperature,pump_flux,target_feeding_measure,'
                             'ambient_light_custom.stream,ambient_light_custom.speed',
    },
    '*.foot_bath.*': {
        'sensor_properties': 'temperature,left_time,fold_status,water_level_status',
        'switch_properties': 'foot_massage,constant_temperature_heating',
        'select_properties': 'heat_level,motor_control',
        'number_properties': 'target_time,target_temperature',
    },
    '*.fridge.*': {
        'switch_properties': 'on',
        'number_properties': 'target_temperature',
    },
    '*.health_pot.*': {
        'button_actions': 'cancel_cooking',
    },
    '*.heater.*': {
        'switch_properties': 'heater.on,horizontal_swing,alarm.alarm,delay.delay',
        'number_properties': 'countdown_time,delay_time',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,mode,target_temperature,fan_level'},
        ],
    },
    '*.humidifier.*': {
        'interval_seconds': 120,
        'select_properties': 'fan_level',
        'chunk_coordinators': [
            {'interval': 20, 'props': 'on,mode,target_humidity,fan_level'},
            {'interval': 25, 'props': 'relative_humidity,temperature'},
            {'interval': 300, 'props': 'filter_life_level,filter_left_time,filter_used_time'},
        ],
    },
    '*.ihcooker.*': {
        'sensor_properties': 'left_time,working_time,temperature',
        'switch_properties': 'induction_cooker.on',
        'number_properties': 'heat_level',
        'button_actions': 'start_cook,pause,cancel_cooking',
    },
    '*.light.*': {
        'number_properties': 'off_delay_time',
        'switch_properties': 'init_power_opt,fan_init_power_opt',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,brightness,color_temperature,color,mode'},
        ],
    },
    '*.litter_box.*': {
        'sensor_properties': 'usage_count,trash_can_status',
        'switch_properties': 'auto_cleanup',
        'button_actions': 'start_clean',
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
    '*.magnet.*': {
        'binary_sensor_properties': 'contact_state',
        'sensor_properties': 'illumination',
    },
    '*.microwave.*': {
        'sensor_properties': 'left_time,heat_level,cook_time',
    },
    '*.mosq.*': {
        'sensor_properties': 'repellent_left_level,liquid_left',
        'select_properties': 'mode',
    },
    '*.motion.*': {
        'sensor_properties': 'illumination,no_motion_duration',
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
    '*.plantmonitor.*': {
        'sensor_properties': 'soil_ec,illumination,temperature,relative_humidity',
    },
    '*.plug.*': {
        'interval_seconds': 60,
        'chunk_coordinators': [
            {'interval': 10, 'props': 'switch.on,electric_power'},
        ],
    },
    '*.s_lamp.*': {
        'sensor_properties': 'left_time',
        'switch_properties': 'uv,radar_on,lighting.on',
        'number_properties': 'target_time',
    },
    '*.senpres.*': {
        'binary_sensor_properties': 'pressure_present_state',
        'sensor_properties': 'pressure_not_present_duration',
    },
    '*.sensor_occupy.*': {
        'sensor_properties': 'illumination,has_someone_duration,no_one_duration',
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
    '*.switch.*': {
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on'},
        ],
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
    '*.vacuum.*': {
        'binary_sensor_properties': 'mop_status',
        'sensor_properties': 'status,cleaning_area,cleaning_time,mop_life_level,brush_life_level,filter_life_level,'
                             'dust_bag_life_level',
        'select_properties': 'mode,sweep_mop_type,sweep_type,clean_times',
        'number_properties': 'volume',
        'button_actions': 'start_sweep,stop_sweeping,stop_and_gocharge,start_only_sweep,start_mop,start_sweep_mop,'
                          'pause_sweeping,continue_sweep,start_dust_arrest,start_mop_wash,start_dry,start_eject,'
                          'stop_mop_wash,stop_dry,back_mop_wash,start_charge,identify,'
                          'reset_mop_life,reset_brush_life,reset_filter_life,reset_dust_bag_life',
        'configuration_entities': 'reset_mop_life,reset_brush_life,reset_filter_life,reset_dust_bag_life',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'status,cleaning_area,cleaning_time,charging_state', 'notify': True},
            {'interval': 15, 'props': 'mode,sweep_mop_type,sweep_type,clean_times'},
        ],
    },
    '*.walkingpad.*': {
        'sensor_properties': 'current_distance,current_step_count,current_calorie_consumption,'
                             'left_distance,left_time,working_time',
        'number_properties': 'target_distance,target_time',
        'select_properties': 'mode',
        'number_select_properties': 'speed_level',
    },
    '*.washer.*': {
        'button_actions': 'start_wash,pause,stop_washing',
        'sensor_properties': 'fault,run_status,left_time,door_state',
        'switch_properties': 'on,sleep_mode,steam_sterilization,ai_mode,high_water_switch,one_click_wash',
        'select_properties': 'mode,drying_level,rinsh_times,drying_degree',
        'number_select_properties': 'target_temperature,spin_speed,soak_time,wash_time,drying_time',
    },
    '*.waterheater.*': {
        'sensor_properties': 'water_velocity,tds_in,tds_out',
        'switch_properties': 'water_heater.on,preheating,cruise_press',
    },
    '*.waterpuri.*': {
        'sensor_properties': 'water_purifier.temperature,tds_in,tds_out',
    },

}

DEVICE_CUSTOMIZES.update({
    '*.airp.*': DEVICE_CUSTOMIZES.get('*.airpurifier.*') or {},
    '*.door.*': DEVICE_CUSTOMIZES.get('*.lock.*') or {},
    '*.dryer.*': DEVICE_CUSTOMIZES.get('*.dry.*') or {},
    '*.pre_cooker.*': DEVICE_CUSTOMIZES.get('*.cooker.*') or {},
})


GLOBAL_CONVERTERS = [
    {
        'class': MiotSwitchConv,
        'services': [
            'switch', 'outlet', 'massager', 'towel_rack', 'diffuser', 'fish_tank',
            'pet_drinking_fountain', 'mosquito_dispeller', 'electric_blanket', 'foot_bath',
        ],
    },
    {
        'class': MiotSensorConv,
        'services': [
            'cooker', 'induction_cooker', 'pressure_cooker', 'oven', 'microwave_oven',
            'health_pot', 'coffee_machine', 'multifunction_cooking_pot',
            'air_fryer', 'juicer', 'electric_steamer',
        ],
        'kwargs': {'main_props': ['status'], 'desc': True},
        'converters' : [
            {'props': ['fault'], 'desc': True},
        ],
    },
    {
        'class': MiotSensorConv,
        'services': ['water_purifier', 'dishwasher', 'fruit_vegetable_purifier'],
        'kwargs': {'main_props': ['status', 'fault'], 'desc': True},
    },
    {
        'class': MiotSensorConv,
        'services': ['printer', 'vibration_sensor', 'router'],
        'kwargs': {'main_props': ['status'], 'desc': True},
    },
    {
        'class': MiotSensorConv,
        'services': ['pet_feeder', 'cat_toilet', 'cat_litter'],
        'kwargs': {'main_props': ['status'], 'desc': True},
    },
    {
        'class': MiotSensorConv,
        'services': ['washer'],
        'kwargs': {'main_props': ['status', 'run_status'], 'desc': True},
    },
    {
        'class': MiotSensorConv,
        'services': ['plant_monitor'],
        'kwargs': {'main_props': ['status'], 'desc': True},
        'converters' : [
            {'props': ['fault'], 'desc': True},
            {'props': ['soil_ec', 'illumination'], 'domain': 'sensor'},
        ],
    },
    {
        'class': MiotSensorConv,
        'services': ['gas_sensor'],
        'kwargs': {'main_props': ['gas_concentration', 'status'], 'desc': True},
    },
    {
        'class': MiotSensorConv,
        'services': ['occupancy_sensor'],
        'kwargs': {'main_props': ['occupancy_status'], 'desc': True},
    },
    {
        'class': MiotSensorConv,
        'services': ['pressure_sensor'],
        'kwargs': {'main_props': ['pressure_present_duration', 'status'], 'desc': True},
    },
    {
        'class': MiotSensorConv,
        'services': ['sleep_monitor'],
        'kwargs': {'main_props': ['sleep_state', 'status'], 'desc': True},
    },
    {
        'class': MiotSensorConv,
        'services': ['smoke_sensor'],
        'kwargs': {'main_props': ['smoke_concentration', 'status'], 'desc': True},
    },
    {
        'class': MiotLightConv,
        'services': ['light'],
        'converters' : [
            {'props': ['brightness'], 'class': MiotBrightnessConv},
            {'props': ['color_temperature', 'color_temp'], 'class': MiotColorTempConv},
            {'props': ['color'], 'class': MiotRgbColorConv},
            {'props': ['mode'], 'desc': True},
        ],
    },
    {
        'class': MiotLightConv,
        'services': ['night_light', 'ambient_light', 'plant_light', 'light_bath_heater'],
        'converters' : [
            {'props': ['brightness'], 'class': MiotBrightnessConv},
            {'props': ['color_temperature', 'color_temp'], 'class': MiotColorTempConv},
            {'props': ['color'], 'class': MiotRgbColorConv},
            {'props': ['mode'], 'desc': True},
        ],
    },
    {
        'class': MiotLightConv,
        'services': ['indicator_light'],
        'kwargs': {
            'main_props': ['on', 'switch', 'brightness'],
            'option': {'entity_category': 'config'},
        },
        'converters' : [
            {'props': ['brightness'], 'class': MiotBrightnessConv},
            {'props': ['mode'], 'desc': True},
        ],
    },
    {
        'class': MiotCoverConv,
        'services': ['airer', 'curtain', 'window_opener', 'motor_controller'],
        'converters' : [
            {'props': ['status', 'motor_control', 'current_position']},
            {'props': ['target_position'], 'class': MiotTargetPositionConv},
        ],
    },
    {
        'services': ['alarm'],
        'converters' : [
            {
                'props': ['alarm'],
                'domain': 'switch',
                'option': {'entity_category': 'config'},
            },
        ],
    },
    {
        'services': ['physical_control_locked', 'physical_controls_locked'],
        'converters' : [
            {
                'props': ['physical_control_locked', 'physical_controls_locked'],
                'domain': 'switch',
                'option': {'entity_category': 'config'},
            },
        ],
    },
    {
        'services': ['tds_sensor'],
        'converters' : [
            {'props': ['tds_in', 'tds_out'], 'domain': 'sensor'},
        ],
    },
    {
        'services': ['filter', 'filter_life'],
        'converters' : [
            {
                'props': [
                    'filter_life', 'filter_life_level',
                    'filter_left_time', 'filter_used_time',
                    'filter_left_flow', 'filter_used_flow',
                ],
                'domain': 'sensor',
            },
        ],
    },
    {
        'services': ['brush_cleaner'],
        'converters' : [
            {'props': ['brush_life_level', 'brush_left_time'], 'domain': 'sensor'},
        ],
    },
    {
        'services': ['environment', 'temperature_humidity_sensor'],
        'converters' : [
            {
                'props': [
                    'temperature', 'indoor_temperature', 'relative_humidity', 'humidity',
                    'pm2_5_density', 'pm10_density', 'co2_density', 'tvoc_density', 'hcho_density',
                    'air_quality', 'air_quality_index', 'illumination', 'atmospheric_pressure',
                ],
                'domain': 'sensor',
            },
        ],
    },
    {
        'services': ['illumination_sensor', 'motion_sensor'],
        'converters' : [
            {'props': ['illumination'], 'domain': 'sensor'},
        ],
    },
    {
        'services': ['battery', 'power_consumption', 'electricity'],
        'converters' : [
            {
                'props': [
                    'battery_level', 'electric_power', 'electric_current',
                    'voltage', 'leakage_current', 'surge_power',
                ],
                'domain': 'sensor',
            },
            {'props': ['charging_state'], 'domain': 'sensor', 'desc': True},
        ],
    },
    {
        'services': ['router', 'wifi', 'guest_wifi'],
        'converters' : [
            {'props': ['on'], 'domain': 'switch'},
            {
                'props': [
                    'download_speed', 'upload_speed', 'connected_device_number', 'network_connection_type',
                    'ip_address', 'online_time', 'wifi_ssid', 'wifi_bandwidth',
                ],
                'domain': 'sensor',
            },
        ],
    },
]
