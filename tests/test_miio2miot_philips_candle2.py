"""miio -> miot mapping for philips.light.candle2 (PR #3043)."""
import json
from pathlib import Path

from custom_components.xiaomi_miot.core.converters import MiotColorTempConv
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.miio2miot import Miio2MiotHelper

MODEL = 'philips.light.candle2'

MAPPING = {
    'prop.2.1': {'siid': 2, 'piid': 1},
    'prop.2.2': {'siid': 2, 'piid': 2},
    'prop.2.3': {'siid': 2, 'piid': 3},
    'prop.2.4': {'siid': 2, 'piid': 4},
    'prop.2.5': {'siid': 2, 'piid': 5},
}

# the mapping as proposed in PR #3043, without the colour-temp template
NAIVE_CONFIG = {
    'model': MODEL,
    'miio_specs': {
        'prop.2.1': {'prop': 'power', 'setter': True, 'format': 'onoff'},
        'prop.2.2': {'prop': 'bright', 'setter': True},
        'prop.2.3': {'prop': 'cct', 'setter': True},
    },
}

EXTEND_FILE = Path(__file__).parent.parent / 'custom_components/xiaomi_miot/core/miot_specs_extend.json'
EXTEND_SPECS = json.loads(EXTEND_FILE.read_text(encoding='utf-8'))[MODEL]


class FakeMiioDevice:
    """Only the two device methods used by Miio2MiotHelper."""

    def __init__(self, power='on', bright=50, cct=1, dv=0, snm=0):
        self.values = {'power': power, 'bright': bright, 'cct': cct, 'dv': dv, 'snm': snm}
        self.sent = []

    async def async_get_prop(self, props, max_properties=None):
        return [self.values[p] for p in props]

    async def async_send(self, method, params):
        self.sent.append([method, params])
        return ['ok']


def load_extended(load_miot_spec):
    spec = load_miot_spec(f'{MODEL}.json')
    spec.extend_specs(services=EXTEND_SPECS)
    return spec


async def read_miot(helper, **kwargs):
    dev = FakeMiioDevice(**kwargs)
    props = await helper.async_get_miot_props(dev, MAPPING)
    return {f"prop.{p['siid']}.{p['piid']}": p['value'] for p in props}


def color_temp_kelvin(spec, value):
    conv = MiotColorTempConv(
        attr='color_temp_kelvin',
        domain='light',
        prop=spec.specs['prop.2.3'],
    )
    payload = {}
    conv.decode(None, payload, value)
    return round(payload[conv.full_name])


def test_spec_is_registered(hass, load_miot_spec):
    spec = load_miot_spec(f'{MODEL}.json')
    helper = Miio2MiotHelper.from_model(hass, MODEL, spec)

    assert helper is not None
    assert helper.miio_props == ['power', 'bright', 'cct', 'dv', 'snm']
    assert spec.specs['prop.2.3'].unit == 'percentage'
    assert spec.specs['prop.2.3'].value_range == [1, 100, 1]


def test_customizes_expose_entities():
    cfg = DEVICE_CUSTOMIZES[MODEL]
    assert cfg['select_properties'] == 'scene'
    assert cfg['number_properties'] == 'delay_off'


def test_customize_entities_are_created(make_device, load_miot_spec):
    device = make_device(load_extended(load_miot_spec), model=MODEL)

    delay = device.find_converter('number.light.delay_off')
    scene = device.find_converter('select.light.scene')
    assert delay is not None and delay.domain == 'number'
    assert scene is not None and scene.domain == 'select'


async def test_keeps_power_and_brightness(hass, load_miot_spec):
    spec = load_miot_spec(f'{MODEL}.json')
    helper = Miio2MiotHelper.from_model(hass, MODEL, spec)

    props = await read_miot(helper, power='on', bright=42, cct=1)
    assert props['prop.2.1'] is True
    assert props['prop.2.2'] == 42

    dev = FakeMiioDevice()
    await helper.async_set_property(dev, 2, 1, False)
    await helper.async_set_property(dev, 2, 2, 42)
    assert dev.sent == [['set_power', ['off']], ['set_bright', [42]]]


async def test_cct_direction(hass, load_miot_spec):
    """miio cct=1 is the warmest end, miot percentage=100 is the warmest end."""
    spec = load_miot_spec(f'{MODEL}.json')
    helper = Miio2MiotHelper.from_model(hass, MODEL, spec)

    assert (await read_miot(helper, cct=1))['prop.2.3'] == 100
    assert (await read_miot(helper, cct=100))['prop.2.3'] == 1

    assert color_temp_kelvin(spec, 100) == 2500  # 100% == warm
    assert color_temp_kelvin(spec, 1) == 6460  # 1% == cold

    dev = FakeMiioDevice()
    await helper.async_set_property(dev, 2, 3, 100)  # warmest kelvin
    await helper.async_set_property(dev, 2, 3, 1)  # coldest kelvin
    assert dev.sent == [['set_cct', [1]], ['set_cct', [100]]]


async def test_naive_mapping_reverses_color_temperature(hass, load_miot_spec):
    """PR #3043 without the template turns a warm bulb into the coldest kelvin."""
    spec = load_miot_spec(f'{MODEL}.json')
    helper = Miio2MiotHelper(hass, NAIVE_CONFIG, spec)

    # the bulb reports its warmest setting (cct=1), miot says "1%"
    props = await read_miot(helper, cct=1)
    assert props['prop.2.3'] == 1
    # ... which the light platform decodes as the coldest kelvin
    assert color_temp_kelvin(spec, props['prop.2.3']) == 6460

    # and setting the warmest kelvin sends the coldest miio value
    dev = FakeMiioDevice()
    await helper.async_set_property(dev, 2, 3, 100)
    assert dev.sent == [['set_cct', [100]]]


async def test_delay_off_number(hass, load_miot_spec):
    spec = load_extended(load_miot_spec)
    prop = spec.get_properties('delay_off')[0]

    assert (prop.range_min(), prop.range_max(), prop.range_step()) == (0, 360, 1)
    assert prop.unit_of_measurement == 'minutes'

    helper = Miio2MiotHelper.from_model(hass, MODEL, spec)
    assert (await read_miot(helper, dv=3600))['prop.2.4'] == 60
    assert (await read_miot(helper, dv=0))['prop.2.4'] == 0

    dev = FakeMiioDevice()
    await helper.async_set_property(dev, 2, 4, 45)
    await helper.async_set_property(dev, 2, 4, 0)
    assert dev.sent == [['delay_off', [2700]], ['delay_off', [0]]]


async def test_scene_select(hass, load_miot_spec):
    spec = load_extended(load_miot_spec)
    prop = spec.get_properties('scene')[0]

    assert prop.list_descriptions() == ['Bright', 'TV', 'Warm', 'Night']
    assert prop.list_value('Warm') == 3

    helper = Miio2MiotHelper.from_model(hass, MODEL, spec)
    assert (await read_miot(helper, snm=3))['prop.2.5'] == 3

    dev = FakeMiioDevice()
    await helper.async_set_property(dev, 2, 5, 2)
    assert dev.sent == [['apply_fixed_scene', [2]]]
