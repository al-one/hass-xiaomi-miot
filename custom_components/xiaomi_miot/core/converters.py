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

    def __post_init__(self):
        self.option = {}

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
    prop: 'MiotProperty' = None
    desc: bool = False

    def __post_init__(self):
        super().__post_init__()
        if not self.mi:
            self.mi = MiotSpec.unique_prop(self.prop.siid, piid=self.prop.iid)

    def decode(self, device: 'Device', payload: dict, value):
        if self.desc:
            payload['property_value'] = value
            value = self.prop.list_description(value)
        super().decode(device, payload, value)

    # from hass
    def encode(self, device: 'Device', payload: dict, value):
        if self.desc:
            value = self.prop.list_value(value)
        super().encode(device, payload, value)
