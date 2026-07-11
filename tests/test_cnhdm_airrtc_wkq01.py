from custom_components.xiaomi_miot.climate import ClimateEntity
from custom_components.xiaomi_miot.fan import FanEntity
from custom_components.xiaomi_miot.core.converters import MiotClimateConv, MiotFanConv
from custom_components.xiaomi_miot.core.hass_entity import convert_unique_id

MODEL = "cnhdm.airrtc.wkq01"


def model_device(make_device, load_miot_spec):
    return make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        model=MODEL,
        customizes=None,
    )


def test_exact_model_converter_mapping(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    climates = [c for c in device.converters if isinstance(c, MiotClimateConv)]
    fans = [c for c in device.converters if isinstance(c, MiotFanConv)]

    assert len(climates) == 2
    assert len(fans) == 1

    air_conditioner = next(c for c in climates if convert_unique_id(c) == 2)
    floor_heating = device.find_converter("climate.floor_heating")
    fresh_air = device.find_converter("fan.fresh_air")

    def unique_props(parent):
        return {
            device.find_converter(attr).prop.unique_prop
            for attr in parent.attrs
        }

    assert unique_props(air_conditioner) == {
        "prop.2.3", "prop.2.1", "prop.2.5", "prop.2.2", "prop.3.1",
    }
    assert unique_props(floor_heating) == {"prop.2.10", "prop.2.8", "prop.3.1"}
    assert unique_props(fresh_air) == {"prop.2.9", "prop.2.7"}

    assert all(
        device.find_converter(attr).domain is None
        for parent in [*climates, *fans]
        for attr in parent.attrs
    )
    assert device.find_converter("button.info") is not None
    assert len([
        c for c in device.converters
        if c.domain == "sensor" and c.prop.unique_prop == "prop.3.1"
    ]) == 1
    assert len([
        c for c in device.converters
        if c.domain == "switch" and c.prop.unique_prop == "prop.5.1"
    ]) == 1
    assert not any(
        getattr(c, "prop", None) and c.prop.service.iid == 4
        for c in device.converters
    )


def test_parent_entity_metadata_and_identity(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    climates = [c for c in device.converters if isinstance(c, MiotClimateConv)]
    air_converter = next(c for c in climates if convert_unique_id(c) == 2)
    floor_converter = device.find_converter("climate.floor_heating")
    fan_converter = device.find_converter("fan.fresh_air")

    air = ClimateEntity(device, air_converter)
    floor = ClimateEntity(device, floor_converter)
    fresh = FanEntity(device, fan_converter)

    assert [air.unique_id, floor.unique_id, fresh.unique_id] == [
        f"{device.unique_id}-2",
        f"{device.unique_id}-floor_heating",
        f"{device.unique_id}-fresh_air",
    ]
    assert len({air.unique_id, floor.unique_id, fresh.unique_id}) == 3
    assert air._attr_name == "Air Conditioner"
    assert floor._attr_name == "Floor Heating"
    assert fresh._attr_name == "Fresh Air"
    assert air._attr_translation_key is None
    assert floor._attr_translation_key is None
    assert fresh._attr_translation_key is None
    assert "thermostat" in air.entity_id
    assert floor.entity_id.endswith("_floor_heating")
    assert fresh.entity_id.endswith("_fresh_air")
