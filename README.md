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

Or click: [![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=xiaomi_miot)

### Add devices using Mi Account
Starting from the v0.4.4 version, the component has added support for selecting the connection device mode when account integration:
**Automatic**: The component will regularly update [the devices that support miot protocol in LAN](https://github.com/al-one/hass-xiaomi-miot/blob/master/custom_components/xiaomi_miot/core/miot_local_devices.py), and automatically use the local connection for the supported devices (recommended)
**Local**: All devices filtered by the integrated configuration will use local connection. If you check the devices that do not support miot in LAN, they will be unavailable
**Cloud**: All devices filtered by the integrated configuration will use cloud connection. It is recommended that miio, BLE, ZigBee devices use this mode

### Add device using host/token
Suitable for devices supporting miot-spec in LAN

### Config Xiaomi Cloud:

> Config Xiaomi cloud for the devices **integrated by host/token**

```yaml
# configuration.yaml
xiaomi_miot:
  username: xiaomi_username
  password: xiaomi_password
  # server_country: cn # location of xiaomi cloud: cn(default), de, i2, ru, sg, us
```

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

> [⚙️ Configuration](https://my.home-assistant.io/redirect/config) > [🖌 Customize](https://www.home-assistant.io/docs/configuration/customizing-devices/#customization-using-the-ui) > 🔍 Select Entity > Add Other Attribute


## [Supported Devices](https://github.com/al-one/hass-xiaomi-miot/issues/12)

- [outlet](https://home.miot-spec.com/s/plug) / [switch](https://home.miot-spec.com/s/switch)
- [light](https://home.miot-spec.com/s/light)
- [air-conditioner](https://home.miot-spec.com/s/aircondition) / [air-conditioner-outlet](https://home.miot-spec.com/s/acpartner) / [thermostat](https://home.miot-spec.com/s/airrtc)
- [fan](https://home.miot-spec.com/s/fan) / [ceiling-fan](https://home.miot-spec.com/s/ven_fan)
- [bath-heater](https://home.miot-spec.com/s/bhf_light) / [heater](https://home.miot-spec.com/s/heater)
- [camera](https://home.miot-spec.com/s/camera) / [video-doorbell](https://home.miot-spec.com/s/cateye) [❓️](https://github.com/al-one/hass-xiaomi-miot/issues/100#issuecomment-903078604)
- [television](https://home.miot-spec.com/s/tv)
- [intelligent-speaker](https://home.miot-spec.com/s/wifispeaker) [❓️](https://github.com/al-one/hass-xiaomi-miot/issues/100#issuecomment-885989099)
- [ir-remote-control](https://home.miot-spec.com/s/chuangmi.remote) [❓️](https://github.com/al-one/hass-xiaomi-miot/commit/fbcc8063783e53b9480574536a034d338634f4e8#commitcomment-56563663)
- [lock](https://home.miot-spec.com/s/look) / [door](https://home.miot-spec.com/s/door)
- [washer](https://home.miot-spec.com/s/washer) / [fridge](https://home.miot-spec.com/s/fridge)
- [water-purifier](https://home.miot-spec.com/s/waterpuri) / [kettle](https://home.miot-spec.com/s/kettle)
- [air-purifier](https://home.miot-spec.com/s/airpurifier) / [air-fresh](https://home.miot-spec.com/s/airfresh)
- [temperature-humidity-sensor](https://home.miot-spec.com/s/sensor_ht) / [submersion-sensor](https://home.miot-spec.com/s/flood) / [smoke-sensor](https://home.miot-spec.com/s/sensor_smoke)
- [cooker](https://home.miot-spec.com/s/cooker) / [pressure-cooker](https://home.miot-spec.com/s/pre_cooker)
- [induction-cooker](https://home.miot-spec.com/s/ihcooker) / [oven](https://home.miot-spec.com/s/oven) / [microwave](https://home.miot-spec.com/s/microwave)
- [air-fryer](https://home.miot-spec.com/s/fryer) / [multifunction-cooking-pot](https://home.miot-spec.com/s/mfcp)
- [health-pot](https://home.miot-spec.com/s/health_pot) / [coffee-machine](https://home.miot-spec.com/s/coffee)
- [juicer](https://home.miot-spec.com/s/juicer)
- [water-heater](https://home.miot-spec.com/s/waterheater) / [hood](https://home.miot-spec.com/s/hood) / [dishwasher](https://home.miot-spec.com/s/dishwasher)
- [curtain](https://home.miot-spec.com/s/curtain) / [window-opener](https://home.miot-spec.com/s/wopener) / [airer](https://home.miot-spec.com/s/airer)
- [vacuum](https://home.miot-spec.com/s/vacuum)
- [humidifier](https://home.miot-spec.com/s/humidifier) / [dehumidifier](https://home.miot-spec.com/s/derh)
- [air-monitor](https://home.miot-spec.com/s/airmonitor) / [plant-monitor](https://home.miot-spec.com/s/plantmonitor)
- [bed](https://home.miot-spec.com/s/bed) / [blanket](https://home.miot-spec.com/s/blanket) / [sleep-monitor](https://home.miot-spec.com/s/lunar)
- [massager](https://home.miot-spec.com/s/massage) / [magic-touch](https://home.miot-spec.com/s/magic_touch)
- [walking-pad](https://home.miot-spec.com/s/walkingpad)
- [toilet](https://home.miot-spec.com/s/toilet)
- [towel-rack](https://home.miot-spec.com/s/.tow)
- [pet-feeder](https://home.miot-spec.com/s/feeder) / [pet-drinking-fountain](https://home.miot-spec.com/s/pet_waterer)
- [fish-tank](https://home.miot-spec.com/s/fishbowl)
- [mosquito-dispeller](https://home.miot-spec.com/s/mosq) / [germicidal-lamp](https://home.miot-spec.com/s/s_lamp)
- [rearview-mirror](https://home.miot-spec.com/s/rv_mirror)
- [watch](https://home.miot-spec.com/s/watch)
- [motion-sensor](https://home.miot-spec.com/s/motion) / [magnet-sensor](https://home.miot-spec.com/s/magnet) [❓️](https://github.com/al-one/hass-xiaomi-miot/issues/100#issuecomment-909031222)
- [vibration-sensor](https://home.miot-spec.com/s/vibration)
- [router](https://home.miot-spec.com/s/router)
- [printer](https://home.miot-spec.com/s/printer)


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
- [Xiaomi Cloud Tokens Extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor)
  1. Download and run [token_extractor.exe](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor/blob/master/token_extractor.exe) for Windows or install [for Python](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor#other-platforms)
  2. Enter username, password and your server region
  3. Extracts tokens from your cloud account. Also reveals the bind_key for BT devices
