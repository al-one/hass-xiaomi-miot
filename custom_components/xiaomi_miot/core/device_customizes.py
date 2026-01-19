"""
This is a device customization built into the component, `DEVICE_CUSTOMIZES` is for device model customization.
Through these customizations, you can expand the functionality of the device in HA, such as:
- `sensor_properties`/`switch_properties` etc. can map miot attributes to entities, which is very useful when the device lacks an entity
- `exclude_miot_properties` can exclude redundant miot attributes, as some devices may become unresponsive due to polling too many attributes
- `chunk_coordinators` can group poll different attributes, which can synchronize the device's key attributes faster

More customization options can be found at https://github.com/al-one/hass-xiaomi-miot/issues/600.
If you want to change these customizations, you should prioritize defining them through the configuration stream (issues/600) or the `configuration.yaml` configuration file.
Assuming one of your devices lacks a temperature and humidity sensor, you can first find the corresponding attribute name on the website home.miot-spec.com and configure it in the following format:
```yaml
# configuration.yaml
xiaomi_miot:
  device_customizes:
    your.device.model: # <-- replace it
      sensor_properties: temperature,relative_humidity
      switch_properties: uv,switch
      select_properties: mode
```
It is worth noting:
- The `-` in miot property names needs to be replaced with `_`
- Your configuration will override the built-in customizations of the component
"""

from .converters import *

CHUNK_1 = {
    'chunk_properties': 1,
}

ENERGY_KWH = {
    'state_class': 'total_increasing',
    'device_class': 'energy',
    'unit_of_measurement': 'kWh',
}

ENERGY_AC_0801 = {
    'stat_power_cost_type': 'total_day',
    'stat_power_cost_key': '8.1',
    'sensor_attributes': 'power_cost_today,power_cost_month',
}

ENERGY_AC_2001 = {
    'stat_power_cost_type': 'stat_day_v3',
    'stat_power_cost_key': '20.1',
    'sensor_attributes': 'power_cost_today,power_cost_month',
}


