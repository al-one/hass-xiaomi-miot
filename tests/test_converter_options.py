from custom_components.xiaomi_miot.core.device import InfoConverter


def test_make_device_adds_info_converter(make_device, load_miot_spec):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))

    assert device.converters[0] is InfoConverter
    assert device.find_converter("button.info") is InfoConverter
