[![version](https://img.shields.io/github/manifest-json/v/al-one/hass-xiaomi-miot?filename=custom_components%2Fxiaomi_miot%2Fmanifest.json)](https://github.com/al-one/hass-xiaomi-miot/releases/latest)
[![releases](https://img.shields.io/github/downloads/al-one/hass-xiaomi-miot/total)](https://github.com/al-one/hass-xiaomi-miot/releases)
[![stars](https://img.shields.io/github/stars/al-one/hass-xiaomi-miot)](https://github.com/al-one/hass-xiaomi-miot/stargazers)
[![issues](https://img.shields.io/github/issues/al-one/hass-xiaomi-miot)](https://github.com/al-one/hass-xiaomi-miot/issues)
[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg)](https://hacs.xyz)

# Xiaomi Miot For HomeAssistant

English | [简体中文](https://github.com/al-one/hass-xiaomi-miot/blob/master/README_zh.md)

[MIoT-Spec](https://iot.mi.com/new/doc/design/spec/overall): The protocol specification for Xiaomi IoT devices, is a standard designed by the Xiaomi IoT platform to describe the function definition of hardware products according to the networking mode of hardware products, the characteristics of product functions, the characteristics of user usage scenarios and the user's requirements for hardware product use experience specification.

This component uses the MIoT-Spec to automatically integrate Xiaomi devices into [HomeAssistant](https://www.home-assistant.io), and currently supports most Xiaomi MIoT devices. And it supports HA Web UI, and you can easily integrate Xiaomi devices into HA without configuring yaml.


## Installing

> Download and copy `custom_components/xiaomi_miot` folder to `custom_components` folder in your HomeAssistant config folder

```shell
# Auto install via terminal shell
wget -q -O - https://cdn.jsdelivr.net/gh/al-one/hass-xiaomi-miot/install.sh | bash -
```

> Or you can install component with [HACS](https://hacs.xyz)


## Config

> [⚙️ Configuration](https://my.home-assistant.io/redirect/config) > [🧩 Integrations](https://my.home-assistant.io/redirect/integrations) > [➕ Add Integration](https://my.home-assistant.io/redirect/config_flow_start?domain=xiaomi_miot) > 🔍 Search `Xiaomi Miot Auto`

Or click (HA v2021.3+): [![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=xiaomi_miot)

**You have two ways to integrate xiaomi devices:**

- Add devices using Mi Account
  > Suitable for miio, ble and ZigBee devices ([miot_cloud](https://github.com/al-one/hass-xiaomi-miot#configuration-xiaomi-cloud) will be enabled)

- Add device using host/token
  > Suitable for devices supporting miot-spec in LAN

### Config Xiaomi Cloud:

> If your device (**integrate by token**) unavailable or return code -4004 or -9999 in logs, You can try this way.

```yaml
# configuration.yaml
xiaomi_miot:
  username: xiaomi_username
  password: xiaomi_password
  # server_country: cn # location of xiaomi cloud: cn(default), de, i2, ru, sg, us
```

Enabled miot cloud for device:

> [⚙️ Configuration](https://my.home-assistant.io/redirect/config) > [🧩 Integrations](https://my.home-assistant.io/redirect/integrations) > Xiaomi Miot Auto > Options > ☑️ Enable miot cloud

### Config translation languages:

```yaml
# configuration.yaml
xiaomi_miot:
  language: zh # Using the built-in dictionary, currently only `zh` is supported
  # https://github.com/al-one/hass-xiaomi-miot/blob/master/custom_components/xiaomi_miot/core/translation_languages.py
  translations:
    # Global dictionary
    idle: '空闲'
    busy: '工作中'
    # Dictionary for specifying fan modes
    'fan.mode':
      'Straight Wind': '直吹模式'
      'Natural Wind': '自然风'
    # Dictionary for specifying the drying modes of the washer
    'washer.drying_level':
      moist: '微湿'
      extra: '特干'
```


### Customize entity

```yaml
# configuration.yaml
homeassistant:
  customize: !include customize.yaml

# Customize via device model
xiaomi_miot:
  # https://github.com/al-one/hass-xiaomi-miot/blob/master/custom_components/xiaomi_miot/core/device_customizes.py
  device_customizes:
    'chuangmi.plug.212a01':
      miot_local: true
      chunk_properties: 7


# Customize via parent entity
# customize.yaml
domain.your_entity_id:
  miot_local: true        # Force to read and write data in LAN (integrate by account)
  miot_cloud: true        # Enable miot cloud for entity (read, write, action)
  miot_cloud_write: true  # Enable miot cloud (only write)
  miot_cloud_action: true # Enable miot cloud (only action)
  check_lan: true         # Check LAN connection in cloud mode
  miio_properties: power,battery # Get miio properties to state attributes
  miio_cloud_props: prop.power,event.dev_online

# Custom sub entities
domain.parent_entity_id:
  sensor_properties: temperature,humidity,illumination # Miot properties
  binary_sensor_properties: is_volume_muted,any_boolen_property
  switch_properties: on,power
  number_properties: volume
  fan_properties: mode,fan_level
  cover_properties: motor_control

climate.your_entity_id:
  bind_sensor: sensor.temperature_entity,sensor.humidity_entity # Sensor entities

camera.your_entity_id:
  video_attribute: 1   # https://github.com/al-one/hass-xiaomi-miot/issues/11#issuecomment-773054167
  keep_streaming: true # Continuously update stream address

cover.your_entity_id:
  closed_position: 5   # Change cover state to closed when position <= 5%
  deviated_position: 2 # Current position deviation 2% -> 0%, 98% -> 100%
  motor_reverse: true  # Reverse motor state
  open_texts: Open,Up
  close_texts: Close,Down

doamin.your_entity_id:
  interval_seconds: 30 # Seconds between each update state (Requires reload config entry)
  chunk_properties: 10 # Chunk miot properties on update state (LAN)
```

**Recommended** [Customization Using The UI](https://www.home-assistant.io/docs/configuration/customizing-devices/#customization-using-the-ui):

> [⚙️ Configuration](https://my.home-assistant.io/redirect/config) > 🖌 Customize > 🔍 Select Entity > Add Other Attribute


## [Supported Devices](https://github.com/al-one/hass-xiaomi-miot/issues/12)

- HomeAssistant Domain
    - [Miot Device](https://miot-spec.org/miot-spec-v2/spec/devices)
    - [Miot Service](https://miot-spec.org/miot-spec-v2/spec/services)

- [sensor](https://www.home-assistant.io/integrations/sensor)
    - [air-fryer](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:air-fryer:00007897)
    - [air-monitor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:device:air-monitor:0000A008)
    - [battery](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:battery:00007805)
    - [bed](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:bed:0000785C)
    - [coffee-machine](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:coffee-machine:00007873)
    - [cooker](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:device:cooker:0000A00B)
    - [door](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:door:00007856)
    - [doorbell](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:doorbell:00007857)
    - [environment](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:environment:0000780A)
    - [filter](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:filter:0000780B)
    - [fridge-chamber](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:fridge-chamber:0000781A)
    - [fridge](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:fridge:00007819)
    - [gas-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:gas-sensor:00007837)
    - [health-pot](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:health-pot:00007860)
    - [illumination-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:illumination-sensor:0000783D)
    - [induction-cooker](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:device:induction-cooker:0000A033)
    - [lock](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:lock:00007855)
    - [microwave-oven](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:microwave-oven:00007843)
    - [oven](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:oven:00007862)
    - [pet-feeder](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:pet-feeder:00007847)
    - [plant-monitor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:plant-monitor:0000784B)
    - [power-consumption](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:power-consumption:0000780E)
    - [pressure-cooker](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:device:pressure-cooker:0000A04B)
    - [printer](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:printer:0000786F)
    - [router](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:router:00007864)
    - [sleep-monitor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:sleep-monitor:00007885)
    - [smoke-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:smoke-sensor:00007838)
    - [switch-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:switch-sensor:00007828)
    - [tds-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:tds-sensor:0000780D)
    - [temperature-humidity-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:temperature-humidity-sensor:00007814)
    - [vibration-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:vibration-sensor:0000786A)
    - [walking-pad](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:walking-pad:00007842)
    - [water-purifier](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:water-purifier:00007821)
- [binary_sensor](https://www.home-assistant.io/integrations/binary_sensor)
    - [magnet-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:magnet-sensor:00007827)
    - [motion-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:motion-sensor:00007825)
    - [submersion-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:submersion-sensor:00007839)
    - [toilet](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:toilet:00007877)
- [switch](https://www.home-assistant.io/integrations/switch)
    - [fish-tank](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:fish-tank:00007894)
    - [germicidal-lamp](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:germicidal-lamp:00007882)
    - [massager](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:massager:0000788E)
    - [mosquito-dispeller](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:mosquito-dispeller:00007886)
    - [outlet](https://miot-spec.org/miot-spec-v2/spec/device?type=urn:miot-spec-v2:device:outlet:0000A002)
    - [pet-drinking-fountain](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:pet-drinking-fountain:00007850)
    - [physical-controls-locked](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:physical-controls-locked:00007807)
    - [switch](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:switch:0000780C)
    - [washer](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:washer:00007834)
- [light](https://www.home-assistant.io/integrations/light)
    - [indicator-light](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:indicator-light:00007803)
    - [light](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:light:00007802)
    - [night-light](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:night-light:00007883)
- [fan](https://www.home-assistant.io/integrations/fan)
    - [ceiling-fan](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:ceiling-fan:00007849)
    - [fan](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:fan:00007808)
    - [hood](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:hood:0000782B)
- [climate](https://www.home-assistant.io/integrations/climate)
    - [air-conditioner-outlet](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:air-condition-outlet:000078A3)
    - [air-conditioner](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:air-conditioner:0000780F)
    - [air-fresh](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:air-fresh:00007822)
    - [air-purifier](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:device:air-purifier:0000A007)
    - [dishwasher](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:dishwasher:0000784D)
    - [electric-blanket](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:electric-blanket:00007844)
    - [heater](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:device:heater:0000A01A)
    - [light-bath-heater](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:light-bath-heater:0000783A)
    - [ptc-bath-heater](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:ptc-bath-heater:0000783B)
    - [thermostat](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:thermostat:0000784A)
    - [water-dispenser](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:water-dispenser:00007891)
- [water_heater](https://www.home-assistant.io/integrations/water_heater)
    - [kettle](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:kettle:00007813)
    - [water-heater](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:water-heater:0000783E)
- [vacuum](https://www.home-assistant.io/integrations/vacuum)
    - [vacuum](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:vacuum:00007810)
- [cover](https://www.home-assistant.io/integrations/cover)
    - [airer](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:airer:00007817)
    - [backrest-control](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:backrest-control:0000782A)
    - [curtain](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:curtain:00007816)
    - [leg-rest-control](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:leg-rest-control:00007859)
    - [window-opener](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:window-opener:00007889)
- [humidifier](https://www.home-assistant.io/integrations/humidifier)
    - [humidifier](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:device:humidifier:0000A00E)
    - [dehumidifier](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:device:dehumidifier:0000A02D)
- [camera](https://www.home-assistant.io/integrations/camera)
    - [camera-control](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:camera-control:0000782F)
    - [camera-stream-for-google-home](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:camera-stream-for-google-home:00007831)
    - [camera-stream-for-amazon-alexa](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:camera-stream-for-amazon-alexa:00007830)
    - [video-doorbell](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:video-doorbell:00007863)
- [media_player](https://www.home-assistant.io/integrations/media_player)
    - [play-control](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:play-control:0000781D)
    - [speaker](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:speaker:0000781C)
    - [intelligent-speaker](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:intelligent-speaker:0000789B)
    - [television](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:television:0000781B)
- [remote](https://www.home-assistant.io/integrations/remote)
    - [remote-control](https://miot-spec.org/miot-spec-v2/spec/device?type=urn:miot-spec-v2:device:remote-control:0000A021)
    - [ir-remote-control](https://miot-spec.org/miot-spec-v2/spec/device?type=urn:miot-spec-v2:device:ir-remote-control:0000A025)
- [device_tracker](https://www.home-assistant.io/integrations/device_tracker)
    - [rearview-mirror](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:rearview-mirror:00007879)
    - [watch](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:watch:00007899)


## Debug

### Get Entity State Attributes

> [🔨 Developer tools](https://my.home-assistant.io/redirect/developer_states) > [ℹ️ State](https://my.home-assistant.io/redirect/developer_states) > 🔍 Filter Entity

### [Get Debug Logs](https://www.home-assistant.io/integrations/logger)

```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.xiaomi_miot: debug
```

> [⚙️ Configuration](https://my.home-assistant.io/redirect/config) > [✍️ Logs](https://my.home-assistant.io/redirect/logs)


## Obtain miio token

- Use HomeAssistant Service
  1. Goto HomeAssistant service developer tool [![](https://my.home-assistant.io/badges/developer_services.svg)](https://my.home-assistant.io/redirect/developer_services/)
  2. Select [`xiaomi_miot.get_token`](https://my.home-assistant.io/redirect/developer_call_service/?service=xiaomi_miot.get_token), Enter the keyword of device name
  3. Find the token from the HA notifications

- Use MiHome mod by [@vevsvevs](https://github.com/custom-components/ble_monitor/issues/7#issuecomment-595874419)
  1. Down apk from [СКАЧАТЬ ВЕРСИЮ 6.x.x](https://www.kapiba.ru/2017/11/mi-home.html)
  2. Create folder `/sdcard/vevs/logs/` ⚠️
  3. Find the token from `vevs/logs/misc/devices.txt`
