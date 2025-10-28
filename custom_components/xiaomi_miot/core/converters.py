from typing import TYPE_CHECKING, Any
from dataclasses import dataclass
from homeassistant.util import color, percentage

if TYPE_CHECKING:
    from .device import Device
    from .miot_spec import MiotService, MiotProperty, MiotAction


@dataclass
class BaseConv:
    attr: str
    domain: str = None
    mi: str | int = None
    attrs: list = None
    option: dict = None

    def __post_init__(self):
        if self.attrs is None:
            self.attrs = []
        if self.option is None:
            self.option = {}

    def with_option(self, **kwargs):
        self.option.update(kwargs)
        return self

    @property
    def full_name(self):
        if not self.domain:
            return self.attr
        return f'{self.domain}.{self.attr}'

    def value_from_dict(self, data):
        return data.get(self.full_name, data.get(self.attr))

    # to hass
    def decode(self, device: 'Device', payload: dict, value):
        payload[self.full_name] = value

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
            self.full_name: device.name,
            'model': device.model,
            'did': device.info.did,
            'mac': device.info.mac,
            'lan_ip': device.info.host,
            'app_link': device.app_link,
            'miot_type': device.info.urn,
            'available': device.available,
            'home_room': device.info.home_room,
            'icon': self.option.get('icon') if device.available else 'mdi:information-off',
            'updater': updater or 'none',
        }
        customizes = {**device.customizes}
        customizes.pop('append_converters', None)
        customizes.pop('extend_miot_specs', None)
        payload.update({
            **infos,
            **device.props,
            'converters': [c.full_name for c in device.converters],
            'customizes': customizes,
            **infos,
        })
        if device.available:
            payload.pop('miot_error', None)
        if device.miot_results:
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
    desc: bool = None

    def __post_init__(self):
        super().__post_init__()
        if self.prop:
            if not self.mi:
                from .miot_spec import MiotSpec
                self.mi = MiotSpec.unique_prop(self.prop.siid, piid=self.prop.iid)
            if self.desc == None:
                self.desc = self.prop.use_desc(self.domain)

    def decode(self, device: 'Device', payload: dict, value):
        if self.desc and self.prop:
            value = self.prop.list_description(value)
            if self.domain == 'sensor' and isinstance(value, str):
                value = value.lower()
        super().decode(device, payload, value)

    def encode(self, device: 'Device', payload: dict, value):
        if self.prop:
            if self.desc:
                if isinstance(value, list):
                    value = self.prop.list_first(value)
                else:
                    value = self.prop.list_value(value)
            elif self.prop.is_integer:
                value = int(value) # bool to int
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
        if self.prop and isinstance(value, str):
            if self.prop.value_list or self.prop.value_range:
                value = self.prop.list_value(value)
            elif self.prop.is_integer:
                value = int(value)
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
        if self.attr:
            pass
        elif self.prop:
            self.attr = self.prop.full_name
        elif self.service:
            self.attr = self.service.desc_name

@dataclass
class MiotSensorConv(MiotServiceConv):
    domain: str = 'sensor'

@dataclass
class MiotSwitchConv(MiotServiceConv):
    domain: str = 'switch'

    def __post_init__(self):
        if not self.main_props:
            self.main_props = ['on', 'switch']
        super().__post_init__()

@dataclass
class MiotLightConv(MiotSwitchConv):
    domain: str = 'light'

@dataclass
class MiotBrightnessConv(MiotPropConv):
    def decode(self, device: 'Device', payload: dict, value: int):
        max = self.prop.range_max()
        if max != None:
            super().decode(device, payload, value / max * 255.0)

    def encode(self, device: 'Device', payload: dict, value: float):
        max = self.prop.range_max()
        if max != None:
            value = round(value / 255.0 * max)
            super().encode(device, payload, int(value))

