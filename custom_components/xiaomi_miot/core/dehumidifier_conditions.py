"""Named sensors for the status codes reported by supported dehumidifiers."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.helpers.entity import EntityCategory

from .converters import MiotConditionConv


DMAKER_22HT_DEVICE_TYPE = 'urn:miot-spec-v2:device:dehumidifier:0000A02D:dmaker-22ht:1'
DMAKER_22HT_FAULT_PROPERTY_TYPE = 'urn:miot-spec-v2:property:fault:00000009:dmaker-22ht:1'

# The device reports one status at a time. Code 0 means no reported condition;
# code 6 means normal defrosting, so it must not appear as a problem.
DMAKER_22HT_CONDITIONS = (
    (1, 'tank_full', None),
    (2, 'temperature_humidity_sensor_fault', EntityCategory.DIAGNOSTIC),
    (3, 'coil_temperature_sensor_fault', EntityCategory.DIAGNOSTIC),
    (4, 'internal_communication_fault', EntityCategory.DIAGNOSTIC),
    (5, 'filter_cleaning_due', None),
    (6, 'defrosting', None),
    (7, 'fan_fault', EntityCategory.DIAGNOSTIC),
    (8, 'compressor_overload_protection', EntityCategory.DIAGNOSTIC),
    (9, 'low_refrigerant_protection', EntityCategory.DIAGNOSTIC),
    (10, 'operating_temperature_out_of_range', None),
)
DMAKER_22HT_KNOWN_CODES = (0,) + tuple(code for code, _, _ in DMAKER_22HT_CONDITIONS)


def create_dehumidifier_condition_converters(device):
    """Create sensors only when the model and property match the documented codes."""
    if device.model != 'dmaker.derh.22ht' or device.spec.type != DMAKER_22HT_DEVICE_TYPE:
        return []
    dehumidifier_services = device.spec.get_services('dehumidifier', excludes=device._exclude_miot_services)
    fault_properties = [prop for service in dehumidifier_services for prop in service.get_properties('fault')]
    if len(fault_properties) != 1:
        return []
    fault_property = fault_properties[0]
    if (
        not fault_property.readable
        or fault_property.format != 'uint8'
        or fault_property.type != DMAKER_22HT_FAULT_PROPERTY_TYPE
        or fault_property.in_list(device._exclude_miot_properties)
        or len(fault_property.value_list) != len(DMAKER_22HT_KNOWN_CODES)
        or any(type(option.get('value')) is not int for option in fault_property.value_list)
        or {option.get('value') for option in fault_property.value_list} != set(DMAKER_22HT_KNOWN_CODES)
    ):
        return []
    # A custom polling map can omit this property even when the schema contains it.
    polled_properties = device.miot_mapping() or {}
    if not any(
        address.get('siid') == fault_property.siid and address.get('piid') == fault_property.iid
        for address in polled_properties.values()
    ):
        return []
    return [
        MiotConditionConv(
            attr=f'dehumidifier_{condition_key}',
            domain='binary_sensor',
            source_property=fault_property,
            active_code=status_code,
            known_codes=DMAKER_22HT_KNOWN_CODES,
            option={
                'device_class': None if condition_key == 'defrosting' else BinarySensorDeviceClass.PROBLEM,
                'entity_category': entity_category,
                'icon': 'mdi:snowflake-melt' if condition_key == 'defrosting' else None,
            },
        )
        for status_code, condition_key, entity_category in DMAKER_22HT_CONDITIONS
    ]
