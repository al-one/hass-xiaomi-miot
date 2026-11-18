from custom_components.xiaomi_miot.core.miot_spec import MiotSpecInstance


def test_format_desc_name_uses_ascii_description():
    assert MiotSpecInstance.format_desc_name('Sleep', 'sleep') == 'sleep'
    assert MiotSpecInstance.format_desc_name(' PM2.5 ', 'pm2_5') == 'pm2_5'
    assert MiotSpecInstance.format_desc_name('- Temperature', 'temperature') == '_temperature'


def test_format_desc_name_falls_back_to_name():
    assert MiotSpecInstance.format_desc_name('', 'name') == 'name'
    assert MiotSpecInstance.format_desc_name('   ', 'name') == 'name'
    assert MiotSpecInstance.format_desc_name('电视', 'tv') == 'tv'
    assert MiotSpecInstance.format_desc_name('PM2.5 浓度', 'pm2_5') == 'pm2_5'
    assert MiotSpecInstance.format_desc_name('1档风速', 'fan_level') == 'fan_level'
    assert MiotSpecInstance.format_desc_name('テレビ', 'tv') == 'tv'
    assert MiotSpecInstance.format_desc_name('😀', 'emoji') == 'emoji'
    assert MiotSpecInstance.format_desc_name('café', 'cafe') == 'cafe'
