from homeassistant.helpers.entity import EntityCategory

from custom_components.xiaomi_miot.sensor import SensorEntity
from custom_components.xiaomi_miot.core.miot_local_devices import MIOT_LOCAL_MODELS


MODEL = "xiaomi.airp.mb5"


def test_xiaomi_airp_mb5_supports_local_miot():
    assert MODEL in MIOT_LOCAL_MODELS


def test_xiaomi_airp_mb5_exposes_supported_entities(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    converters = {converter.full_name for converter in device.converters}

    assert {
        "fan.air_purifier.on",
        "switch.air_purifier.anion",
        "switch.air_purifier.uv",
        "switch.screen.on",
        "switch.alarm",
        "switch.physical_controls_locked",
        "select.screen.brightness",
        "select.air_purifier_favorite.fan_level",
        "button.filter.reset_filter_life",
        "sensor.environment.pm1",
    } <= converters
    assert "number.aqi.aqi_updata_heartbeat" not in converters
    assert "sensor.custom_service.favorite_square" not in converters
    assert any(
        converter.domain == "sensor"
        and getattr(converter, "prop", None)
        and converter.prop.name == "motor_rpm_feedback"
        for converter in device.converters
    )


def test_xiaomi_airp_mb5_sensor_categories(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)

    pm1 = SensorEntity(device, device.find_converter("sensor.environment.pm1"))
    motor_rpm = next(
        SensorEntity(device, converter)
        for converter in device.converters
        if converter.domain == "sensor"
        and getattr(converter, "prop", None)
        and converter.prop.name == "motor_rpm_feedback"
    )

    assert pm1.entity_category is None
    assert motor_rpm.entity_category is EntityCategory.DIAGNOSTIC


def test_xiaomi_airp_mb5_omits_factory_and_debug_properties(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    mapping = device.miot_mapping()

    assert "filter_debug.filter_used_time" not in mapping
    assert "filter_tag.tag" not in mapping
    assert "aqi.aqi_updata_heartbeat" not in mapping
    assert "custom_service.country_code" not in mapping
    assert "custom_service.reboot_cause" not in mapping
    assert "custom_service.favorite_square" not in mapping
    motor_rpm = device.spec.get_property("motor_rpm_feedback")
    assert motor_rpm.full_name in mapping
