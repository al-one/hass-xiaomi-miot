from homeassistant.helpers.entity import EntityCategory

from custom_components.xiaomi_miot.sensor import SensorEntity
from custom_components.xiaomi_miot.core.miot_local_devices import MIOT_LOCAL_MODELS


MODEL = "zhimi.airp.rmb1"


def find_prop_converter(device, domain, prop_name):
    return next(
        (
            converter
            for converter in device.converters
            if converter.domain == domain
            and getattr(converter, "prop", None)
            and converter.prop.name == prop_name
        ),
        None,
    )


def test_zhimi_airp_rmb1_supports_local_miot():
    assert MODEL in MIOT_LOCAL_MODELS


def test_zhimi_airp_rmb1_exposes_supported_entities(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    converters = {converter.full_name for converter in device.converters}

    assert {
        "fan.air_purifier.on",
        "switch.alarm",
        "select.screen.brightness",
        "button.filter.reset_filter_life",
    } <= converters
    for domain, prop_name in [
        ("sensor", "relative_humidity"),
        ("sensor", "pm2_5_density"),
        ("sensor", "temperature"),
        ("sensor", "filter_life_level"),
        ("sensor", "filter_left_time"),
        ("sensor", "filter_used_time"),
        ("sensor", "fault"),
        ("sensor", "moto_speed_rpm"),
        ("select", "temperature_display_unit"),
        ("number", "favorite_level"),
        ("number", "aqi_updata_heartbeat"),
    ]:
        assert find_prop_converter(device, domain, prop_name), f"{domain}.{prop_name}"


def test_zhimi_airp_rmb1_sensor_categories(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)

    pm25 = SensorEntity(device, find_prop_converter(device, "sensor", "pm2_5_density"))
    fault = SensorEntity(device, find_prop_converter(device, "sensor", "fault"))
    motor_rpm = SensorEntity(device, find_prop_converter(device, "sensor", "moto_speed_rpm"))

    assert pm25.entity_category is None
    assert fault.entity_category is EntityCategory.DIAGNOSTIC
    assert motor_rpm.entity_category is EntityCategory.DIAGNOSTIC
