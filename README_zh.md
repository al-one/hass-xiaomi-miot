# Xiaomi Miot For HomeAssistant

[English](https://github.com/al-one/hass-xiaomi-miot/blob/master/README.md) | 简体中文

[MIoT-Spec](https://iot.mi.com/new/doc/design/spec/overall) 是小米IoT平台根据硬件产品的联网方式、产品功能的特点、用户使用场景的特征和用户对硬件产品使用体验的要求，设计的描述硬件产品功能定义的标准规范。

本插件利用了MIoT-Spec的规范，可将小米设备自动接入[HomeAssistant](https://www.home-assistant.io)，目前已支持大部分小米MIoT设备。且该插件支持HA后台界面集成，无需配置yaml即可轻松将小米设备接入HA。


## 安装

> 下载并复制`custom_components/xiaomi_miot`文件夹到HA根目录下的`custom_components`文件夹

```shell
# 执行下面的命令可以自动安装
wget -q -O - https://raw.fastgit.org/al-one/hass-xiaomi-miot/master/install.sh | bash -
```

> 或者通过[HACS](https://hacs.xyz)搜索`Xiaomi Miot Auto`安装


## 配置

> [⚙️ 配置](https://my.home-assistant.io/redirect/config) > [🧩 集成](https://my.home-assistant.io/redirect/integrations) > [➕ 添加集成](https://my.home-assistant.io/redirect/config_flow_start?domain=xiaomi_miot) > 🔍 搜索 `Xiaomi Miot Auto`

或者点击(HA v2021.3.0+): [![add](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=xiaomi_miot)

**目前有两种方式集成小米设备:**

- Add device using host/token
  > 通过设备host/token接入，适用于在局域网环境下支持miot-spec的设备

- Add devices using Mi Account
  > 通过小米账号接入设备，适用于miio、ZigBee、蓝牙（默认开启[云端模式](https://github.com/al-one/hass-xiaomi-miot#configuration-xiaomi-cloud)）

### 配置云端模式:

> 如果你的设备(**通过token集成**)`不可用`或者出现`-4004`或`-9999`错误码，你可以尝试此方法

```yaml
# configuration.yaml
xiaomi_miot:
  username: xiaomi_username
  password: xiaomi_password
  # server_country: cn # 小米云服务器位置: cn(默认), de, i2, ru, sg, us
```

为设备开启云端模式：

> [⚙️ 配置](https://my.home-assistant.io/redirect/config) > [🧩 集成](https://my.home-assistant.io/redirect/integrations) > Xiaomi Miot Auto > 选项 > ☑️ 开启云端模式


### 自定义实体

```yaml
# configuration.yaml
homeassistant:
  customize: !include customize.yaml


# customize.yaml
domain.your_entity_id:
  miot_cloud: true          # 为该实体开启云端模式 (read, write, action)
  # miot_cloud_write: true  # (可选) 仅写属性使用云端模式
  # miot_cloud_action: true # (可选) 仅action使用云端模式
  # miot_local: true        # 使用本地模式 (通过账号接入的设备)

climate.your_entity_id:
  bind_sensor: sensor.temperature_entity,sensor.humidity_entity # 绑定传感器实体

camera.your_entity_id:
  video_attribute: 1   # https://github.com/al-one/hass-xiaomi-miot/issues/11#issuecomment-773054167
  keep_streaming: true # 持续更新流地址
  check_lan: true      # 云端模式下检查设备在局域网是否可用

cover.your_entity_id:
  closed_position: 5 # 当实体位置值小于等于此值时为关闭状态

doamin.your_entity_id:
  interval_seconds: 30 # 每次更新状态间隔秒数(需要重载集成配置)
  chunk_properties: 10 # 单次查询设备属性的最大个数(LAN)
```

**推荐**[使用界面自定义实体](https://www.home-assistant.io/docs/configuration/customizing-devices/#customization-using-the-ui):

> [⚙️ 配置](https://my.home-assistant.io/redirect/config) > 🖌 自定义 > 🔍 选择实体 > 选择要覆盖的属性 > 添加Other属性


## [支持的设备](https://github.com/al-one/hass-xiaomi-miot/issues/12)

- HomeAssistant设备类型
    - [Miot设备](https://miot-spec.org/miot-spec-v2/spec/devices)
    - [Miot服务](https://miot-spec.org/miot-spec-v2/spec/services)

- [sensor](https://www.home-assistant.io/integrations/sensor)
    - [air-fryer](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:air-fryer:00007897)
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
    - [health-pot](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:health-pot:00007860)
    - [illumination-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:illumination-sensor:0000783D)
    - [induction-cooker](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:device:induction-cooker:0000A033)
    - [microwave-oven](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:microwave-oven:00007843)
    - [oven](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:oven:00007862)
    - [pet-feeder](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:pet-feeder:00007847)
    - [plant-monitor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:plant-monitor:0000784B)
    - [power-consumption](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:power-consumption:0000780E)
    - [pressure-cooker](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:device:pressure-cooker:0000A04B)
    - [printer](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:printer:0000786F)
    - [router](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:router:00007864)
    - [sleep-monitor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:sleep-monitor:00007885)
    - [tds-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:tds-sensor:0000780D)
    - [temperature-humidity-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:temperature-humidity-sensor:00007814)
    - [vibration-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:vibration-sensor:0000786A)
    - [video-doorbell](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:video-doorbell:00007863)
    - [water-purifier](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:water-purifier:00007821)
- [binary_sensor](https://www.home-assistant.io/integrations/binary_sensor)
    - [magnet-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:magnet-sensor:00007827)
    - [motion-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:motion-sensor:00007825)
    - [submersion-sensor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:submersion-sensor:00007839)
    - [toilet](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:toilet:00007877)
- [air_quality](https://www.home-assistant.io/integrations/air_quality)
    - [air-monitor](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:device:air-monitor:0000A008)
    - [environment](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:environment:0000780A)
- [switch](https://www.home-assistant.io/integrations/switch)
    - [massager](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:massager:0000788E)
    - [outlet](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:switch:0000780C)
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
    - [water-dispenser](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:water-dispenser:00007891)
- [water_heater](https://www.home-assistant.io/integrations/water_heater)
    - [kettle](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:kettle:00007813)
    - [water-heater](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:water-heater:0000783E)
- [vacuum](https://www.home-assistant.io/integrations/vacuum)
    - [vacuum](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:vacuum:00007810) (不支持定点/划区清扫)
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
- [media_player](https://www.home-assistant.io/integrations/media_player)
    - [play-control](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:play-control:0000781D)
    - [speaker](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:speaker:0000781C)
    - [intelligent-speaker](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:intelligent-speaker:0000789B)
    - [television](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:television:0000781B)
- [device_tracker](https://www.home-assistant.io/integrations/device_tracker)
    - [rearview-mirror](https://miot-spec.org/miot-spec-v2/spec/service?type=urn:miot-spec-v2:service:rearview-mirror:00007879)


## 调试

### 获取实体状态属性

> [🔨 开发者工具](https://my.home-assistant.io/redirect/developer_states) > [ℹ️ 状态](https://my.home-assistant.io/redirect/developer_states) > 🔍 筛选实体

### [获取调试日志](https://www.home-assistant.io/integrations/logger)

```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.xiaomi_miot: debug
```

> [⚙️ 配置](https://my.home-assistant.io/redirect/config) > [✍️ 日志](https://my.home-assistant.io/redirect/logs)


## 获取 miio token

- 使用HomeAssistant服务
  1. [![打开HomeAssistant服务工具](https://my.home-assistant.io/badges/developer_services.svg)](https://my.home-assistant.io/redirect/developer_services/)
  2. 选择服务`xiaomi_miot.get_token`，输入实体ID和设备名称
  3. 在HA通知列表中找到token

- 使用[@vevsvevs](https://github.com/custom-components/ble_monitor/issues/7#issuecomment-595874419)修改版的米家
  1. 下载APK [СКАЧАТЬ ВЕРСИЮ 6.x.x](https://www.kapiba.ru/2017/11/mi-home.html)
  2. 创建目录`/sdcard/vevs/logs/` ⚠️
  3. 在`vevs/logs/misc/devices.txt`文件中找到token
