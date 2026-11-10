# Dehumidifier alerts

`dmaker.derh.22ht` automatically adds ten sensors: **Tank full**, **Filter cleaning
due**, **Defrosting**, temperature/humidity sensor fault, coil temperature sensor
fault, internal communication fault, fan fault, compressor overload protection,
low refrigerant protection, and operating temperature out of range.

- Select these sensors directly in automations. All are enabled; disable unwanted
  ones in their entity settings.
- The device reports one condition at a time. Defrosting is normal operation.
- Sensors share the existing reading, normally updated every two minutes. No
  extra requests are added. Existing raw fault sensors keep their settings.
- Unknown codes show **unknown**; failed readings show **unavailable**. After a
  restart, sensors wait for a fresh reading.

Code meanings come from Xiaomi's [specification](https://miot-spec.org/miot-spec-v2/instance?type=urn:miot-spec-v2:device:dehumidifier:0000A02D:dmaker-22ht:1)
and [translations](https://miot-spec.org/instance/v2/multiLanguage?urn=urn:miot-spec-v2:device:dehumidifier:0000A02D:dmaker-22ht:1).
