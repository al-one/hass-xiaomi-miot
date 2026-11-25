"""zhimi.humidifier.ca6: model customizes keep the inherited wildcard values."""

from types import SimpleNamespace

from custom_components.xiaomi_miot.core.utils import get_customize_via_model
from custom_components.xiaomi_miot.humidifier import MODE_OFF, HumidifierEntity

MODEL = "zhimi.humidifier.ca6"


def _props(device, domain):
    return {c.prop.name for c in device.converters if c.domain == domain and getattr(c, "prop", None)}


def test_ca6_customize_keeps_inherited_values():
    cfg = get_customize_via_model(MODEL)

    assert cfg["chunk_coordinators"] == [
        {"interval": 20, "props": "humidifier.on,mode,target_humidity,fan_level"},
        {"interval": 25, "props": "relative_humidity,temperature"},
        {"interval": 300, "props": "filter_life_level,filter_left_time,filter_used_time"},
        {"interval": 30, "props": "self_clean_percent", "cloud": True},
    ]
    assert cfg["switch_properties"].split(",") == [
        "alarm", "other.clean", "humidifier.dry", "humidifier.automatic_air_drying",
    ]
    # inherited and not overridden
    assert cfg["interval_seconds"] == 120
    assert cfg["select_properties"] == "screen.brightness"
    assert cfg["number_properties"] == "speed_level"
    assert cfg["without_mode_off"] is True


def test_ca6_entities(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)

    assert {"alarm", "clean", "automatic_air_drying"} <= _props(device, "switch")
    assert {"water_level", "actual_speed", "self_clean_percent"} <= _props(device, "sensor")
    assert "brightness" in _props(device, "select")


def test_ca6_modes_without_off(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    conv = next(c for c in device.converters if c.domain == "humidifier")
    entity = HumidifierEntity(device, conv)

    assert MODE_OFF not in entity._attr_available_modes
    assert entity._attr_available_modes  # Fav / Auto / Sleep

    entity.set_state({entity._conv_power.attr: False})
    assert entity._attr_is_on is False
    assert entity._attr_mode != MODE_OFF


async def test_ca6_cloud_chunk_is_not_main(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL)
    config = {"username": "test-user", "conn_mode": "auto"}
    device.entry.get_config = lambda key=None, default=None: config.get(key, default)
    device.cloud = SimpleNamespace()

    names = [c.name.rsplit("-", 1)[-1] for c in await device.init_miot_coordinators()]

    assert names == ["chunk_1", "chunk_2", "chunk_3", "chunk_4_cloud", "miot_status"]
    assert [c.name.rsplit("-", 1)[-1] for c in device.main_coordinators] == ["chunk_1"]
