from typing import TYPE_CHECKING
from dataclasses import dataclass
from .miot_spec import MiotSpec

if TYPE_CHECKING:
    from .device import Device
    from .miot_spec import MiotProperty


@dataclass
class BaseConv:
    attr: str
    domain: str = None
    mi: str | int = None
    option: dict = None

    # to hass
    def decode(self, device: 'Device', payload: dict, value):
        payload[self.attr] = value

    # from hass
    def encode(self, device: 'Device', payload: dict, value):
        params = None
        if self.mi and 'prop.' in self.mi:
            _, s, p = self.mi.split('.')
            payload['method'] = 'set_properties'
            params = {'siid': int(s), 'piid': int(p)}
        if params:
            params.update({'did': device.did, 'value': value})
            payload.setdefault('params', []).append(params)

@dataclass
class MiotPropConv(BaseConv):
    attr: 'MiotProperty'

    def __post_init__(self):
        if not self.mi:
            self.mi = MiotSpec.unique_prop(self.attr.siid, piid=self.attr.iid)

    def decode(self, device: 'Device', payload: dict, value):
        payload[self.attr.full_name] = value
