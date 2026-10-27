"""Reviewed dehumidifier condition profiles, independent of translated labels."""

from .converters import MiotConditionConv


DMAKER_22HT_URN = 'urn:miot-spec-v2:device:dehumidifier:0000A02D:dmaker-22ht:1'

# The device reports one enum, not independent physical fault bits. Code 6 is
# normal defrost operation; the other entries are reported alerts/protections.
# code, semantic key, diagnostic category
DMAKER_22HT_CONDITIONS = (
    (1, 'tank_full', False),
    (2, 'temperature_humidity_sensor_fault', True),
    (3, 'coil_temperature_sensor_fault', True),
    (4, 'internal_communication_fault', True),
    (5, 'filter_cleaning_due', False),
    (6, 'defrosting', False),
    (7, 'fan_fault', True),
    (8, 'compressor_overload_protection', True),
    (9, 'low_refrigerant_protection', True),
    (10, 'operating_temperature_out_of_range', False),
)


def dehumidifier_condition_converters(device):
    """Expand only a reviewed model/schema; never guess another model's codes."""
    if device.model != 'dmaker.derh.22ht' or device.spec.type != DMAKER_22HT_URN:
        return []
    services = device.spec.get_services('dehumidifier', excludes=device._exclude_miot_services)
    sources = [prop for service in services for prop in service.get_properties('fault')]
    if len(sources) != 1:
        return []
    source = sources[0]
    if (
        not source.readable
        or source.format != 'uint8'
        or source.type != 'urn:miot-spec-v2:property:fault:00000009:dmaker-22ht:1'
        or source.in_list(device._exclude_miot_properties)
        or len(source.value_list) != 11
        or any(type(v.get('value')) is not int for v in source.value_list)
        or {v.get('value') for v in source.value_list} != set(range(11))
    ):
        return []
    mapping = device.miot_mapping() or {}
    if not any(m.get('siid') == source.siid and m.get('piid') == source.iid for m in mapping.values()):
        return []
    return [
        MiotConditionConv(
            attr=f'dehumidifier_{key}',
            domain='binary_sensor',
            source=source,
            value=code,
            values=tuple(range(11)),
            option={
                'device_class': None if key == 'defrosting' else 'problem',
                'entity_category': 'diagnostic' if diagnostic else None,
                'icon': 'mdi:snowflake-melt' if key == 'defrosting' else None,
            },
        )
        for code, key, diagnostic in DMAKER_22HT_CONDITIONS
    ]
