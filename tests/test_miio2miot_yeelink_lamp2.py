"""miio -> miot off delay for yeelink.light.lamp2 (miio delayoff / cron_add / cron_del)."""
import json
from pathlib import Path

from custom_components.xiaomi_miot.core.miio2miot import Miio2MiotHelper
from custom_components.xiaomi_miot.core.utils import get_customize_via_model

MODEL = 'yeelink.light.lamp2'
EXTEND_FILE = Path(__file__).parent.parent / 'custom_components/xiaomi_miot/core/miot_specs_extend.json'
EXTEND_SPECS = json.loads(EXTEND_FILE.read_text(encoding='utf-8'))[MODEL]


class FakeMiioDevice:
    def __init__(self, **values):
        self.values = values
        self.sent = []

    async def async_get_prop(self, props, max_properties=None):
        return [self.values.get(p, 0) for p in props]

    async def async_send(self, method, params):
        self.sent.append([method, params])
        return ['ok']


def load_extended(load_miot_spec):
    spec = load_miot_spec(f'{MODEL}.json')
    spec.extend_specs(services=EXTEND_SPECS)
    return spec


def test_off_delay_comes_from_the_light_wildcard():
    # no model block: `*.light.*` already lists off_delay_time
    cfg = get_customize_via_model(MODEL)
    assert 'off_delay_time' in cfg['number_properties'].split(',')


def test_off_delay_number_is_created(make_device, load_miot_spec):
    device = make_device(load_extended(load_miot_spec), model=MODEL)
    conv = device.find_converter('number.light.off_delay_time')
    assert conv is not None
    assert conv.prop.value_range == [0, 60, 1]


async def test_off_delay_reads_delayoff(hass, load_miot_spec):
    spec = load_extended(load_miot_spec)
    helper = Miio2MiotHelper.from_model(hass, MODEL, spec)
    assert 'delayoff' in helper.miio_props

    props = await helper.async_get_miot_props(
        FakeMiioDevice(power='on', delayoff=25), {'prop.2.102': {'siid': 2, 'piid': 102}},
    )
    assert props[0]['value'] == 25


async def test_off_delay_starts_and_cancels_the_timer(hass, load_miot_spec):
    spec = load_extended(load_miot_spec)
    helper = Miio2MiotHelper.from_model(hass, MODEL, spec)

    dev = FakeMiioDevice()
    await helper.async_set_property(dev, 2, 102, 15)
    await helper.async_set_property(dev, 2, 102, 0)
    assert dev.sent == [['cron_add', [0, 15]], ['cron_del', [0, 0]]]