@dataclass
class MiotColorTempConv(MiotPropConv):
    def decode(self, device: 'Device', payload: dict, value: int):
        if self.prop.unit == 'percentage':
            if not value:
                return
            value = self.percentage_to_kelvin(value)
        elif self.prop.unit != 'kelvin':
            if not value:
                return
            value = round(1000000.0 / value)
        super().decode(device, payload, value)

    def encode(self, device: 'Device', payload: dict, value: int):
        if self.prop.unit == 'percentage':
            if not value:
                return
            value = self.kelvin_to_percentage(value)
        elif self.prop.unit != 'kelvin':
            if not value:
                return
            value = round(1000000.0 / value)

        if value < self.prop.range_min():
            value = self.prop.range_min()
        if value > self.prop.range_max():
            value = self.prop.range_max()
        super().encode(device, payload, value)

    @staticmethod
    def percentage_to_kelvin(p: int) -> int:
        return 6500 - p * 40

    @staticmethod
    def kelvin_to_percentage(k: int) -> int:
        return round((6500 - k) / 40)

@dataclass
class MiotRgbColorConv(MiotPropConv):
    def decode(self, device: 'Device', payload: dict, value: int):
        super().decode(device, payload, MiotRgbColorConv.int_to_rgb(value))

    def encode(self, device: 'Device', payload: dict, rgb: tuple[int, int, int]):
        super().encode(device, payload, MiotRgbColorConv.rgb_to_int(rgb))

    @staticmethod
    def rgb_to_int(rgb: tuple[int, int, int]):
        num = int(rgb[0]) << 16 | int(rgb[1]) << 8 | int(rgb[2])
        return int(num)

    @staticmethod
    def int_to_rgb(value: int):
        x = int(value)
        r = (x >> 16) & 0xFF
        g = (x >> 8) & 0xFF
        b = x & 0xFF
        return r, g, b

@dataclass
class MiotHsColorConv(MiotPropConv):
    def decode(self, device: 'Device', payload: dict, value: int):
        rgb = MiotRgbColorConv.int_to_rgb(value)
        super().decode(device, payload, color.color_RGB_to_hs(*rgb))

    def encode(self, device: 'Device', payload: dict, value: tuple):
        rgb = color.color_hs_to_RGB(*value)
        super().encode(device, payload, MiotRgbColorConv.rgb_to_int(rgb))

@dataclass
class MiotFanConv(MiotServiceConv):
    domain: str = 'fan'

    def __post_init__(self):
        if not self.main_props:
            self.main_props = ['on', 'fan_level']
        super().__post_init__()

@dataclass
class MiotClimateConv(MiotServiceConv):
    domain: str = 'climate'

    def __post_init__(self):
        if not self.main_props:
            self.main_props = ['mode', 'target_temperature']
        super().__post_init__()

@dataclass
class MiotCoverConv(MiotServiceConv):
    domain: str = 'cover'

    def __post_init__(self):
        if not self.main_props:
            self.main_props = ['motor_control']
        super().__post_init__()

@dataclass
class MiotCameraConv(MiotServiceConv):
    domain: str = 'camera'

@dataclass
class MiotHumidifierConv(MiotServiceConv):
    domain: str = 'humidifier'

    def __post_init__(self):
        if not self.main_props:
            self.main_props = ['on', 'target_humidity']
        super().__post_init__()

@dataclass
class PercentagePropConv(MiotPropConv):
    ranged = None

    def __post_init__(self):
        super().__post_init__()
        if self.prop and self.prop.value_range:
            self.ranged = (self.prop.range_min(), self.prop.range_max())

    def decode(self, device: 'Device', payload: dict, value: int):
        if self.ranged:
            value = int(percentage.scale_ranged_value_to_int_range(self.ranged, (0, 100), value))
        super().decode(device, payload, value)

    def encode(self, device: 'Device', payload: dict, value: int):
        if self.ranged:
            value = int(percentage.scale_to_ranged_value((0, 100), self.ranged, value))
            if value < self.ranged[0]:
                value = self.ranged[0]
            if value > self.ranged[1]:
                value = self.ranged[1]
        super().encode(device, payload, value)

class MiotTargetPositionConv(PercentagePropConv):
    pass