DEVICE_CUSTOMIZES = {
    '090615.aircondition.ktf': {
        'current_temp_property': 'setmode.roomtemp',
        'append_converters': [
            {
                'class': MiotClimateConv,
                'services': ['air_conditioner'],
                'converters': [{'props': ['setmode.roomtemp']}],
            }
        ],
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
    '090615.switch.x6wtft': {
        'select_properties': 'mode,default_power_on_state',
        'text_properties': 'name,diy_words',
        'exclude_miot_services': 'scene,location',
        'chunk_coordinators': [
            {'interval': 11, 'props': 'switch.on'},
            {'interval': 21, 'props': 'light.*,diy_words'},
            {'interval': 31, 'props': 'air_conditioner.*'},
            {'interval': 61, 'props': 'environment.*'},
            {'interval': 91, 'props': 'indicator_light.*'},
            {'interval': 180, 'props': 'mode,name,default_power_on_state'},
        ],
    },

    'adp.motor.adswb4': {
        'button_actions': 'toggle',
        'sensor_properties': 'battery_percentage,charging_status,total_movement',
        'switch_properties': 'motor_control,switch_invert,click,adaptive_movement,ad_switch',
        'select_properties': 'mode',
        'number_properties': 'rotate_angle,sustain_time,resistance',
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
    'aupu.bhf_light.a3spro': {
        'sensor_properties': 'fault,left_time,count_down',
        'switch_properties': 'external_light,night_light',
        'select_properties': 'mode,ventilate_gear',
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
    'babai.curtain.cmb5': {
        'interval_seconds': 180,
        'select_properties': 'mode,speed_level',
        'exclude_miot_properties': 'fault,speedselect',
        'chunk_coordinators': [
            {'interval': 30, 'props': 'current_position,target_position'},
        ],
    },
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
    'careco.evc.*': {
        'button_actions': 'start_charge,stop_charge',
        'sensor_properties': 'status,4g_signal,electric_power,electric_current,charged_quantity,fault',
        'switch_properties': 'timer_on,full_charge,authorize_mode,auto_upgrade',
        'number_properties': 'maximum_current_regulation',
    },
    'careco.evc.*:electric_power': {
        'state_class': 'measurement',
        'device_class': 'power',
    },
    'careco.evc.*:charged_quantity': ENERGY_KWH,
    'careco.evc.a07b01': {
        'select_properties': 'lock_status',
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
    'cddz.switch.jhicw': {
        'switch_properties': 'switch,one_key,two_key,three_key,four_key',
        'select_properties': 'mode,default_power_on_state',
        'number_properties': 'backlighting_br',
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
        'interval_seconds': 180,
        'select_properties': 'monitoring_frequency,screen_off,device_off,screensaver_type',
        'number_properties': 'screensaver_time,auto_slideing_time',
        'exclude_miot_services': 'mac',
        'exclude_miot_properties': 'start_time,end_time,tempature_unit,time_zone,page_sequence,*_led_th',
        'chunk_coordinators': [
            {'interval': 51, 'props': 'pm2_5_density,pm10_density,co2_density'},
            {'interval': 61, 'props': 'relative_humidity,temperature'},
            {'interval': 71, 'props': 'battery_level,charging_state,voltage'},
            {'interval': 121, 'props': 'monitoring_frequency,screen_off,device_off'},
            {'interval': 131, 'props': 'screensaver_type,screensaver_time,auto_slideing_time'},
        ],
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
    'cgllc.sensor_ht.dk2': {
        'sensor_properties': 'battery_level',
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
    'chunmi.health_pot.*': {
        'sensor_properties': 'fault,left_time,temperature,kw_temperature,ctrl_temperature,power_value,cook_mode,'
                             'cook_total_time,kw_left_time,kw_total_time,pre_left_time,cur_left_time',
        'switch_properties': 'auto_keepwarm',
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
    'chunmi.oven.s1': {
        'sensor_properties': 'status,fault,left_time,temperature,cook_time',
        'button_actions': 'start_cooke,cancel_cooking,pause',
        'select_properties': 'cook_mode',
        'number_properties': 'target_temperature',
    },
    'chunmi.pre_cooker.mini1': {
        'button_actions': 'cancel_cooking',
        'select_actions': 'start_cook',
        'binary_sensor_properties': 'cover_state,cook_finish_flag',
        'sensor_properties': 'status,left_time,temperature,cook_time,taste,cook_status,press_status,error_code',
        'switch_properties': 'finish_push',
    },
    'cokit.mosq.coq5': {
        'sensor_properties': 'replace_fluid',
        'switch_properties': 'on',
        'slectt_properties': 'timer',
        'button_properties': 'reset',
    },
    'cubee.airrtc.th123e': {
        'sensor_properties': 'tempfloor',
        'current_temp_property': 'tempfloor',
        'append_converters': [
            {
                'class': MiotClimateConv,
                'services': ['thermostat'],
                'converters': [{'props': ['heatold.tempfloor']}],
            }
        ],
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
    'cuco.plug.co3d': {
        'binary_sensor_properties': 'temp_over,current_over',
        'switch_properties': 'light,mode',
        'select_properties': 'memory',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '8.1',
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
        'chunk_coordinators': [
            {'interval': 21, 'props': 'prop.2.*'},
            {'interval': 23, 'props': 'prop.3.*'},
            {'interval': 25, 'props': 'prop.4.*'},
            {'interval': 27, 'props': 'prop.5.*'},
            {'interval': 29, 'props': 'prop.6.*'},
            {'interval': 31, 'props': 'prop.7.*'},
        ],
    },
    'cuco.plug.cp5prd': {
        'exclude_miot_services': 'device_setting,use_ele_alert',
        'exclude_miot_properties': 'power_consumption,electric_current,voltage,temperature_high_ai,temperature_high_ci,'
                                   'indicator_light.mode,start_time,end_time,data_values',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '10.1',
        'chunk_coordinators': [
            {'interval': 21, 'props': 'prop.2.*'},
            {'interval': 23, 'props': 'prop.3.*'},
            {'interval': 25, 'props': 'prop.4.*'},
            {'interval': 27, 'props': 'prop.5.*'},
            {'interval': 29, 'props': 'prop.6.*'},
            {'interval': 31, 'props': 'prop.7.*'},
        ],
    },
    'cuco.plug.cp5prd:power_cost_today': {'value_ratio': 1},
    'cuco.plug.cp5prd:power_cost_month': {'value_ratio': 1},
    'cuco.plug.cp5pro': {
        'exclude_miot_services': 'power_consumption,device_setting,use_ele_alert',  # issues/763
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '10.1',
        'chunk_coordinators': [
            {'interval': 21, 'props': 'prop.2.*'},
            {'interval': 23, 'props': 'prop.3.*'},
            {'interval': 25, 'props': 'prop.4.*'},
            {'interval': 27, 'props': 'prop.5.*'},
            {'interval': 29, 'props': 'prop.6.*'},
            {'interval': 31, 'props': 'prop.7.*'},
        ],
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
        'chunk_coordinators': [
            {'interval': 21, 'props': 'prop.2.*'},
            {'interval': 23, 'props': 'prop.3.*'},
            {'interval': 25, 'props': 'prop.4.*'},
            {'interval': 27, 'props': 'prop.5.*'},
            {'interval': 29, 'props': 'prop.6.*'},
            {'interval': 31, 'props': 'prop.7.*'},
        ],
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
        'sensor_properties': 'electric_power,fault,temperature',
        'switch_properties': 'on,cycle.status',
        'number_properties': 'charging_protection.power,protect_time,max_power_limit.power,charge_prt_ext.power'
                             'duration,over_ele_day,over_ele_month,power_ext',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '11.1',
        'chunk_coordinators': [
            {'interval': 16, 'props': 'switch.on'},
            {'interval': 51, 'props': 'electric_power,temperature'},
            {'interval': 71, 'props': 'prop.3.*,prop.4.*'},
            {'interval': 81, 'props': 'prop.8.*,prop.9.*'},
            {'interval': 91, 'props': 'prop.10.*,prop.12.*,prop.14.*,prop.15.*'},
        ],
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
    'deerma.humidifier.jsq': {
        'chunk_properties': 1,
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
        'chunk_coordinators': [
            {'interval': 30, 'props': 'humidifier.on,mode,target_humidity,fan_level'},
            {'interval': 300, 'props': 'filter_life_level,filter_left_time,filter_used_time'},
        ],
    },
    'degree.lunar.smh013': {
        'exclude_miot_properties': 'search_report,set_sleep_time,user_info,user_info_down,set_sleep_time_down,'
                                   'fast_update_switch,linkage_sleepstage,linkage_warning,gen_report,'
                                   'search_report_today',
        'sensor_properties': 'realtime_heart_rate,realtime_breath_rate,realtime_sleepstage',
        'switch_properties': 'fast_update_switch',
    },
    'devcea.light.ls2307': {
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
    'dmaker.fan.p5c': {
        'button_actions': 'turn_left,turn_right,toggle_mode,loop_gear',
        'number_properties': 'off_delay_time',
    },
    'dmaker.fan.p11': {
        'percentage_property': 'fan.status',  # issues/838
        'append_converters': [
            {
                'class': MiotFanConv,
                'services': ['fan'],
                'converters': [{'props': ['fan.status']}],
            },
        ],
    },
    'dmaker.fan.p15': {
        'percentage_property': 'fan.status',
        'append_converters': [
            {
                'class': MiotFanConv,
                'services': ['fan'],
                'converters': [{'props': ['fan.status']}],
            },
        ],
    },
    'dmaker.fan.p18': {
        'button_actions': 'toggle_mode,loop_gear',
        'button_properties': 'motor_control',
        'switch_properties': 'brightness,alarm',
        'select_properties': 'fan_level,horizontal_angle',
        'number_properties': 'speed_level,off_delay_time',
    },
    'dmaker.fan.p23': {
        'button_actions': 'toggle,toggle_mode,loop_gear',
        'switch_properties': 'on,heating,horizontal_swing,symmetrical_swing,alarm',
        'select_properties': 'fan.mode,swing_lr_manual',
        'number_properties': 'target_temperature,left_angle,right_angle,off_delay_time',
    },
    'dmaker.fan.p28': {
        'switch_properties': 'alarm,horizontal_swing,vertical_swing,swing_all,off_to_center',
        'button_properties': 'swing_updown_manual,swing_lr_manual,back_to_center,start_left,start_right,start_up,start_down',
    },
    'dmaker.fan.p33': {
        'select_properties': 'motor_control',
        'open_texts': 'LEFT',
        'close_texts': 'RIGHT',
        'percentage_property': 'fan.status',
        'append_converters': [
            {
                'class': MiotFanConv,
                'services': ['fan'],
                'converters': [{'props': ['fan.status']}],
            },
        ],
    },
    'dmaker.fan.p39': {
        'switch_properties': 'brightness',
        'select_properties': 'motor_control',
        'button_actions': 'toggle,loop_gear,loop_mode',
    },
    'dmaker.fan.p45': {
        'button_actions': 'turn_left,turn_right',
    },
    'dmaker.fan.*': {
        'interval_seconds': 90,
        'switch_properties': 'alarm,horizontal_swing,vertical_swing',
        'number_select_properties': 'horizontal_swing_included_angle,horizontal_angle,'
                                    'vertical_swing_included_angle,vertical_angle',
        'number_properties': 'off_delay_time',
        'exclude_miot_properties': 'natural_*',
        'chunk_coordinators': [
            {'interval': 16, 'props': 'on,mode,fan_level,speed_level'},
            {'interval': 21, 'props': 'off_delay_time,horizontal_swing*'},
        ],
        'append_converters': [
            {
                'class': MiotFanConv,
                'services': ['fan'],
                'converters': [{'props': ['dm_service.speed_level']}],
            }
        ],
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

    'hfjh.fishbowl.v2': {
        'switch_properties': 'water_pump,ledboard_time_switch,feed_time_switch,key_switch',
        'select_properties': 'ledboard_model',
        'number_properties': 'ledboard_brightness,ledboard_sun,ledboard_color,ledboard_stream,ledboard_speed,'
                             'pump_flux,feed_num',
        'select_actions': 'set_feed_single',
        'power_property': 'fish_tank.on',
        'mode_property': 'ledboard_model',
        'brightness_property': 'ledboard_brightness',
        'color_property': 'ledboard_color',
        'append_converters': [
            {
                'class': MiotLightConv,
                'services': ['fish_tank'],
                'converters' : [
                    {'props': ['ledboard_brightness'], 'class': MiotBrightnessConv},
                    {'props': ['ledboard_color'], 'class': MiotRgbColorConv},
                ],
            },
        ],
    },
    'hfjh.fishbowl.m100': {
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
        **CHUNK_1,
        'number_properties': 'target_position,drying_time',
        'append_converters': [
            {
                'class': MiotCoverConv,
                'services': ['airer'],
                'converters': [{'props': ['prop.2.11']}],
            }
        ],
        'disable_target_position': True,
        'cover_position_mapping': {},
    },
    'hyd.airer.pro': {
        'switch_properties': 'mode,nightlight_switch',
        'number_properties': 'brightness,upper_limit,lower_limit',
        'append_converters': [
            {
                'class': MiotCoverConv,
                'services': ['airer'],
                'converters': [{'props': ['*.current_position', '*.set_position']}],
            }
        ],
        'target_position_props': 'set_position',
        'cover_position_mapping': None,
    },
    'hyd.airer.pro2': {
        'switch_properties': 'mode,nightlight_switch',
        'select_properties': None,
        'number_properties': 'brightness,upper_limit,lower_limit',
        'append_converters': [
            {
                'class': MiotCoverConv,
                'services': ['airer'],
                'converters': [{'props': ['*.current_position', '*.set_position']}],
            }
        ],
        'target_position_props': 'set_position',
        'cover_position_mapping': None,
    },
    'hyd.airer.znlyj2': {
        **CHUNK_1,
        'cover_position_mapping': {0: 50, 1: 100, 2: 0},
    },
    'hyd.airer.znlyj4': {
        'cover_position_mapping': {0: 50, 1: 100, 2: 0},
    },
    'hyd.airer.znlyj5': {
        'cover_position_mapping': {0: 50, 1: 100, 2: 0},
    },
    'hyd.airer.*': {
        'switch_properties': 'uv',
        'select_properties': 'mode,dryer',
        'number_properties': 'drying_time',
        'exclude_miot_properties': 'motor_control',
        'cover_position_mapping': {0: 50, 1: 100, 2: 0},
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
        'interval_seconds': 120,
        'button_actions': 'start_sweep*,start_only_sweep,start_mop,start_charge,stop_*',
        'sensor_properties': 'vacuum.status,door_state,main_brush_life,side_brush_life,hypa_life,mop_life',
        'switch_properties': 'repeat_state,alarm',
        'select_properties': 'mode,sweep_type,suction_state,water_state',
        'exclude_miot_services': 'order',
        'exclude_miot_properties': 'vacuum.on,*_points,multi_prop_vacuum,cur_cleaning_path,consumablesinfo,'
                                   'dnd_start_*,dnd_end_*',
        'chunk_coordinators': [
            {'interval': 31, 'props': 'status,mode'},
            {'interval': 41, 'props': 'sweep_type,suction_state'},
            {'interval': 51, 'props': 'water_state,repeat_state,mop_route'},
            {'interval': 71, 'props': 'ai_recognize,dirt_recognize,pet_recognize,cloth_state'},
            {'interval': 81, 'props': 'remember_state,cur_map_id,build_map,has_new_map'},
            {'interval': 91, 'props': 'alarm,volume,door_state,cleaning_time,cleaning_area,carpet_booster'},
            {'interval': 131, 'props': 'battery_level,tank_shake,shake_shift,map_encrypt,target_point'},
            {'interval': 300, 'props': 'main_brush_*,side_brush_*,hypa_*,mop_life,mop_hours,map_num'},
            {'interval': 999, 'props': 'time_zone,cur_lang,multi_prop_vacuum'},
        ],
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
    'iot.plug.pw6u1': {
        'sensor_properties': 'fault',
        'switch_properties': '*_switch.on,child_lock',
        'select_properties': 'default_power_on_state',
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '3.1',
        'exclude_miot_properties': 'indicator_set,circle_task_*',
        'chunk_coordinators': [
            {'interval': 16, 'props': 'switch.on'},
            {'interval': 21, 'props': '*_switch.on,electric_power'},
        ],
    },
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
        'sensor_properties': 'occupancy_status,illumination,distance,has_someone_duration,no_one_duration',
        'switch_properties': 'led_enable',
        'number_properties': 'no_one_determine_time,detect_range,enterin_confirm_time',
    },
    'izq.sensor_occupy.solo': {
        'sensor_properties': 'occupancy_status,illumination',
        'number_properties': 'bio_sensitive',
        'switch_properties': 'shadow_tracking',
        'button_actions': 'led_toggle,find_device,reset_occupy_state',
        'chunk_coordinators': [
            {'interval': 3, 'props': 'occupancy_status,illumination'},
        ],
    },
    'izq.sensor_occupy.trio': {
        'sensor_properties': 'occupancy_status,illumination',
        'number_properties': 'bio_sensitive',
        'switch_properties': 'shadow_tracking',
        'button_actions': 'led_toggle,find_device,reset_occupy_state',
        'chunk_coordinators': [
            {'interval': 3, 'props': 'occupancy_status,illumination'},
        ],
    },
    'jipin.blanket.tt7xxa': {
        **CHUNK_1,
        'interval_seconds': 90,
        'sensor_properties': 'left_time',
        'switch_properties': 'left_speed_hot,right_speed_hot,anti_acne',
        'number_properties': 'timer,left_gears,right_gears',
    },
    'jyf.tow_w.ts03': {
        'auto_cloud': True,
        'interval_seconds': 120,
        'exclude_miot_properties': 'mode,fault',
        'chunk_coordinators': [
            {'interval': 31, 'props': 'on'},
            {'interval': 41, 'props': 'target_temperature'},
            {'interval': 51, 'props': 'temperature'},
            {'interval': 61, 'props': 'left_time'},
        ],
    },
    'leishi.bhf_light.lsyb01': {
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
    'lemesh.switch.sw0c01': {
        'chunk_coordinators': [
            {'interval': 20, 'props': 'on'},
        ],
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
        'append_converters': [
            {
                'class': MiotLightConv,
                'services': ['vd_light_a', 'vd_light_b', 'vd_light_c'],
                'converters' : [
                    {'props': ['brightness'], 'class': MiotBrightnessConv},
                    {'props': ['color_temperature'], 'class': MiotColorTempConv},
                    {'props': ['color'], 'class': MiotRgbColorConv},
                    {'props': ['color_mode'], 'desc': True},
                ],
            },
        ],
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
        'interval_seconds': 120,
        'sensor_properties': 'electric_power',
        'switch_properties': 'on,vertical_swing,quick_cool_enable,indicator_light',
        'select_properties': 'fan_level,ac_mode',
        'miio_cloud_props': [],
        'stat_power_cost_type': 'stat_day_v3',
        'stat_power_cost_key': '7.1,7.3',
        'sensor_attributes': 'power_cost_today,power_cost_month,power_cost_today_2,power_cost_month_2',
        'configuration_entities': 'ac_mode,indicator_light',
        'exclude_miot_services': 'device_protect,device_info',
        'exclude_miot_properties': 'fault,set_ele_info,sleep_cfg',
        'chunk_coordinators': [
            {'interval': 11, 'props': 'on,mode,target_temperature'},
            {'interval': 16, 'props': 'fan_level,vertical_swing'},
            {'interval': 26, 'props': 'electric_power'},
            {'interval': 500, 'props': 'brand_id,remote_id,ac_ctrl_range,ac_state'},
        ],
    },
    'lumi.acpartner.mcn04:power_consumption': ENERGY_KWH,
    'lumi.acpartner.mcn04:power_cost_today': {'value_ratio': 1, **ENERGY_KWH},
    'lumi.acpartner.mcn04:power_cost_month': {'value_ratio': 1, **ENERGY_KWH},
    'lumi.acpartner.mcn04:power_cost_today_2': ENERGY_KWH,
    'lumi.acpartner.mcn04:power_cost_month_2': ENERGY_KWH,
    'lumi.acpartner.v2': {
        'cloud_set_single': True,
    },
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
        'sensor_attributes': 'power_cost_today,power_cost_month',
        'stat_power_cost_key': '3.1',
    },
    'lxzn.switch.cbcsmj:voltage': {'value_ratio': 0.1},
    'lxzn.switch.cbcsmj:electric_current': {'value_ratio': 0.001},

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
    'mibx5.washer.f28': {
        'select_action': 'clean_start',
    },
    'mibx5.washer.*': {
        'sensor_properties': 'fault,left_time,door_state,run_status,power_consumption,water_consumption,clean_lefttime,'
                             'detergent_left_level,fabric_softener_left_level,water_temperature,has_washed_times,has_dried_times',
        'switch_properties': 'on,sleep_mode,steam_sterilization,high_water_switch,detergent_self_delivery,blue_oxygen,'
                             'child_protected_enabled,self_delivery_auto_turnoff,laundry_beads,one_click_wash,ai_mode,'
                             'disinfectant_mode,linkage_on',
        'select_properties': 'mode,soak_time,drying_level,drying_degree,reservation_wash_status,card_slot,'
                             'detergent_self_delivery_level,softener_self_delivery_level',
        'number_select_properties': 'target_temperature,rinsh_times,spin_speed,wash_time,shake_time,drying_time,reservation_left_time',
        'button_actions': 'start_wash,stop_washing,pause,clean_stop,make_cabin_openable',
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
    'mrbond.airer.m31a': {
        'cover_position_mapping': None,
        'disable_target_position': True,
        'number_properties': 'target_position',
        'append_converters': [
            {
                'class': MiotCoverConv,
                'services': ['airer'],
                'converters': [{'props': ['prop.2.10']}],
            }
        ],
    },
    'mrbond.airer.m53pro': {
        'sensor_properties': 'fault,left_time',
        'select_properties': 'dryer,drying_level',
        'switch_properties': '',
        'chunk_properties': 1,
    },
    'mrbond.airer.*': {
        'deviated_position': 0,
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
        'miio_cloud_props_template': 'mxiang_cateye_cloud_props',
        'miio_cloud_records': 'event.human_visit_details:1',
        'miio_cloud_records_interval': 120,
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
        'number_properties': 'function_countdown.warm,function_countdown.blower,'
                             'function_countdown.breath,function_countdown,shutdown',
        'append_converters': [
            {
                'class': MiotLightConv,
                'services': ['aura_light'],
                'converters' : [
                    {'props': ['brightness'], 'class': MiotBrightnessConv},
                    {'props': ['color'], 'class': MiotRgbColorConv},
                ],
            },
        ],
    },
    'opple.light.dcfan2': {
        'sensor_properties': 'temperature',
        'switch_properties': 'cycle_switch,mode_switch,switch,intelligent_speed,circle_air,bwind_rotate,'
                             'fan_countdown_switch',
        'select_properties': 'nursing_value,fan_level,buzzer_status',
        'number_properties': 'temp_set,fan_countdown_time',
        'percentage_property': 'fan_advance.speed',
        'append_converters': [
            {
                'class': MiotFanConv,
                'services': ['fan'],
                'converters': [{'props': ['fan_advance.speed']}],
            },
        ],
        'chunk_coordinators': [
            {'interval': 11, 'props': 'light.on,mode,brightness,color_temperature'},
            {'interval': 16, 'props': 'fan.on,speed,fan_level'},
        ],
    },
    'opple.light.yrtd': {
        'switch_properties': 'night_light,time_display,wake_up_at_night,voice',
        'select_properties': 'study_time',
        'number_properties': 'love_bright,love_color',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,mode'},
        ],
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
        'switch_properties': 'enable',
        'select_properties': 'mode,rgb_order',
        'number_properties': 'numleds,pixel_per_step,fade_delay,step_delay,stair_travel_time',
        'append_converters': [
            {
                'class': MiotLightConv,
                'services': ['light_ct', 'light_led_strip'],
                'converters' : [
                    {'props': ['brightness'], 'class': MiotBrightnessConv},
                    {'props': ['color_temperature', 'color_temp'], 'class': MiotColorTempConv},
                    {'props': ['color'], 'class': MiotRgbColorConv},
                ],
            },
        ],
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
        'interval_seconds': 30,
        'sensor_attributes': 'props:clean_area,props:clean_time',
        'sensor_properties': 'vacuum.status',
        'select_properties': 'water_level,mop_mode',
        'chunk_coordinators': [],
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
        'interval_seconds': 81,
        'button_actions': 'start_sweep,stop_sweeping,pause,continue_sweep,find_robot,start_charge,stop_find_charge,'
                          'pause_find_charge,continue_find_charge,start_dust,reset_filter_life,reset_brush_life',
        'binary_sensor_properties': 'mop',
        'sensor_properties': 'status,fault,clean_area,clean_time,filter_life_level,brush_life_level',
        'switch_properties': 'auto_boost,double_clean,edge_sweep,led_switch,lidar_collision,mute,map_memory,'
                             'station_key,station_led,use_auto_area',
        'select_properties': 'mode,sweep_type,work_station_freq,water_level,path_type',
        'number_properties': 'volume',
        'exclude_miot_services': None,
        'exclude_miot_properties': 'vacuum.on,custom.progress,station_type,voice_conf,app_state,sweep_mode',
        'chunk_coordinators': [
            {'interval': 21, 'props': 'status,mode,sweep_type,charging_state', 'notify': True},
            {'interval': 41, 'props': 'fault,mop,water_level'},
            {'interval': 61, 'props': 'double_clean,edge_sweep,battery_level,clean_area,clean_time,work_station_freq'},
            {'interval': 121, 'props': 'auto_boost,led_switch,lidar_collision,station_key,station_led,volume,mute'},
            {'interval': 151, 'props': 'total_clean_time,total_clean_areas,clean_counts,path_type'},
            {'interval': 600, 'props': 'filter_l*,brush_l*'},
            {'interval': 610, 'props': 'custom.uid,timing,forbid_mode,current_audio,map_memory,use_auto_area'},
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
    'shhf.light.sfla12': {
        'button_actions': 'toggle,toggle_light_mode',
        'switch_properties': 'ambient_light.on,switch.on,default_power_on_state,flex_switch,sleep_aid_mode,wake_up_mode,'
                             'delay,off_to_center,vertical_swing,horizontal_swing',
        'chunk_coordinators': [
            {'interval': 16, 'props': 'light.on,brightness,color_temperature,mode'},
            {'interval': 21, 'props': 'fan.on,fan_level,ambient_light.on,switch.on'},
            {'interval': 61, 'props': 'default_power_on_state,flex_switch,sleep_aid_mode,wake_up_mode'},
            {'interval': 71, 'props': 'delay*,off_to_center,vertical_swing,horizontal_swing'},
        ],
    },
    'shuii.humidifier.jsq002': {
        'brightness_for_on': 3,
        'brightness_for_off': 1,
    },
    'suittc.airrtc.wk168': {
        'interval_seconds': 30,
        'sensor_properties': 'temperature',
        'switch_properties': 'on',
        'turn_on_hvac': 'heat',
        'chunk_coordinators': [],
    },

    'tmwl.valve.iotb2': {
        'sensor_attributes': 'current_power,current_voltage,current_current,leakage_current,*_temperature',
        'switch_properties': 'valve_switch',
        'number_properties': 'target_water_level,over_current_off,overload_alarm,overload_device_off,leakage_alarm,'
                             'mcu_over_temp_alarm,term_over_temp_alarm,term_over_temp_off,leakage_device_off',
    },
    'tofan.airrtc.wk01': {
        'append_converters': [
            {
                'services': ['thermostat'],
                'converters': [{'props': ['air_conditioner.mode']}],
            }
        ],
    },
    'topwit.bhf_light.rz01': {
        'sensor_attributes': 'ptc_bath_heater.temperature.error',
        'switch_properties': 'heating,blow,ventilation',
        'number_properties': 'ventilation_cnt_down',
    },

    'uvfive.steriliser.maine': CHUNK_1,

    'viomi.aircondition.y116': {
        'interval_seconds': 200,
        'switch_properties': 'air_conditioner.on,uv,auto_clean',
        'exclude_miot_properties': 'fault,autoclean_worktime',
        'chunk_coordinators': [
            {'interval': 31, 'props': 'air_conditioner.on'},
            {'interval': 36, 'props': 'mode'},
            {'interval': 41, 'props': 'target_temperature'},
            {'interval': 46, 'props': 'fan_level'},
            {'interval': 51, 'props': 'horizontal_swing'},
            {'interval': 56, 'props': 'vertical_swing'},
            {'interval': 61, 'props': 'temperature'},
            {'interval': 66, 'props': 'uv'},
            {'interval': 71, 'props': 'eco'},
            {'interval': 76, 'props': 'sleep_mode'},
            {'interval': 199, 'props': 'indicator_light.on'},
            {'interval': 299, 'props': 'auto_clean'},
        ],
    },
    'viomi.airer.xy108': {
        'switch_properties': 'dryer',
    },
    'viomi.airer.*': {
        'sensor_properties': 'status',
        'switch_properties': '',
        'select_properties': 'dryer,swing_mode',
        'number_properties': 'drying_time',
        'cover_position_mapping': {
            0: 50,   # Normal
            1: 100,  # Rising-limit
            2: 0,    # Descent-limit
        },
    },
    'viomi.fan.v7': {
        'switch_properties': 'screen.on',
        'select_properties': 'horizontal_angle',
        'number_properties': 'countdown_time',
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
        'sensor_attributes': 'clean_area,clean_time',
        'sensor_properties': 'vacuum.status,main_brush_life,side_brush_life,hypa_life,mop_life',
    },
    'viomi.vacuum.*:clean_area': {
        'unit_of_measurement': '㎡',
    },
    'viomi.vacuum.*:clean_time': {
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

    'xiaomi.airc.r09h00': {
        'sensor_properties': 'outdoor_temp,mosquito_life,filter_life_level,power_consumption',
        'switch_properties': 'on,eco,heater,dryer,sleep_mode,vertical_swing,un_straight_blowing,favorite_on,alarm',
        'select_properties': 'vertical_angle,favorite_type,brightness,room_size',
        'number_properties': 'target_temperature,target_humidity,fan_percent',
    },
    'xiaomi.airc.r24r00': {
        'sensor_properties': 'power_consumption,fault_value',
    },
    'xiaomi.airc.r34r00': {
        'sensor_properties': 'power_consumption,fault_value',
    },
    'xiaomi.airc.ra2r00': {
        'sensor_properties': 'fault_value,outdoor_temp,power_consumption',
        'switch_properties': 'auto_cooling,list_soft_wind,max_level,always_favorite_on',
        'select_properties': 'low_watt_level,wind_direction,vertical_position,horizontal_position',
        'number_properties': 'fan_percent',
        'exclude_miot_services': 'air_conditioner_dev_mode,system_parm',
    },
    'xiaomi.airc.*': {
        'button_actions': 'favorite_toggle,reset_filter_life',
        'switch_properties': 'on,favorite_on,un_straight_blowing,horizontal_swing,vertical_swing',
        'select_properties': 'vertical_swing_included_angle,room_size',
        'number_properties': 'fan_percent',
    },
    'xiaomi.airc.*:power_consumption': ENERGY_KWH,
    'xiaomi.aircondition.c12': ENERGY_AC_0801,
    'xiaomi.aircondition.c13': ENERGY_AC_0801,
    'xiaomi.aircondition.c15': ENERGY_AC_0801,
    'xiaomi.aircondition.c16': ENERGY_AC_0801,
    'xiaomi.aircondition.c24': {
        **ENERGY_AC_0801,
        'stat_power_cost_type': 'stat_day_v3',
    },
    'xiaomi.aircondition.c26': {
        **ENERGY_AC_0801,
        'stat_power_cost_type': 'stat_day_v3',
    },
    'xiaomi.aircondition.c30': ENERGY_AC_2001,
    'xiaomi.aircondition.c31': ENERGY_AC_2001,
    'xiaomi.aircondition.c32': ENERGY_AC_2001,
    'xiaomi.aircondition.c33': ENERGY_AC_2001,
    'xiaomi.aircondition.c35': ENERGY_AC_2001,
    'xiaomi.aircondition.c36': ENERGY_AC_2001,
    'xiaomi.aircondition.c37': ENERGY_AC_2001,
    'xiaomi.aircondition.c38': ENERGY_AC_2001,
    'xiaomi.aircondition.c39': ENERGY_AC_2001,
    'xiaomi.aircondition.c40': ENERGY_AC_2001,
    'xiaomi.aircondition.m4': {
        'switch_properties': 'air_conditioner.on,un_straight_blowing,favorite_on',
        'exclude_miot_services': 'maintenance,machine_state,single_smart_scene,system_parm,favorite_type_data,'
                                 'air_conditioner_dev_mode,product_appearance',
        'exclude_miot_properties': 'fault,enhance.timer,humidity_range',
    },
    'xiaomi.aircondition.m9': {
        'interval_seconds': 90,
        'switch_properties': 'air_conditioner.on,un_straight_blowing,favorite_on',
        'exclude_miot_services': 'electricity,maintenance,enhance,machine_state,flag_bit,single_smart_scene,system_parm,'
                                 'mosquito_repellent,favorite_type_data,air_conditioner_dev_mode,product_appearance',
        'exclude_miot_properties': 'fault,enhance.timer,humidity_range',
    },
    'xiaomi.aircondition.m15': ENERGY_AC_2001,
    'xiaomi.aircondition.m16': ENERGY_AC_2001,
    'xiaomi.aircondition.m18': ENERGY_AC_2001,
    'xiaomi.aircondition.m19': ENERGY_AC_2001,
    'xiaomi.aircondition.m22': ENERGY_AC_2001,
    'xiaomi.aircondition.m27': ENERGY_AC_2001,
    'xiaomi.aircondition.m28': ENERGY_AC_2001,
    'xiaomi.aircondition.ma1': {
        'miot_type': 'urn:miot-spec-v2:device:air-conditioner:0000A004:xiaomi-ma1:4',
    },
    'xiaomi.aircondition.ma2': {
        'miot_type': 'urn:miot-spec-v2:device:air-conditioner:0000A004:xiaomi-ma2:3',
    },
    'xiaomi.aircondition.ma4': {
        'miot_type': 'urn:miot-spec-v2:device:air-conditioner:0000A004:xiaomi-ma4:2',
    },
    'xiaomi.aircondition.mc1': ENERGY_AC_0801,
    'xiaomi.aircondition.mc2': ENERGY_AC_0801,
    'xiaomi.aircondition.mc3': ENERGY_AC_0801,
    'xiaomi.aircondition.mc4': ENERGY_AC_0801,
    'xiaomi.aircondition.mc5': ENERGY_AC_0801,
    'xiaomi.aircondition.mc6': ENERGY_AC_0801,
    'xiaomi.aircondition.mc7': ENERGY_AC_0801,
    'xiaomi.aircondition.mc8': ENERGY_AC_0801,
    'xiaomi.aircondition.mc9': {
        **ENERGY_AC_0801,
        'exclude_miot_services': 'machine_state,flag_bit',
        'exclude_miot_properties': 'enhance.timer',
    },
    'xiaomi.aircondition.mh1': ENERGY_AC_0801,
    'xiaomi.aircondition.mh2': ENERGY_AC_0801,
    'xiaomi.aircondition.mh3': ENERGY_AC_0801,
    'xiaomi.aircondition.mh4': ENERGY_AC_0801,
    'xiaomi.aircondition.mh6': ENERGY_AC_0801,
    'xiaomi.aircondition.mt0': {
        **ENERGY_AC_0801,
        'exclude_miot_services': 'iot_linkage,machine_state,screen_show',
        'exclude_miot_properties': 'enhance.timer,humidity_range,filter_core_rest,sleep_diy_sign',
    },
    'xiaomi.aircondition.mt1': ENERGY_AC_0801,
    'xiaomi.aircondition.mt2': ENERGY_AC_0801,
    'xiaomi.aircondition.mt3': ENERGY_AC_0801,
    'xiaomi.aircondition.mt4': ENERGY_AC_0801,
    'xiaomi.aircondition.mt5': {
        **ENERGY_AC_0801,
        'append_converters': [
            {
                'class': MiotFanConv,
                'services': ['fan_control'],
                'converters' : [{'props': ['air_conditioner.on', 'enhance.fan_percent', 'horizontal_swing']}],
            },
        ],
    },
    'xiaomi.aircondition.mt6': {
        **ENERGY_AC_0801,
        'select_properties': 'fan_level,horizontal_angle,vertical_angle',
        'number_properties': 'target_humidity,fan_percent',
        'exclude_miot_services': 'iot_linkage,machine_state,screen_show',
        'exclude_miot_properties': 'enhance.timer,humidity_range,filter_core_rest,sleep_diy_sign',
    },
    'xiaomi.aircondition.mt7': ENERGY_AC_0801,
    'xiaomi.aircondition.mt8': ENERGY_AC_0801,
    'xiaomi.aircondition.mt9': ENERGY_AC_0801,
    'xiaomi.aircondition.*': {
        'exclude_miot_services': 'iot_linkage,machine_state,flag_bit',
        'exclude_miot_properties': 'enhance.timer',
    },
    'xiaomi.aircondition.*:power_cost_today': ENERGY_KWH,
    'xiaomi.aircondition.*:power_cost_month': ENERGY_KWH,
    'xiaomi.airp.cpa4': {
        'button_actions': 'toggle,reset_filter_life',
        'sensor_properties': 'filter_life_level',
        'switch_properties': 'alarm',
        'select_properties': 'brightness,aqi_updata_heartbeat',
        'number_properties': 'favorite_level',
        'speed_property': 'favorite_level',
        'exclude_miot_services': None,
        'exclude_miot_properties': 'moto-speed-rpm,country_code,filter_used_time_dbg',
        'chunk_coordinators': [
            {'interval': 21, 'props': 'on,mode'},
            {'interval': 51, 'props': 'favorite_level,pm2_5_density'},
            {'interval': 121, 'props': 'alarm,physical_controls_locked,brightness,aqi_updata_heartbeat'},
            {'interval': 300, 'props': 'filter_*'},
        ],
    },
    'xiaomi.airp.mp4': {
        'switch_properties': 'anion,alarm',
        'select_properties': 'brightness',
        'exclude_miot_services': 'rfid',
    },
    'xiaomi.airp.va2b': {
        'switch_properties': 'on,anion',
        'exclude_miot_services': 'custom_service,rfid',
    },
    'xiaomi.airp.va4': {
        'sensor_properties': 'relative_humidity,air_quality,pm2_5_density,temperature,hcho_density,filter_life_level',
        'switch_properties': 'on,anion,uv,alarm',
        'select_properties': 'air_purifier_favorite.fan_level,brightness',
        'number_properties': 'aqi_updata_heartbeat',
        'button_actions': 'reset_filter_life',
        'exclude_miot_services': 'rfid,custom_service,filter_debug',
    },
    'xiaomi.airp.va5': {
        'sensor_properties': 'fault,air_quality,pm1',
        'switch_properties': 'on,uv',
        'select_properties': 'air_purifier_favorite.fan_level,brightness',
        'number_properties': 'update_heartbeat',
        'button_actions': 'toggle,reset_filter_life',
        'exclude_miot_services': 'custom_service,filter_debug,filter_tag',
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
        'button_actions': 'wake_up,stop_alarm,homepage,light',
        'select_actions': 'switch_page',
        'text_actions': 'play_text,execute_text_directive',
    },
    'xiaomi.cooker.cmk7': {
        'select_actions': None,  # issues/2347
        'select_properties': 'cook_mode,texture',
        'number_properties': 'target_time,reservation_left_time,keep_warm_time',
    },
    'xiaomi.blanket.mj1': {
        'chunk_properties': 1,
        'switch_properties': 'anti_scald_switch,ab_sleep_switch,auto_screen_off',
        'select_properties': 'mode,heat_level',
        'number_properties': 'a_countdown,b_countdown',
    },
    'xiaomi.fishbowl.m200': {
        'sensor_properties': 'water_pump_status,temperature,light_water_use_time,today_feeded_num',
        'switch_properties': 'on,water_pump,light_edit_on,off_flipcover_switch,feed_protect_switch,no_disturb',
        'select_properties': 'pump_flux',
        'number_properties': 'light_edit_color,light_edit_bright',
    },
    'xiaomi.fryer.*': {
        'interval_seconds': 120,
        'button_actions': 'air_fryer.start_cook,pause,cancel_cooking,resume_cook',
        'sensor_properties': 'status,fault,left_time,turn_pot',
        'switch_properties': 'on,auto_keep_warm,current_keep_warm,preheat,turn_pot_config',
        'select_properties': 'mode,texture,target_cooking_measure',
        'number_properties': 'target_time,target_temperature,reservation_left_time,cooking_weight',
        'exclude_miot_properties': 'recipe_id,recipe_name,recipe_sync',
        'chunk_coordinators': [
            {'interval': 20, 'props': 'status,target_time,target_temperature,left_time,turn_pot'},
            {'interval': 35, 'props': 'fault,mode,reservation_left_time,cooking_weight'},
        ],
    },
    'xiaomi.fryer.jl12': {
        'switch_properties': 'on,*_keep_warm,end_cooking_together,turn_pot_config,*shake_food_switch,is_dual_baskets',
        'select_properties': 'mode,double_pot_param_sync,currently_using_pot',
    },
    'xiaomi.fryer.jl12:left_time': {
        'device_class': 'duration',
        'unit_of_measurement': 'min',
    },
    'xiaomi.fryer.jl12:target_time': {
        'device_class': 'duration',
        'unit_of_measurement': 'min',
    },
    'xiaomi.derh.13l': {
        **CHUNK_1,
        'binary_sensor_properties': 'is_warming_up',
        'sensor_properties': 'fault,dry_left_time,delay_remain_time',
        'switch_properties': 'delay,dry_after_off',
        'select_properties': 'indicator_light.mode',
        'number_properties': 'delay_time',
    },
    'xiaomi.derh.lite': {
        **CHUNK_1,
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
    'xiaomi.fan.p45': {
        'button_actions': 'turn_left,turn_right,toggle,toggle_mode,loop_gear',
        'switch_properties': 'delay,horizontal_swing',
        'select_properties': 'horizontal_swing_included_angle',
        'number_properties': 'delay_time',
        'chunk_coordinators': [
            {'interval': 20, 'props': 'on,mode,fan_level'},
        ],
    },
    'xiaomi.fan.p51': {
        'button_actions': 'turn_left,turn_right,toggle,toggle_mode,loop_gear',
        'switch_properties': 'delay',
        'select_properties': 'horizontal_swing_included_angle',
        'number_properties': 'delay_time',
    },
    'xiaomi.feeder.iv2001': {
        'button_actions': 'pet_food_out,reset_desiccant_life,weigh_manual_calibrate',
        'binary_sensor_properties': 'battery_level',
        'sensor_properties': 'pet_food_left_level,status,eaten_food_measure,desiccant_left_level,desiccant_left_time',
        'switch_properties': 'add_meal_state,food_intake_state,schedule_state,compensate_switch,prevent_accumulation',
        'select_properties': 'set_screen_display',
        'number_properties': 'target_feeding_measure,food_intake_rate',
    },
    'xiaomi.feeder.iv2001:battery_level': {
        'device_class': 'battery',
    },
    'xiaomi.feeder.pi2001': {
        'chunk_properties': 1,
        'button_actions': 'pet_food_out,reset_desiccant_life,weigh_manual_calibrate',
        'number_properties': 'target_feeding_measure',
        'sensor_properties': 'pet_food_left_level,fault,eaten_food_measure,desiccant_left_level,desiccant_left_time',
        'switch_properties': 'compensate_switch,prevent_accumulation',
    },
    'xiaomi.feeder.*:eaten_food_measure': {
        'state_class': 'measurement',
        'unit_of_measurement': 'g',
    },
    'xiaomi.feeder.*:pet_food_out': {
        'action_params': '{{ attrs["target_feeding_measure-2-7"]|default(1) }}',
    },
    'xiaomi.juicer.dems2': {
        'button_actions': 'start_cook,cancel_cooking,resume_cook,set_recipe,pause',
        'sensor_properties': 'status,fault,left_time,tank_status,timeout_time,boiling_point',
        'switch_properties': 'alarm,pot_lift_memory,auto_keep_warm,auto_screen_on',
        'select_properties': 'cook_mode',
        'number_properties': 'keep_warm_time,target_temperature,working_level,target_time',
    },
    'xiaomi.health_pot.p1': {
        'select_actions': 'start_cook',
    },
    'xiaomi.heater.ma8': {
        'button_actions': 'toggle',
    },
    'xiaomi.hood.jyjp2': {
        'interval_seconds': 90,
        'button_actions': 'toggle,stop_dry_cleaning',
        'binary_sensor_properties': 'prop.12.2,prop.12.3',
        'sensor_properties': 'status,stove_link_status,current_heat_level,left_time,stove_hood_linkage,charge_progress,'
                             'dry_cleaning_status,dry_cleaning_left_time,pm1',
        'switch_properties': 'delay,off_delay,power_on_with_light,power_off_with_light,clean_remind_on,gestures,'
                             'auto_ventilation_on,*_auto_ventilation,dry_cleaning_timing_on,dry_cleaning_guide,'
                             'auto_screen_off,delay_remain_time',
        'select_properties': 'display_state,delay_time',
        'number_properties': 'off_delay_time,countdown_time,clean_remind_time,working_remind_time,auto_screen_off_time,'
                             'pm_trig_*_value,pm_auto_ventilation_time',
        'chunk_coordinators': [
            {'interval': 16, 'props': 'on,fan_level,current_heat_level'},
            {'interval': 21, 'props': 'status,left_time'},
        ],
    },
    'xiaomi.humidifier.airmx': {
        'button_actions': 'toggle,reset_filter_life',
        'sensor_properties': 'water_level,air_dry_remain_time,remain_time,filter_life_level',
        'switch_properties': 'overwet_protect,automatic_air_drying,delay,alarm,auto_alarm_off,clean.on,descale.on'
                             'indicator_light.on,auto_lights_off,wash_water_tank',
        'select_properties': 'indicator_light.brightness',
        'number_properties': 'delay_time',
    },
    'xiaomi.humidifier.p800': {
        'button_actions': 'loop_mode,reset_filter_life',
        'select_properties': 'screen.brightness',
        'sensor_properties': 'fault,water_level,air_dry_remain_time,clean_left_time,filter_life_level,delay_remain_time',
        'switch_properties': 'overwet_protect,automatic_air_drying,alarm,dry_switch,over_wet_protect,screen.on,delay',
        'number_properties': 'delay_time',
    },
    'xiaomi.humidifier.p1200': {
        'button_actions': 'loop_mode,reset_filter_life',
        'select_properties': 'screen.brightness',
        'sensor_properties': 'clean_time,fan_dry_time,fault,water_level,water_status',
        'switch_properties': 'alarm,dry_switch,over_wet_protect,screen.on',
        'number_properties': 'off_delay_time',
    },
    'xiaomi.humidifier.*:water_level': {
        'state_class': 'measurement',
        'unit_of_measurement': '%',
    },
    'xiaomi.kettle.v20': {
        'button_actions': 'stop_work',
        'binary_sensor_properties': 'kettle_lifting',
        'sensor_properties': 'status,temperature,warming_time',
        'switch_properties': 'on,auto_keep_warm,no_disturb,custom_knob_temp,lift_remember_temp,'
                             'boiling_reminder,keep_warm_reminder',
        'number_properties': 'target_temperature,keep_warm_temperature,keep_warm_time,target_mode',
    },
    'xiaomi.oven.cm30l': {
        'select_actions': 'start_cook',
        'sensor_properties': 'status,fault,left_time,working_time,temperature,'
                             'timeout_time,cook_step,door_state,water_box_status',
        'select_properties': 'furnace_light_mode',
        'number_properties': 'target_temperature,cook_time,reservation_left_time',
    },
    'xiaomi.pet_waterer.70m2': {
        'binary_sensor_properties': 'water_shortage_status,usb_insert_state,low_battery,pump_block,fault',
        'button_actions': 'reset_filter_life',
        'switch_properties': 'no_disturb,physical_controls_locked',
        'sensor_properties': 'status,filter_life_level,filter_left_time,battery_level,charging_state',
        'number_properties': 'out_water_interval,time_period_start,time_period_end',
        'select_properties': 'mode',
        'exclude_miot_properties': 'event_time,event_mode,event_water,event_timezone'
    },
    'xiaomi.pet_waterer.70m2:fault': {
         'reverse_state': True,
    },
    'xiaomi.pet_waterer.70m2:filter_left_time': {
         'state_class': 'measurement',
         'unit_of_measurement': 'days',
    },
    'xiaomi.pet_waterer.iv02': {
        'button_actions': 'reset_filter_life,low_battery,pump_block',
        'binary_sensor_properties': 'water_shortage_status',
        'sensor_properties': 'status,event_mode,event_water',
        'switch_properties': 'on,no_disturb',
        'number_properties': 'out_water_interval',
        'select_properties': 'mode',
        'exclude_miot_properties': 'time_period_start,time_period_end,event_timezone'
    },
    'xiaomi.plug.mcn003': {
        'button_actions': 'toggle',
        'sensor_properties': 'fault,electric_power',
        'select_properties': 'default_power_on_state',
        'stat_power_cost_key': '3.1',
    },
    'xiaomi.plug.mcn003:power_cost_today': ENERGY_KWH,
    'xiaomi.plug.mcn003:power_cost_month': ENERGY_KWH,
    'xiaomi.sensor_occupy.p1': {
        'sensor_properties': 'occupancy_status,has_someone_duration,no_one_duration,illumination,people_num',
        'switch_properties': 'enable_switch,installation_image',
        'select_properties': 'installation_method,use_map_number,response_speed',
        'number_properties': 'bio_sensitive',
        'text_properties': 'one_map_name,two_map_name',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'occupancy_status'},
            {'interval': 15, 'props': 'has_someone_duration'},
            {'interval': 15, 'props': 'no_one_duration'},
            {'interval': 20, 'props': 'illumination,people_num,one_map_name,two_map_name'},
            {'interval': 300, 'props': 'enable_switch,installation_method,bio_sensitive,use_map_number,'
                                       'installation_image,response_speed'},
        ],
    },
    'xiaomi.sensor_occupy.p1:people_num': {
        'state_class': 'measurement',
        'unit_of_measurement': 'people',
    },
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
        'interval_seconds': 150,
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
        'exclude_miot_properties': 'zone_ids,restricted_sweep_areas,restricted_walls',
        'configuration_entities': 'edge_swing_tail_sweep,carpet_discriminate,carpet_boost,alarm,dnd_switch,'
                                  'carpet_avoidance,carpet_display,sweep_break_switch,edge_sweep_frequency,'
                                  'carpet_cleaning_method,reset_brush_life,reset_filter_life',
        'chunk_coordinators': [
            {'interval': 21, 'props': 'status,mop_status,charging_state', 'notify': True},
            {'interval': 31, 'props': 'sweep_mop_type,sweep_type,mode,clean_times,suction_level'},
            {'interval': 61, 'props': 'battery_level,cleaning_area,cleaning_time,mop_water_output_level'},
            {'interval': 301, 'props': 'brush_l*,filter_l*'},
            {'interval': 302, 'props': 'frameware_version,vacuum_room_ids,points,current_physical_control_lock'},
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
        'interval_seconds': 121,
        'exclude_miot_services': 'custom,ai_small_pictures,voice_management',
        'exclude_miot_properties': 'vacuum_frameware_version,restricted_sweep_areas,restricted_walls,room_information,'
                                   'order_clean,map_complete_dialog,carpet_deep_cleaning,carpet_discriminate,'
                                   'water_check_list,sweep_ai_object,sweep_furniture,carpet_object,vacuum_route,'
                                   'fault_ids,plugin_info_remind,enable_time_period,current_no_disturb,sweep_route,'
                                   'current_physical_control_lock,current_no_disturb,obstacle_avoidance_strategy,'
                                   'carpet_obj_name,map_3d_info',
        'button_actions': 'start_sweep,start_only_sweep,start_mop,start_sweep_mop,start_custom_sweep,start_dry,'
                          'pause_sweeping,continue_sweep,stop_and_gocharge,start_charge,start_mop_wash,start_cut_hair,'
                          'enter_remote,exit_remote,stop_mop_wash,back_mop_wash,stop_dry,stop_cut_hair,identify,'
                          'reset_mop_life,reset_brush_life,reset_filter_life,reset_detergent_management_level,'
                          'reset_dust_bag_life',
        'select_actions': 'remote_control',
        'configuration_entities': 'ai_cleaning,ai_managed_cleaning,use_detergent,*_detection,cut_hair_config,'
                                  'mop_auto_lift,carpet_boost,carpet_avoidance,carpet_cleaning_method,'
                                  'hot_water_mop_wash,physical_control_locked,volume,detergent_self_delivery*,'
                                  'auto_water_change,auto_mop_dry,auto_dust_arrest,dust_arrest_frequency',
        'diagnostic_entities': 'voltage,water_check_status,filter_l*,dust_bag_l*,brush_l*,detergent_l*',
        'chunk_coordinators': [
            {'interval': 11, 'props': 'status,cleaning_area,cleaning_time,charging_state', 'notify': True},
            {'interval': 16, 'props': 'mode,sweep_mop_type,sweep_type,clean_times,vacuum_position'},
            {'interval': 61, 'props': 'mop_status,battery_level,charging_state'},
            {'interval': 130, 'props': 'auto_*,*_detection'},
            {'interval': 300, 'props': 'filter_l*,mop_l*,dust_bag_l*,brush_l*,detergent_l*'},
            {'interval': 999, 'props': 'clean_record'},
        ],
    },
    'xiaomi.vacuum.d102gl': {
        'interval_seconds': 120,
        'button_actions': 'start_sweep,start_only_sweep,start_mop,start_sweep_mop,start_custom_sweep,start_mop_wash,'
                          'pause_sweeping,continue_sweep,start_dust_arrest,start_dry,start_eject,back_mop_wash,'
                          'stop_sweeping,stop_and_gocharge,stop_mop_wash,stop_dry,identify',
        'chunk_coordinators': [
            {'interval': 11, 'props': 'status', 'notify': True},
            {'interval': 21, 'props': 'mode,sweep_mop_type,sweep_type'},
            {'interval': 31, 'props': 'charging_state,vacuum_position'},
            {'interval': 41, 'props': 'cleaning_area,cleaning_time'},
            {'interval': 61, 'props': 'mop_status,battery_level,clean_times'},
            {'interval': 150, 'props': 'auto_*,*_detection'},
            {'interval': 200, 'props': 'carpet_*,water_*'},
            {'interval': 250, 'props': 'map_*'},
            {'interval': 300, 'props': 'filter_l*,mop_l*,dust_bag_l*,brush_l*,detergent_l*'},
            {'interval': 999, 'props': 'clean_record,map_3d_info,room_information'},
        ],
    },
    'xiaomi.vacuum.d109gl': {
        'interval_seconds': 120,
        'exclude_miot_services': 'vacuum_map,custom,voice_management',
        'number_properties': 'frequency_mop_wash_by_time',
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
    },
    'xiaomi.vacuum.ov31gl': {
        'interval_seconds': 120,
        'exclude_miot_services': 'vacuum_map,custom,voice_management',
        'sensor_properties': 'sweep_mop_status,sewage_tank_status,water_tank_status,base_station_water_tank_status,'
                             'host_water_tank_status',
        'switch_properties': 'brush_outswing,repeat_wash_mop',
        'number_properties': 'frequency_mop_wash_by_time',
        'button_actions': 'start_sweep,stop_sweeping,stop_and_gocharge,start_only_sweep,start_mop,start_sweep_mop,'
                          'pause_sweeping,continue_sweep,start_dust_arrest,start_mop_wash,start_dry,stop_mop_wash,stop_dry,'
                          'start_water_self_check,cancel_water_self_check,start_base_station_cleaning,start_charge,'
                          'start_sweep_before_mopping,stop_working,empty_base_station_water_tank,empty_host_water_tank,'
                          'identify,reset_*_life',
    },
    'xiaomi.vacuum.ov81gl': {
        'interval_seconds': 121,
        'exclude_miot_services': 'custom,ai_small_pictures,voice_management',
        'exclude_miot_properties': 'vacuum_frameware_version,restricted_sweep_areas,restricted_walls,room_information,'
                                   'order_clean,map_complete_dialog,carpet_deep_cleaning,carpet_discriminate,'
                                   'water_check_list,sweep_ai_object,sweep_furniture,carpet_object,vacuum_route,'
                                   'fault_ids,plugin_info_remind,enable_time_period,current_no_disturb,sweep_route,'
                                   'current_physical_control_lock,current_no_disturb,obstacle_avoidance_strategy,'
                                   'carpet_obj_name,map_3d_info',
        'button_actions': 'start_sweep,start_only_sweep,start_mop,start_sweep_mop,start_custom_sweep,start_dry,'
                          'pause_sweeping,continue_sweep,stop_and_gocharge,start_charge,start_mop_wash,start_cut_hair,'
                          'enter_remote,exit_remote,stop_mop_wash,back_mop_wash,stop_dry,stop_cut_hair,identify,'
                          'reset_mop_life,reset_brush_life,reset_filter_life,reset_detergent_management_level,'
                          'reset_dust_bag_life',
        'select_actions': 'remote_control',
        'configuration_entities': 'ai_cleaning,ai_managed_cleaning,use_detergent,*_detection,cut_hair_config,'
                                  'mop_auto_lift,carpet_boost,carpet_avoidance,carpet_cleaning_method,'
                                  'hot_water_mop_wash,physical_control_locked,volume,detergent_self_delivery*,'
                                  'auto_water_change,auto_mop_dry,auto_dust_arrest,dust_arrest_frequency',
        'diagnostic_entities': 'voltage,water_check_status,filter_l*,dust_bag_l*,brush_l*,detergent_l*',
        'chunk_coordinators': [
            {'interval': 11, 'props': 'status,cleaning_area,cleaning_time,charging_state', 'notify': True},
            {'interval': 16, 'props': 'mode,sweep_mop_type,sweep_type,clean_times,vacuum_position'},
            {'interval': 61, 'props': 'mop_status,battery_level,charging_state'},
            {'interval': 130, 'props': 'auto_*,*_detection'},
            {'interval': 300, 'props': 'filter_l*,mop_l*,dust_bag_l*,brush_l*,detergent_l*'},
            {'interval': 999, 'props': 'clean_record'},
        ],
    },
    'xiaomi.vacuum.*': {
        'interval_seconds': 90,
        'chunk_coordinators': [
            {'interval': 11, 'props': 'status,cleaning_area,cleaning_time', 'notify': True},
            {'interval': 16, 'props': 'mode,sweep_mop_type,sweep_type,vacuum_position'},
            {'interval': 61, 'props': 'mop_status,battery_level,charging_state,clean_times'},
            {'interval': 150, 'props': 'auto_*,*_detection'},
            {'interval': 200, 'props': 'carpet_*,water_*'},
            {'interval': 250, 'props': 'map_*'},
            {'interval': 300, 'props': 'filter_l*,mop_l*,dust_bag_l*,brush_l*,detergent_l*'},
            {'interval': 999, 'props': 'clean_record,map_3d_info,room_information'},
        ],
    },
    'xiaomi.watch.*': {
        'sensor_properties': 'current_step_count,current_distance',
    },
    'xiaomi.waterheater.ymm6': {
        'sensor_properties': 'status,input_water_temperature,water_flow,anti_icing_status,water_pump_volt,'
                             'water_consumption,gas_consumption,temperature,filter_life_level',
        'switch_properties': 'on,hot_water_recirculation,water_control_preheat,rapid_preheat,intelligent_preheat,boost,'
                             'ventilation,cloud_preheater,inner_loop',
        'select_properties': 'boost_mode,boost_level',
        'number_properties': 'preheat_time,ventilation_time,auto_screen_off_time',
        'chunk_coordinators': [
            {'interval': 11, 'props': 'on,status,mode,target_temperature,temperature'},
            {'interval': 21, 'props': 'hot_water_recirculation,*_preheat,boost*'},
        ],
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
    'xiaomi.ysj.v2': {
        'binary_sensor_properties': 'whether_have_water',
        'sensor_properties': 'status,temperature,rinse_progress,store_timeout',
        'switch_properties': 'icing,child_lock,drink_remind,switch_button,buzzer_enable',
        'select_properties': 'mode,rinse_status',
        'number_properties': 'target_temperature',
    },
    'xjx.toilet.relax': {
        'button_actions': 'flush_on',
    },
    'xjx.toilet.relaxp': {
        'sensor_properties': 'status,bubble_level',
        'switch_properties': 'status_seatheat,status_led,auto_led,flush_setting,statys_bubbleshield,'
                             'status_seat,status_cover,auto_seat_close,auto_cover_close,status_microw_seat,'
                             'status_microw_cover,status_footin_seat,status_footin_cover,status_selfclean,'
                             'moving_t,moving_w,massage_temp',
        'select_properties': 'water_temp_t,water_strong_t,water_pos_t,water_temp_w,water_strong_w,water_pos_w,'
                             'seat_temp,status_massage_w,status_massage_t,fen_temp',
        'button_actions': 'stop_working,flush_work,start_foam,clean_work',
    },
    'xtl.vacuum.xm2216': {  # poorly spec
        'button_actions': 'stop_clean,seek_robot',
        'select_actions': 'pause_continue_work,set_clean_mode,set_fan_mode,set_water_mode,set_dust_collection,manual_control',
        'sensor_properties': 'status,robot_status,clean_time,clean_area,error,message',
        'switch_properties': 'disturb_switch,break_clean_switch,collect_dust,dry_mop,wash_mop,child_lock,drying_switch',
        'select_properties': 'clean_mode,water_mode,fan_mode,carpet_clean_prefer',
        'exclude_miot_properties': 'scheduled_timers,time_zone,clean_records,aw_check_*,room_edite_result,language_ver',
        'chunk_coordinators': [
            {'interval': 11, 'props': 'status,charging_state', 'notify': True},
            {'interval': 21, 'props': 'mode,clean_mode,water_mode,fan_mode'},
            {'interval': 61, 'props': 'robotic_vacuum.*_status,battery_level'},
            {'interval': 71, 'props': 'robotic_vacuum.*_switch'},
            {'interval': 81, 'props': 'clean_values,error,message,station_error'},
            {'interval': 301, 'props': 'consumables,filter_l*,brush_l*,detergent_l*,dust_bag_l*'},
        ],
    },
    'xwhzp.diffuser.xwxfj': {
        'sensor_properties': 'fragrance_liquid_left_level',
        'switch_properties': 'anion',
        'select_properties': 'mode',
        'number_properties': 'fragrance_out_time,countdown_time,countdown,scent_mix_level,brightness,color',
    },

    'yeelink.curtain.crc2': CHUNK_1,
    'yeelink.curtain.ctmt1': {
        **CHUNK_1,
        'chunk_coordinators': [],
    },
    'yeelink.curtain.ctmt2': {
        **CHUNK_1,
        'chunk_coordinators': [],
    },
    'yeelink.bhf_light.v1': {
        'interval_seconds': 30,
        'chunk_coordinators': [],
    },
    'yeelink.bhf_light.v2': {
        'interval_seconds': 30,
        'chunk_coordinators': [],
    },
    'yeelink.bhf_light.v3': {
        'interval_seconds': 30,
        'chunk_coordinators': [],
    },
    'yeelink.bhf_light.v5': {
        'interval_seconds': 30,
        'select_properties': 'heat_mode,cold_mode,vent_mode',
        'chunk_coordinators': [],
    },
    'yeelink.bhf_light.v6': {
        'interval_seconds': 30,
        'select_properties': 'heat_mode,cold_mode,vent_mode',
        'chunk_coordinators': [],
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
    'yeelink.light.lamp22': {
        'interval_seconds': 120,
        'chunk_coordinators': [
            {'interval': 21, 'props': 'on,brightness'},
            {'interval': 31, 'props': 'color_temperature,mode,default_power_on_state'},
            {'interval': 81, 'props': 'delay_*,scene_mode,work_minutes,break_minutes'},
            {'interval': 91, 'props': 'mode_one_*,mode_two_*'},
            {'interval': 96, 'props': 'mode_three_*,mode_four_*'},
        ],
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
        'interval_seconds': 20,
        'switch_properties': 'bg_on,init_power_opt,fan_init_power_opt',
        'chunk_coordinators': [],
    },
    'yeelink.mirror.bm1': {
        'switch_properties': 'heat_control',
        'number_properties': 'off_delay_time,heat_delayoff',
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
    'yuemee.sensor_gas.56712': {
        'chunk_coordinators': [
            {'interval': 21, 'props': 'status'},
            {'interval': 120, 'props': 'updown'},
            {'interval': 300, 'props': 'read_log_data'},
        ],
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
    'zhimi.airp.meb1': {
        'select_properties': 'brightness,temperature_display_unit',
    },
    'zhimi.airp.meb1:pm10_density': {
        'unit_of_measurement': 'µg/m³',
    },
    'zhimi.airp.rmb1': {
        'switch_properties': 'alarm',
        'select_properties': 'brightness',
        'number_properties': 'favorite_level',
    },
    'zhimi.airp.sa4': {
        'switch_properties': 'alarm',
        'select_properties': 'brightness',
        'number_properties': 'air_purifier_favorite.fan_level,aqi_updata_heartbeat',
        'button_actions': 'reset_filter_life',
    },
    'zhimi.airp.rma3': {
        'interval_seconds': 150,
        'sensor_properties': 'moto_speed_rpm',
        'switch_properties': 'alarm',
        'select_properties': 'brightness,air_purifier_favorite.fan_level',
        'chunk_coordinators': [
            {'interval': 21, 'props': 'on,mode,fan_level'},
            {'interval': 61, 'props': 'fault,relative_humidity,pm2_5_density,temperature,air_quality'},
            {'interval': 301, 'props': 'filter_*'},
        ],
    },
    'zhimi.airp.vb4:pm10_density': {
        'unit_of_measurement': 'µg/m³',
    },
    'zhimi.airp.*:moto_speed_rpm': {
        'unit_of_measurement': 'rpm',
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
        'switch_properties': 'horizontal_swing,vertical_swing,oscillating,h_swing_back,v_swing_back,brightness,alarm',
        'number_properties': 'timing',
        'select_properties': 'mode,fan_level,horizontal_angle,vertical_angle',
        'button_properties': 'h_swing_step_move,v_swing_step_move',
    },
    'zhimi.fan.za3': {
        'miot_type': 'urn:miot-spec-v2:device:fan:0000A005:zhimi-za3:3',
        'number_select_properties': 'fan_level',
    },
    'zhimi.fan.za4': {
        'miot_type': 'urn:miot-spec-v2:device:fan:0000A005:zhimi-za4:3',
        'number_select_properties': 'fan_level',
    },
    'zhimi.fan.za5': {
        **CHUNK_1,
        'number_properties': 'speed_level',
        'exclude_miot_properties': 'button_press,country_code',
        'interval_seconds': 121,
        'chunk_coordinators': [
            {'interval': 21, 'props': 'on,speed_level,mode'},
            {'interval': 61, 'props': 'fan_level,horizontal_swing,horizontal_angle,off_delay,anion,speed_now'},
            {'interval': 91, 'props': 'temperature,relative_humidity,temp_sens'},
            {'interval': 301, 'props': 'battery_state,ac_state'},
        ],
    },
    'zhimi.fan.*': {
        'switch_properties': 'anion,alarm,horizontal_swing,vertical_swing',
        'number_properties': 'horizontal_angle,vertical_angle,off_delay',
        'append_converters': [
            {
                'class': MiotFanConv,
                'services': ['fan'],
                'converters': [{'props': ['custom_service.speed_level']}],
            }
        ],
    },
    'zhimi.heater.na1': {
        'switch_properties': 'on,return_to_middle',
        'number_properties': 'countdown_time',
    },
    'zhimi.heater.nb1': {
        'switch_properties': 'on,return_to_middle',
        'number_properties': 'countdown_time',
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
    'zhimi.toilet.pa5': {
        'button_actions': 'flushing,open_cover_circle,close_cover_circle,stoving,hip_washing,women_washing,'
                          'move_back_and_forth,child_washing,strong_washing,nozzle_selfclean,foam_shield,'
                          'user_process_one,user_process_two,user_process_three,user_process_four,user_process_five,'
                          'stop_working,reset_filter_life,ceramics_self_clean',
        'sensor_properties': 'cover_circle_status',
        'switch_properties': 'on,leave_auto_flushing,eco_smart,foot_feel_auto,flap_flushing,flap_footfeel_syn',
        'select_properties': 'water_temperature,person_switch,wind_strength,wind_position,wind_temperature',
        'number_properties': 'flap_auto_time,foamshield_time',
        'chunk_coordinators': [
            {'interval': 16, 'props': 'status,seating_state,cover_circle_status'},
            {'interval': 61, 'props': 'toilet.on,heat_level,washing_strength,nozzle_position,deodorization'},
            {'interval': 71, 'props': 'water_temperature,eco_smart,wind_strength,wind_position,wind_temperature'},
            {'interval': 81, 'props': 'leave_auto_flushing,indicator_light.on,physical_controls_locked,alarm'},
            {'interval': 91, 'props': 'night_light.on,night_save.on,start_time,end_time'},
            {'interval': 301, 'props': 'fault,filter_life_level,device_version'},
        ],
        'interval_seconds': 120,
        'exclude_miot_properties': 'user_*_one,user_*_two,user_*_three,user_*_four,user_*_five',
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
        'sensor_attributes': 'store.powerCost:today,store.powerCost:month',
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
    'zinguo.etool.tk01': {
        'binary_sensor_properties': 'boost,feed,heat,recircle,defreeze,water_shortage,low_pressure,overflow,overload,leakage',
        'sensor_properties': 'water_level,temperature,sensor_fault,power,energy',
        'switch_properties': '*_enable,back_light,overload_protect',
        'select_properties': 'mode,pre_water_level,hengshui_level,sensility,*_feed_level,exe_*',
        'number_properties': 'pre_temperature,wenkong_temperature,hengwen_temperature,recircle_time,shortage_delay_time,*_heat_temperature',
        'interval_seconds': 181,
        'chunk_coordinators': [
            {'interval': 21, 'props': 'water_level,temperature'},
            {'interval': 31, 'props': 'boost,feed,heat,recircle,defreeze'},
            {'interval': 41, 'props': 'water_shortage,low_pressure,overflow,overload,leakage,sensor_fault'},
            {'interval': 51, 'props': 'power,energy'},
            {'interval': 91, 'props': 'mode,pre_water_level,hengshui_level,*_enable'},
            {'interval': 101, 'props': 'timer_mode.one_*'},
            {'interval': 102, 'props': 'timer_mode.two_*'},
            {'interval': 103, 'props': 'timer_mode.tri_*'},
            {'interval': 104, 'props': 'eco_mode.one_*'},
            {'interval': 105, 'props': 'eco_mode.two_*'},
            {'interval': 106, 'props': 'eco_mode.tri_*'},
            {'interval': 107, 'props': 'sunny_mode.one_*'},
            {'interval': 108, 'props': 'sunny_mode.two_*'},
            {'interval': 109, 'props': 'sunny_mode.tri_*'},
            {'interval': 110, 'props': 'rainy_mode.one_*'},
            {'interval': 111, 'props': 'rainy_mode.two_*'},
            {'interval': 112, 'props': 'rainy_mode.tri_*'},
        ],
    },
    'zinguo.etool.tk01:energy': {
        **ENERGY_KWH,
        'value_ratio': 0.1,
    },
    'zinguo.etool.tk01:power': {
        'state_class': 'measurement',
        'device_class': 'power',
        'unit_of_measurement': 'W',
        'value_ratio': 0.1,
    },
    'zinguo.etool.tk01:water_level': {
        'unit_of_measurement': '%',
    },
    'zinguo.etool.tk01:temperature': {
        'state_class': 'measurement',
        'device_class': 'temperature',
        'unit_of_measurement': '°C',
    },
    'zinguo.motor.mk01': {
        'sensor_properties': 'status,fault,block_alarm,unclosed_alarm',
        'select_properties': 'mode,block_type',
        'number_properties': 'block_devicealarm,unclosed_devicealarm,unclosed_set',
    },
    'zinguo.motor.mk01:motor_control': {
        'device_class': 'garage',
    },
    'zinguo.switch.b5m': {
        'sensor_properties': 'temperature',
        'switch_properties': 'heating,blow,ventilation',
        'select_properties': 'link',
    },

    '*.aircondition.*': {
        'sensor_properties': 'electricity.electricity',
        'switch_properties': 'air_conditioner.on',
        'select_properties': 'fan_level',
        'number_properties': 'target_humidity',
        'chunk_coordinators': [
            {'interval': 11, 'props': 'air_conditioner.on,mode,target_temperature,fan_level', 'notify': True},
            {'interval': 31, 'props': 'target_humidity,fan_percent,*_swing,*_angle'},
            {'interval': 51, 'props': 'eco,heater,dryer,sleep_mode,temperature,relative_humidity'},
            {'interval': 91, 'props': 'alarm,indicator_light.on,brightness'},
            {'interval': 299, 'props': 'filter_life_*'},
        ],
    },
    '*.airer.*': {
        'sensor_properties': 'left_time',
        'switch_properties': 'dryer,uv',
        'select_properties': 'drying_level',
        'chunk_coordinators': [
            {'interval': 16, 'props': 'status,current_position,target_position'},
            {'interval': 21, 'props': 'light.on'},
            {'interval': 26, 'props': 'dryer,drying_level,uv'},
        ],
    },
    '*.airfresh.*': {
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,mode,fan_level'},
            {'interval': 300, 'props': 'filter_life_level,filter_left_time,filter_used_time'},
        ],
    },
    '*.airpurifier.*': {
        'switch_properties': 'air_purifier.on,alarm.alarm,anion,uv',
        'sensor_properties': 'relative_humidity,pm2_5_density,temperature,filter_life_level',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,mode,fan_level'},
            {'interval': 300, 'props': 'filter_life_level,filter_left_time,filter_used_time'},
        ],
    },
    '*.airrtc.*': {
        'switch_properties': 'air_conditioner.on',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,mode,target_temperature,fan_level', 'notify': True},
        ],
    },
    '*.bhf_light.*': {
        'sensor_properties': 'temperature',
        'switch_properties': 'on,heating,blow,ventilation,dryer,vertical_swing',
        'select_properties': 'mode,room_size,fan_level',
        'number_properties': 'target_temperature,delay_time,off_delay_time',
        'button_actions': 'stop_working',
        'chunk_coordinators': [
            {'interval': 11, 'props': 'on,mode,target_temperature,fan_level'},
            {'interval': 16, 'props': 'heating,blow,ventilation,dryer'},
        ],
    },
    '*.blanket.*': {
        'interval_seconds': 120,
        'sensor_properties': 'temperature',
        'select_properties': 'mode,heat_level,water_level',
        'number_properties': 'target_temperature',
        'chunk_coordinators': [
            {'interval': 21, 'props': 'on,mode,heat_level,water_level,target_temperature,left_time'},
        ],
    },
    '*.camera.*': {
        'miot_cloud_action': True,
        'sensor_properties': 'memory_card_management.status,storage_free_space,storage_used_space',
        'select_properties': 'night_shot,recording_mode,detection_sensitivity',
        'switch_properties': 'on,time_watermark,motion_tracking,motion_detection,wdr_mode,glimmer_full_color',
        'number_properties': 'image_rollover,alarm_interval',
    },
    '*.cateye.*': {
        'auto_cloud': True,
        'use_motion_stream': True,
    },
    '*.chair.*': {
        'binary_sensor_properties': 'seating_state',
        'switch_properties': 'on',
        'select_properties': 'mode',
    },
    '*.coffee.*': {
        'sensor_properties': 'status,fault',
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
        'switch_properties': 'motor_reverse',
        'select_properties': 'mode',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'status,current_position,target_position'},
        ],
    },
    '*.derh.*': {
        'interval_seconds': 120,
        'select_properties': 'fan_level',
        'chunk_coordinators': [
            {'interval': 20, 'props': 'on,mode,target_humidity,fan_level'},
            {'interval': 25, 'props': 'relative_humidity,temperature'},
            {'interval': 300, 'props': 'filter_life_level,filter_left_time,filter_used_time'},
        ],
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
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,wash_mode,wash_time,target_water_level,water_level,left_time'},
        ],
    },
    '*.fan.*': {
        'button_actions': 'turn_left,turn_right',
        'number_properties': 'off_delay_time',
        'switch_properties': 'fan_init_power_opt',
        'chunk_coordinators': [
            {'interval': 16, 'props': 'on,mode,fan_level,speed_level'},
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
        'sensor_properties': 'temperature,door_not_close_remind',
        'switch_properties': 'on',
        'select_properties': 'mode',
        'number_properties': 'target_temperature',
    },
    '*.health_pot.*': {
        'button_actions': 'cancel_cooking',
    },
    '*.heater.*': {
        'switch_properties': 'heater.on,horizontal_swing,alarm.alarm,delay.delay',
        'select_properties': 'heat_level',
        'number_properties': 'countdown_time,delay_time',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'on,mode,target_temperature,fan_level'},
        ],
    },
    '*.humidifier.*': {
        'interval_seconds': 120,
        'select_properties': 'fan_level',
        'chunk_coordinators': [
            {'interval': 20, 'props': 'humidifier.on,mode,target_humidity,fan_level'},
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
        'number_properties': 'off_delay_time,light_on_gradient_time,light_off_gradient_time',
        'switch_properties': 'flex_switch,night_light_switch',
        'button_actions': 'toggle',
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
        'chunk_coordinators': [
            {'interval': 10, 'props': 'status,left_time,heat_level,cook_time'},
        ],
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
    '*.motor.*': {
        'switch_properties': 'motor_reverse',
        'select_properties': 'mode',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'status,current_position,target_position'},
        ],
    },
    '*.oven.*': {
        'button_actions': 'pause,resume_cook,cancel_cooking',
        'sensor_properties': 'temperature,left_time,cook_time,working_time',
        'number_properties': 'target_temperature',
        'switch_properties': 'oven.on',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'oven.on,target_temperature,temperature,left_time,cook_time,working_time'},
        ],
    },
    '*.plantmonitor.*': {
        'sensor_properties': 'soil_ec,illumination,temperature,relative_humidity',
    },
    '*.plug.*': {
        'chunk_coordinators': [
            {'interval': 10, 'props': 'switch.on,electric_power'},
        ],
    },
    '*.s_lamp.*': {
        'sensor_properties': 'left_time',
        'switch_properties': 'on,uv,radar_on',
        'number_properties': 'target_time',
        'chunk_coordinators': [
            {'interval': 20, 'props': 'on,uv,target_time,left_time'},
        ],
    },
    '*.senpres.*': {
        'binary_sensor_properties': 'pressure_present_state',
        'sensor_properties': 'pressure_not_present_duration',
    },
    '*.sensor_occupy.*': {
        'sensor_properties': 'illumination,has_someone_duration,no_one_duration',
        'chunk_coordinators': [
            {'interval': 10, 'props': 'occupancy_status,has_someone_duration,no_one_duration'},
        ],
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
        'select_properties': 'mode,sweep_mop_type,sweep_type,suction_level,water_level,clean_times',
        'number_properties': 'volume',
        'button_actions': 'start_sweep,stop_sweeping,stop_and_gocharge,start_only_sweep,start_mop,start_sweep_mop,'
                          'pause_sweeping,continue_sweep,start_dust_arrest,start_mop_wash,start_dry,start_eject,'
                          'stop_mop_wash,stop_dry,back_mop_wash,start_charge,identify,reset_*',
        'configuration_entities': 'reset_*',
        'diagnostic_entities': 'filter_l*,brush_l*,detergent_l*,dust_bag_l*',
        'chunk_coordinators': [
            {'interval': 11, 'props': 'status,charging_state', 'notify': True},
            {'interval': 16, 'props': 'mode,sweep_mop_type,sweep_type,suction_level,water_level'},
            {'interval': 301, 'props': 'filter_l*,brush_l*,detergent_l*,dust_bag_l*'},
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
        'number_select_properties': 'target_temperature,target_water_level,spin_speed,soak_time,wash_time,drying_time',
    },
    '*.waterheater.*': {
        'sensor_properties': 'water_velocity,tds_in,tds_out',
        'switch_properties': 'water_heater.on,preheating,cruise_press',
    },
    '*.waterpuri.*': {
        'sensor_properties': 'water_purifier.temperature,tds_in,tds_out',
    },

}
DEVICE_CUSTOMIZES.update({item: DEVICE_CUSTOMIZES[src] for src, dest in {
    'mrbond.airer.m31a': [
        'hyd.airer.h51a',
        'hyd.airer.h51c',
        'hyd.airer.hx1',
        'hyd.airer.hx2',
        'hyd.airer.hx3',
        'mrbond.airer.m31a2',
        'mrbond.airer.m31c',
        'mrbond.airer.m31c2',
        'mrbond.airer.m33a',
        'mrbond.airer.m33c',
    ],

    '*.airpurifier.*': ['*.airp.*'],
    '*.lock.*': ['*.door.*'],
    '*.dry.*': ['*.dryer.*'],
    '*.cooker.*': ['*.pre_cooker.*'],
}.items() for item in dest})


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
        'class': MiotFanConv,
        'services': ['fan', 'ceiling_fan', 'air_fresh', 'air_purifier', 'hood'],
        'converters' : [
            {'props': ['on']},
            {'props': ['mode', 'fan_control.mode'], 'desc': True},
            {'props': ['*.stepless_fan_level', '*.speed_level']},
            {'props': ['fan_level', 'fan_control.fan_level'], 'desc': True},
            {'props': ['*.favorite_level']},
            {'props': ['horizontal_swing', 'fan_control.horizontal_swing']},
            {'props': ['vertical_swing', 'fan_control.vertical_swing']},
            {'props': ['*.uv', '*.anion', '*.plasma'], 'domain': 'switch'},
        ],
    },
    {
        'class': MiotClimateConv,
        'services': ['air_conditioner', 'heater', 'thermostat', 'ptc_bath_heater'],
        'converters' : [
            {'props': ['on', 'target_temperature']},
            {'props': ['indoor_temperature', 'temperature']},
            {'props': ['environment.indoor_temperature', 'environment.temperature']},
            {'props': ['relative_humidity', 'humidity', 'target_humidity']},
            {'props': ['environment.relative_humidity', 'environment.humidity']},
            {'props': ['mode', 'fan_control.mode'], 'desc': True},
            {'props': ['fan_level', 'fan_control.fan_level', 'heat_level'], 'desc': True},
            {'props': ['horizontal_swing', 'fan_control.horizontal_swing'], 'domain': 'switch'},
            {'props': ['vertical_swing', 'fan_control.vertical_swing'], 'domain': 'switch'},
            {'props': ['*.uv', 'heater', 'eco', 'dryer', 'sleep_mode', 'soft_wind'], 'domain': 'switch'},
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
        'class': MiotCameraConv,
        'services': ['camera_control', 'video_doorbell'],
        'converters' : [
            {'props': ['battery_level'], 'domain': 'sensor'},
        ],
    },
    {
        'class': MiotHumidifierConv,
        'services': ['humidifier', 'dehumidifier'],
        'converters' : [
            {'props': ['on', 'target_humidity']},
            {'props': ['mode'], 'desc': True},
            {'props': ['relative_humidity', 'humidity']},
            {'props': ['environment.relative_humidity', 'environment.humidity']},
            {'props': ['fan_level', 'fan_control.fan_level'], 'desc': True, 'domain': 'select'},
        ],
    },
    {
        'services': ['alarm'],
        'converters' : [
            {'props': ['alarm'], 'domain': 'switch', 'option': {'entity_category': 'config'}},
            {'props': ['volume'], 'domain': 'number', 'option': {'entity_category': 'config'}},
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
        'services': ['vacuum'],
        'converters' : [
            {'domain': 'sensor', 'props': ['status', 'cleaning_area', 'cleaning_time']},
            {'domain': 'sensor', 'props': ['water_check_status', '*_life_level', '*_left_level']},
            {'domain': 'binary_sensor', 'props': ['mop_status', 'sleep_status']},
            {'domain': 'switch', 'props': [
                'sweep_break_switch', 'enable_mop_wash', 'auto_dust_arrest', 'auto_mop_dry',
                'mop_auto_lift', 'mop_outer_swing', 'auto_water_change', 'no_disturb',
            ], 'all_services': True},
            {'domain': 'switch', 'props': [
                'use_detergent', 'detergent_self_delivery', 'edge_swing_tail_sweep', 'detergent_depletion_reminder',
                'carpet_boost', 'carpet_avoidance', 'carpet_display', 'carpet_deep_cleaning', 'carpet_discriminate',
                'sweep_carpet_first', 'ai_cleaning', 'sweep_ai_detection', 'ai_managed_cleaning', 'defecation_detection',
                'dirt_detection', 'object_detection', 'room_detection', 'solid_dirt_detection', 'liquid_dirt_detection',
                'floor_material_detection', 'cut_hair_config', 'hot_water_mop_wash',
            ], 'all_services': True, 'option': {'entity_category': 'config'}},
            {'domain': 'select', 'props': [
                'mode', 'sweep_mop_type', 'sweep_type', 'sweep_route', 'clean_times', 'edge_sweep_frequency',
                'drying_time', 'dust_arrest_frequency', 'mop_water_output_level', 'mop_water_output_level_no_tank',
            ], 'all_services': True},
            {'domain': 'select', 'props': [
                'frequency_mop_wash', 'frequency_mop_wash_no_tank', 'carpet_cleaning_method', 'mop_outer_swing_frequency',
                'water_output_for_washing_mop', 'obstacle_avoidance_strategy', 'detergent_self_delivery_level',
                'worry_free_clean_mode', 'auto_dust_arrest_power_level', 'wash_mop_water_temperature',
            ], 'all_services': True, 'option': {'entity_category': 'config'}},
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
                    'temperature', 'indoor_temperature', 'outdoor_temperature', 'relative_humidity', 'humidity',
                    'pm2_5_density', 'pm10_density', 'co_density', 'co2_density', 'tvoc_density', 'voc_density',
                    'hcho_density', 'ch4_density', 'illumination', 'atmospheric_pressure',
                    'air_quality', 'air_quality_index',
                ],
                'domain': 'sensor',
                'exclude_format': ['bool'],
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
        'services': ['toilet', 'seat'],
        'converters' : [
            {'props': ['on', 'deodorization'], 'domain': 'switch'},
            {'props': ['status'], 'domain': 'sensor'},
            {'props': ['seating_state'], 'domain': 'binary_sensor'},
            {'props': ['heat_level', 'washing_strength', 'nozzle_position'], 'domain': 'select'},
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
