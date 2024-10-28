from typing import TYPE_CHECKING, Any
from dataclasses import dataclass

if TYPE_CHECKING:
    from .device import Device
    from .miot_spec import MiotService, MiotProperty, MiotAction


@dataclass
class BaseConv:
    attr: str
    domain: str = None
    mi: str | int = None
    attrs: set = None
    option: dict = None

    def __post_init__(self):
        if self.attrs is None:
            self.attrs = set()
        if self.option is None:
            self.option = {}

    def with_option(self, **kwargs):
        self.option.update(kwargs)
        return self

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
class InfoConv(BaseConv):
    attr: str = 'info'
    domain: str = 'button'

    def decode(self, device: 'Device', payload: dict, value):
        updater = device.data.get('updater')
        infos = {
            self.attr: device.name,
            'model': device.model,
            'did': device.info.did,
            'mac': device.info.mac,
            'lan_ip': device.info.host,
            'app_link': device.app_link,
            'available': device.available,
            'icon': self.option.get('icon') if device.available else 'mdi:information-off',
            'updater': updater or 'none',
            'updated_at': str(device.data.get('updated', '')),
        }
        payload.update({
            **infos,
            **device.props,
            'converters': [c.attr for c in device.converters],
            'customizes': device.customizes,
            **infos,
        })
        if device.miot_results:
            payload.pop('miot_error', None)
            if err := device.miot_results.errors:
                payload['miot_error'] = str(err)

    def encode(self, device: 'Device', payload: dict, value):
        payload.update({
            'method': 'update_status',
        })

@dataclass
class AttrConv(BaseConv):
    pass

@dataclass
class MiotPropConv(BaseConv):
    prop: 'MiotProperty' = None
    desc: bool = False

    def __post_init__(self):
        super().__post_init__()
        if not self.mi and self.prop:
            from .miot_spec import MiotSpec
            self.mi = MiotSpec.unique_prop(self.prop.siid, piid=self.prop.iid)

    def decode(self, device: 'Device', payload: dict, value):
        if self.desc and self.prop:
            value = self.prop.list_description(value)
            if self.domain == 'sensor' and isinstance(value, str):
                value = value.lower()
        super().decode(device, payload, value)

    def encode(self, device: 'Device', payload: dict, value):
        if self.desc and self.prop:
            value = self.prop.list_value(value)
        super().encode(device, payload, value)

@dataclass
class MiotPropValueConv(MiotPropConv):
    value: Any = None
    description: str = None

    def decode(self, device: 'Device', payload: dict, value):
        pass

@dataclass
class MiotActionConv(BaseConv):
    action: 'MiotAction' = None
    prop: 'MiotProperty' = None

    def __post_init__(self):
        super().__post_init__()
        if not self.mi:
            from .miot_spec import MiotSpec
            self.mi = MiotSpec.unique_prop(self.action.siid, aiid=self.action.iid)
        if not self.prop:
            self.prop = self.action.in_properties()[0] if self.action.ins else None

    def decode(self, device: 'Device', payload: dict, value):
        super().decode(device, payload, value)

    def encode(self, device: 'Device', payload: dict, value):
        if self.prop and self.prop.value_list and isinstance(value, str):
            value = self.prop.list_value(value)
        ins = value if isinstance(value, list) else [] if value is None else [value]
        _, s, p = self.mi.split('.')
        payload['method'] = 'action'
        payload['param'] = {
            'did': device.did,
            'siid': int(s),
            'aiid': int(p),
            'in':   ins,
        }

@dataclass
class MiotServiceConv(MiotPropConv):
    attr: str = None
    service: 'MiotService' = None
    prop: 'MiotProperty' = None
    main_props: list = None

    def __post_init__(self):
        if not self.prop and self.service and self.main_props:
            self.prop = self.service.get_property(*self.main_props)
        super().__post_init__()
        if not self.attr and self.prop:
            self.attr = self.prop.full_name

@dataclass
class MiotSensorConv(MiotServiceConv):
    domain: str = 'sensor'

@dataclass
class MiotSwitchConv(MiotServiceConv):
    domain: str = 'switch'

    def __post_init__(self):
        if not self.main_props:
            self.main_props = ['on']
        super().__post_init__()
