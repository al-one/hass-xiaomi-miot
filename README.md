# Xiaomi Miot For HomeAssistant

## Tested Devices

- xiaomi.aircondition.mt1
- xiaomi.aircondition.mt5
- xiaomi.aircondition.mc5
- yunmi.waterpuri.lx11
- lumi.curtain.hagl05
- mrbond.airer.m1pro


## Installing

> Or manually copy `xiaomi_miot` folder to `custom_components` folder in your HomeAssistant config folder

or

> You can install component with [HACS](https://hacs.xyz) custom repo: `al-one/hass-xiaomi-miot`


## Config

### HomeAssistant GUI

> Configuration > Integration > ➕ > Xiaomi Miot

### Configuration variables:

- **host**(*Required*): The IP of your device
- **token**(*Required*): The Token of your device
- **name**(*Optional*): The name of your device
- **mode**(*Optional*): `sensor,climate,cover` Guess from Model if empty


## Obtain miio token

- Use MiHome mod by [@vevsvevs](https://github.com/custom-components/ble_monitor/issues/7#issuecomment-595874419)
  1. Down apk from [СКАЧАТЬ ВЕРСИЮ 5.x.x](https://www.kapiba.ru/2017/11/mi-home.html)
  2. Create folder `/your_interlal_storage/vevs/logs/`
  3. Find token from `vevs/logs/misc/devices.txt`
