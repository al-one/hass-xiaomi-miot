# Dehumidifier reported conditions

The `dmaker.derh.22ht` dehumidifier automatically provides these binary sensors
under its existing Home Assistant device. Tank full and Filter cleaning due can
be selected directly in automations; no property customization or template
helper is required.

| Device code | Entity | Category |
| --- | --- | --- |
| 1 | Tank full | Sensor |
| 2 | Temperature and humidity sensor fault | Diagnostic |
| 3 | Coil temperature sensor fault | Diagnostic |
| 4 | Internal communication fault | Diagnostic |
| 5 | Filter cleaning due | Sensor |
| 6 | Defrosting | Sensor |
| 7 | Fan fault | Diagnostic |
| 8 | Compressor overload protection | Diagnostic |
| 9 | Low refrigerant protection | Diagnostic |
| 10 | Operating temperature out of range | Sensor |

Alerts use Home Assistant's **problem** binary sensor class (problem detected /
OK). Defrosting is a normal operating condition and uses on / off. All ten
entities are enabled by default; unwanted entities can be disabled individually
in the entity settings.

These are comparisons against one device-reported enum, not ten independent
physical measurements. Code 0 means no condition is currently reported. A
different reported code makes the other comparisons off; it does not prove that
multiple physical issues cannot coexist. Low refrigerant protection is a device
report, not a measurement of refrigerant quantity or a confirmed leak diagnosis.
Internal communication fault refers to communication inside the appliance.

An unrecognized value produces **unknown**. A failed or missing requested source
read produces **unavailable** until the source succeeds, even if temperature
reads continue working. Offline devices are unavailable. Old condition states
are not restored as current measurements after a Home Assistant restart.

All conditions share the existing `dehumidifier.fault` property response; no
polls are added. The default dehumidifier schedule reads this property every
120 seconds, so automations may take up to the next successful poll to react.
Existing polling customizations still apply. The existing raw Device Fault
sensor, if already configured, retains its name, unique ID, and state values.

For a notification, create an automation with the **Tank full** entity changing
to **problem detected** as its trigger, then choose your notification action.
The integration does not send notifications automatically.

Only this reviewed model and schema are expanded. Other models may use different
properties, codes or protocols and need their own verified profile.

## Schema evidence and testing

The fixtures were captured on 27 October 2026 from Xiaomi's specification
endpoints using the integration's existing schema URN:

- [Instance schema](https://miot-spec.org/miot-spec-v2/instance?type=urn:miot-spec-v2:device:dehumidifier:0000A02D:dmaker-22ht:1)
- [Vendor translations](https://miot-spec.org/instance/v2/multiLanguage?urn=urn:miot-spec-v2:device:dehumidifier:0000A02D:dmaker-22ht:1)

The source is service 2, property 2, `uint8`, read/notify. Vendor English and
Chinese translations identify the two sensor faults and compressor protection
more precisely than the schema's generic English labels. Labels are used to
review the profile, never to compare live values or generate entity identities.

Automated tests exercise all eleven enum values, malformed/unknown values,
source failures, partial updates, offline recovery, entity metadata and existing
raw sensor compatibility. This change has not been tested on physical hardware.
A natural full-tank to empty-tank transition should be verified before release;
component faults should not be deliberately induced.

## Contribution scope and previous discussions

[Issue #2863](https://github.com/al-one/hass-xiaomi-miot/issues/2863) reports
the missing raw fault entity for this model. This change provides semantic
condition entities; it preserves a manually configured raw sensor and does not
change automatic raw-property discovery for other models.

[PR #2362](https://github.com/al-one/hass-xiaomi-miot/pull/2362) proposed raw
fault exposure. The maintainer objected to a five-second schedule applied across
dehumidifiers and noted that models have different properties and fault codes.
They requested model-specific support. The revised PR was closed unmerged;
the visible discussion does not explain why the revision was closed. It does
not establish a rejection of separate condition binary sensors.

This implementation addresses those concerns with one explicitly reviewed
model/schema, no new polling, and numeric comparisons independent of translated
property names. [Issue #283](https://github.com/al-one/hass-xiaomi-miot/issues/283)
also shows the maintainer helping expose a dedicated tank-full binary sensor
for a different legacy model, whose protocol is not assumed to match this one.
Settings navigation and general fault/failure discovery remain separate work.
