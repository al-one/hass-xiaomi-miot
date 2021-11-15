[![version](https://img.shields.io/github/manifest-json/v/al-one/hass-xiaomi-miot?filename=custom_components%2Fxiaomi_miot%2Fmanifest.json)](https://github.com/al-one/hass-xiaomi-miot/releases/latest)
[![releases](https://img.shields.io/github/downloads/al-one/hass-xiaomi-miot/total)](https://github.com/al-one/hass-xiaomi-miot/releases)
[![stars](https://img.shields.io/github/stars/al-one/hass-xiaomi-miot)](https://github.com/al-one/hass-xiaomi-miot/stargazers)
[![issues](https://img.shields.io/github/issues/al-one/hass-xiaomi-miot)](https://github.com/al-one/hass-xiaomi-miot/issues)
[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg)](https://hacs.xyz)

# Xiaomi Miot For HomeAssistant

[English](https://github.com/al-one/hass-xiaomi-miot/blob/master/README.md) | 简体中文

[MIoT-Spec](https://iot.mi.com/new/doc/design/spec/overall) 是小米IoT平台根据硬件产品的联网方式、产品功能的特点、用户使用场景的特征和用户对硬件产品使用体验的要求，设计的描述硬件产品功能定义的标准规范。

本插件利用了**miot**协议的规范，可将小米设备自动接入[HomeAssistant](https://www.home-assistant.io)，目前已支持大部分小米米家智能设备。且该插件支持HA后台界面集成，无需配置yaml即可轻松将小米设备接入HA。


## 安装

> 下载并复制`custom_components/xiaomi_miot`文件夹到HA根目录下的`custom_components`文件夹

```shell
# 执行下面的命令可以自动安装
wget -q -O - https://cdn.jsdelivr.net/gh/al-one/hass-xiaomi-miot/install.sh | bash -

# 如果遇到下载缓慢或下载失败可以执行下面的命令
wget -q -O - https://cdn.jsdelivr.net/gh/al-one/hass-xiaomi-miot/install.sh | HUB_DOMAIN=hub.fastgit.org bash -
```

> 或者通过[HACS](https://hacs.xyz)搜索`Xiaomi Miot Auto`安装


## 配置

> [⚙️ 配置](https://my.home-assistant.io/redirect/config) > [🧩 集成](https://my.home-assistant.io/redirect/integrations) > [➕ 添加集成](https://my.home-assistant.io/redirect/config_flow_start?domain=xiaomi_miot) > 🔍 搜索 `Xiaomi Miot Auto`

或者点击: [![添加集成](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=xiaomi_miot)

### 账号集成 (Add devices using Mi Account):
自v0.4.4版本开始，插件新增支持账号集成时选择连接设备的模式：
- **自动模式**：插件定期更新[支持本地miot协议的设备](https://github.com/al-one/hass-xiaomi-miot/blob/master/custom_components/xiaomi_miot/core/miot_local_devices.py)，并自动将用户筛选的设备中符合条件的型号使用本地连接（推荐）
- **本地模式**：集成配置所筛选的设备都将使用本地连接，如勾选了不支持本地miot协议的设备将不可用
- **云端模式**：集成配置所筛选的设备都将使用云端连接，建议旧版miio、蓝牙、ZigBee设备使用

### 本地集成 (Add device using host/token):
通过host/token接入设备，适用于在局域网环境下支持miot协议的设备

### 配置云端模式:

> 为**通过token集成的设备**开启云端模式

```yaml
# configuration.yaml
xiaomi_miot:
  username: xiaomi_username
  password: xiaomi_password
  # server_country: cn # 小米云服务器位置: cn(默认), de, i2, ru, sg, us
```

> [⚙️ 配置](https://my.home-assistant.io/redirect/config) > [🧩 集成](https://my.home-assistant.io/redirect/integrations) > Xiaomi Miot Auto > 选项 > ☑️ 开启云端模式

### 配置翻译词典:

```yaml
# configuration.yaml
xiaomi_miot:
  language: zh # 使用内置词典，目前仅支持`zh`
  # https://github.com/al-one/hass-xiaomi-miot/blob/master/custom_components/xiaomi_miot/core/translation_languages.py
  translations:
    # 全局词典，对所有实体生效
    idle: '空闲'
    busy: '工作中'
    # 指定风扇模式的词典
    fan.mode:
      'straight wind': '直吹模式'
      'natural wind': '自然风'
    # 指定洗衣机烘干模式的词典
    washer.drying_level:
      moist: '微湿'
      extra: '特干'
```


### 自定义实体

```yaml
# configuration.yaml
homeassistant:
  customize: !include customize.yaml

# 通过设备型号自定义
xiaomi_miot:
  # https://github.com/al-one/hass-xiaomi-miot/blob/master/custom_components/xiaomi_miot/core/device_customizes.py
  device_customizes:
    'chuangmi.plug.212a01':
      miot_local: true
      chunk_properties: 7


# 通过父实体自定义
# customize.yaml
domain.your_entity_id:
  miot_local: true        # 使用本地模式 (通过账号接入的设备)
  miot_cloud: true        # 为该实体开启云端模式 (read, write, action)
  miot_cloud_write: true  # 仅写属性使用云端模式
  miot_cloud_action: true # 仅action使用云端模式
  check_lan: true         # 云端模式下检查设备在局域网是否可用
  miio_properties: power,battery # 获取miio属性到实体的属性中
  miio_cloud_props: prop.power,event.dev_online

# 自定义子实体
domain.parent_entity_id:
  sensor_properties: temperature,humidity,illumination # Miot属性
  binary_sensor_properties: is_volume_muted,any_boolen_property
  switch_properties: on,power
  number_properties: volume
  select_properties: mode
  fan_properties: mode,fan_level
  cover_properties: motor_control

climate.your_entity_id:
  bind_sensor: sensor.temperature_entity,sensor.humidity_entity # 绑定传感器实体

camera.your_entity_id:
  video_attribute: 1   # https://github.com/al-one/hass-xiaomi-miot/issues/11#issuecomment-773054167
  keep_streaming: true # 持续更新流地址

cover.your_entity_id:
  closed_position: 5   # 当实体位置值小于等于此值时为关闭状态
  deviated_position: 2 # 位置偏差值 2% -> 0%, 98% -> 100%
  motor_reverse: true  # 反转电机状态
  open_texts: 打开,升
  close_texts: 关闭,降

doamin.your_entity_id:
  interval_seconds: 30 # 每次更新状态间隔秒数(需要重载集成配置)
  chunk_properties: 10 # 单次查询设备属性的最大个数(LAN)
```

**推荐**[使用界面自定义实体](https://github.com/al-one/hass-xiaomi-miot/issues/100#issuecomment-864678774):

> [⚙️ 配置](https://my.home-assistant.io/redirect/config) > [🖌 自定义](https://github.com/al-one/hass-xiaomi-miot/issues/100#issuecomment-864678774) > 🔍 选择实体 > 选择要覆盖的属性 > 添加Other属性


## [支持的设备](https://github.com/al-one/hass-xiaomi-miot/issues/12)

- [插座](https://home.miot-spec.com/s/plug) / [开关](https://home.miot-spec.com/s/switch)
- [智能灯](https://home.miot-spec.com/s/light)
- [空调](https://home.miot-spec.com/s/aircondition) / [空调伴侣](https://home.miot-spec.com/s/acpartner) / [温控器](https://home.miot-spec.com/s/airrtc)
- [风扇](https://home.miot-spec.com/s/fan) / [凉霸](https://home.miot-spec.com/s/ven_fan)
- [浴霸](https://home.miot-spec.com/s/bhf_light) / [取暖器](https://home.miot-spec.com/s/heater)
- [摄像头](https://home.miot-spec.com/s/camera) / [猫眼/可视门铃](https://home.miot-spec.com/s/cateye) [❓️](https://github.com/al-one/hass-xiaomi-miot/issues/100#issuecomment-903078604)
- [电视](https://home.miot-spec.com/s/tv) / [投影仪](https://home.miot-spec.com/s/projector) / [机顶盒](https://home.miot-spec.com/s/tvbox)
- [小爱音箱](https://home.miot-spec.com/s/wifispeaker) [❓️](https://github.com/al-one/hass-xiaomi-miot/issues/100#issuecomment-885989099)
- [万能遥控器](https://home.miot-spec.com/s/chuangmi.remote) [❓️](https://github.com/al-one/hass-xiaomi-miot/commit/fbcc8063783e53b9480574536a034d338634f4e8#commitcomment-56563663)
- [智能门锁](https://home.miot-spec.com/s/look) / [智慧门](https://home.miot-spec.com/s/door)
- [洗衣机](https://home.miot-spec.com/s/washer) / [冰箱](https://home.miot-spec.com/s/fridge)
- [净水器](https://home.miot-spec.com/s/waterpuri) / [饮水机](https://home.miot-spec.com/s/kettle)
- [空气净化器](https://home.miot-spec.com/s/airpurifier) / [新风机](https://home.miot-spec.com/s/airfresh)
- [温湿度传感器](https://home.miot-spec.com/s/sensor_ht) / [水侵传感器](https://home.miot-spec.com/s/flood) / [烟雾传感器](https://home.miot-spec.com/s/sensor_smoke)
- [电饭煲](https://home.miot-spec.com/s/cooker) / [压力锅](https://home.miot-spec.com/s/pre_cooker)
- [电磁炉](https://home.miot-spec.com/s/ihcooker) / [烤箱](https://home.miot-spec.com/s/oven) / [微波炉](https://home.miot-spec.com/s/microwave)
- [空气炸锅](https://home.miot-spec.com/s/fryer) / [多功能锅](https://home.miot-spec.com/s/mfcp)
- [养生壶](https://home.miot-spec.com/s/health_pot) / [咖啡机](https://home.miot-spec.com/s/coffee)
- [破壁机](https://home.miot-spec.com/s/juicer) / [搅拌机](https://home.miot-spec.com/s/juicer)
- [热水器](https://home.miot-spec.com/s/waterheater) / [油烟机](https://home.miot-spec.com/s/hood) / [洗碗机](https://home.miot-spec.com/s/dishwasher)
- [窗帘电机](https://home.miot-spec.com/s/curtain) / [开窗器](https://home.miot-spec.com/s/wopener) / [晾衣机](https://home.miot-spec.com/s/airer)
- [扫地/扫拖机器人](https://home.miot-spec.com/s/vacuum)
- [加湿器](https://home.miot-spec.com/s/humidifier) / [除湿器](https://home.miot-spec.com/s/derh)
- [空气检测仪](https://home.miot-spec.com/s/airmonitor) / [植物检测仪](https://home.miot-spec.com/s/plantmonitor)
- [电动床](https://home.miot-spec.com/s/bed) / [电热毯/水暖床垫](https://home.miot-spec.com/s/blanket) / [睡眠监测仪](https://home.miot-spec.com/s/lunar)
- [按摩椅](https://home.miot-spec.com/s/massage) / [按摩仪](https://home.miot-spec.com/s/magic_touch)
- [走步机](https://home.miot-spec.com/s/walkingpad)
- [马桶(盖)](https://home.miot-spec.com/s/toilet)
- [毛巾架](https://home.miot-spec.com/s/.tow)
- [宠物喂食器](https://home.miot-spec.com/s/feeder) / [宠物饮水机](https://home.miot-spec.com/s/pet_waterer)
- [鱼缸](https://home.miot-spec.com/s/fishbowl)
- [驱蚊器](https://home.miot-spec.com/s/mosq) / [消毒/灭菌灯](https://home.miot-spec.com/s/s_lamp)
- [智能后视镜](https://home.miot-spec.com/s/rv_mirror) / [抬头显示HUD](https://home.miot-spec.com/s/hud)
- [智能/儿童手表](https://home.miot-spec.com/s/watch)
- [人体传感器](https://home.miot-spec.com/s/motion) / [门窗传感器](https://home.miot-spec.com/s/magnet) [❓️](https://github.com/al-one/hass-xiaomi-miot/issues/100#issuecomment-909031222)
- [动静贴](https://home.miot-spec.com/s/vibration)
- [路由器](https://home.miot-spec.com/s/router)
- [打印机](https://home.miot-spec.com/s/printer)


## 调试

### 获取实体状态属性

> [🔨 开发者工具](https://my.home-assistant.io/redirect/developer_states) > [ℹ️ 状态](https://my.home-assistant.io/redirect/developer_states) > 🔍 筛选实体

### [获取调试日志](https://www.home-assistant.io/integrations/logger)

```yaml
# 使用HA服务 (无需重启)
service: logger.set_level
data:
  custom_components.xiaomi_miot: debug

# 或者修改 configuration.yaml (需重启)
logger:
  default: warning
  logs:
    custom_components.xiaomi_miot: debug
```

> [⚙️ 配置](https://my.home-assistant.io/redirect/config) > [✍️ 日志](https://my.home-assistant.io/redirect/logs)


## 获取 miio token

- 使用HomeAssistant服务
  1. 打开HomeAssistant服务工具 [![](https://my.home-assistant.io/badges/developer_services.svg)](https://my.home-assistant.io/redirect/developer_services/)
  2. 选择服务[`xiaomi_miot.get_token`](https://my.home-assistant.io/redirect/developer_call_service/?service=xiaomi_miot.get_token)，输入设备名称关键词
  3. 在HA通知列表中找到token

- 使用[@vevsvevs](https://github.com/custom-components/ble_monitor/issues/7#issuecomment-595874419)修改版的米家
  1. 下载APK [СКАЧАТЬ ВЕРСИЮ 6.x.x](https://www.kapiba.ru/2017/11/mi-home.html) 并安装
  2. 打开米家APP > 我的 > 实验室功能
  3. 打开`Write custom log files`和`Enable app's debug mode`
  4. 重启APP后在`vevs/logs/misc/devices.txt`文件中找到token
