from custom_components.xiaomi_miot.device_tracker import MiotTrackerEntity


def test_tracker_does_not_override_deprecated_properties():
    assert "battery_level" not in MiotTrackerEntity.__dict__
    assert "location_name" not in MiotTrackerEntity.__dict__
    assert "_attr_location_name" not in MiotTrackerEntity.__dict__
