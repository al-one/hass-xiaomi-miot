"""Property entity ID collisions use actual converters in the same domain."""
import pytest

from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.number import NumberEntity
from custom_components.xiaomi_miot.sensor import SensorEntity


def duplicate_spec(hass, same_service=False, reverse=False):
    services = [{
        "iid": sid,
        "type": f"urn:miot-spec-v2:service:{name}:00007801:test:1",
        "properties": [{
            "iid": 1, "type": "urn:miot-spec-v2:property:status:00000001:test:1",
            "description": "Status", "format": "uint8", "access": ["read"],
            "value-range": [0, 10, 1],
        }],
    } for sid, name in [(2, "alpha"), (3, "alpha" if same_service else "beta")]]
    services[0]["properties"].append({
        "iid": 2, "type": "urn:miot-spec-v2:property:temperature:00000020:test:1",
        "description": "Distinct Reading", "format": "float", "access": ["read"],
    })
    return MiotSpec(hass, {
        "type": "urn:miot-spec-v2:device:sensor:0000A001:test-ids:1",
        "services": list(reversed(services)) if reverse else services,
    })


@pytest.mark.parametrize("same_service", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_defaults_keep_stable_ids_and_other_defaults(hass, make_device, same_service, reverse):
    device = make_device(duplicate_spec(hass, same_service, reverse), customizes={
        "converters": [], "sensor_properties": "prop.2.1,prop.3.1,prop.2.2",
    })
    entities = {c.prop.unique_prop: SensorEntity(device, c)
                for c in device.converters if c.domain == "sensor"}
    assert entities["prop.2.1"].entity_id.endswith("_alpha_2_status_1")
    assert entities["prop.3.1"].entity_id.endswith(
        "_alpha_3_status_1" if same_service else "_beta_3_status_1"
    )
    assert len({e.entity_id for e in entities.values()}) == 3
    assert entities["prop.2.2"].entity_id.endswith("_distinct_reading")


@pytest.mark.parametrize("other_domain", [None, "number"])
def test_unexposed_or_other_domain_property_does_not_change_default(hass, make_device, other_domain):
    device = make_device(duplicate_spec(hass), customizes={
        "converters": [], "sensor_properties": "prop.2.1",
        "number_properties": "prop.3.1" if other_domain else "",
    })
    sensor = next(SensorEntity(device, c) for c in device.converters if c.domain == "sensor")
    assert sensor.entity_id.endswith("_status")
    if other_domain:
        number = next(NumberEntity(device, c) for c in device.converters if c.domain == "number")
        assert number.entity_id.endswith("_status")
        assert sensor.entity_id != number.entity_id
