import logging
import voluptuous as vol
from functools import partial

from .miot_spec import (MiotSpec, MiotProperty)
from .templates import CUSTOM_TEMPLATES
from .miio2miot_specs import MIIO_TO_MIOT_SPECS
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)


class Miio2MiotHelper:
    def __init__(self, hass, config: dict, miot_spec: MiotSpec):
        self.hass = hass
        if ext := config.get('extend_model'):
            if m2m := Miio2MiotHelper.from_model(hass, ext, miot_spec):
                sps = m2m.config.get('miio_specs', {})
                sps.update(config.get('miio_specs', {}))
                config = {**m2m.config, **config, 'miio_specs': sps}
        self.config = config
        self.miot_spec = miot_spec
        self.specs = config.get('miio_specs', {})
        self.miio_props = []
        for k, v in self.specs.items():
            if p := v.get('prop'):
                self.miio_props.append(p)
        self.miio_props.extend(config.get('miio_props', []))
        self.miio_props_values = {}

    @staticmethod
    def from_model(hass, model, miot_spec):
        cfg = MIIO_TO_MIOT_SPECS.get(model) or {}
        if isinstance(cfg, str):
            return Miio2MiotHelper.from_model(hass, cfg, miot_spec)
        if cfg:
            the = Miio2MiotHelper(hass, cfg, miot_spec)
            if not the.miio_props:
                the = None
            return the
        return None

    def get_miio_props(self, device):
        dic = {}
        if not self.config.get('without_props'):
            vls = device.get_properties(self.miio_props)
            dic.update(dict(zip(self.miio_props, vls)))
        if cls := self.config.get('miio_commands'):
            for c in cls:
                vls = device.send(c['method'], c.get('params', []))
                if tpl := c.get('template'):
                    tpl = CUSTOM_TEMPLATES.get(tpl, tpl)
                    tpl = cv.template(tpl)
                    tpl.hass = self.hass
                    pdt = tpl.render({'results': vls})
                    if isinstance(pdt, dict):
                        dic.update(pdt)
                elif kls := c.get('values', []):
                    if len(kls) == len(vls):
                        dic.update(dict(zip(kls, vls)))
        self.miio_props_values = dic
        _LOGGER.info('Got miio props for miot: %s', [device.ip, dic])
        return dic

    async def async_get_miot_props(self, *args, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.get_miot_props, *args, **kwargs)
        )

    def get_miot_props(self, device, mapping: dict = None):
        if mapping is None:
            mapping = device.mapping or {}
        rls = []
        if dic := self.get_miio_props(device):
            for k, v in mapping.items():
                u = MiotSpec.unique_prop(v, valid=True)
                c = self.specs.get(u, {})
                p = c.get('prop')
                if not p:
                    continue
                val = dic.get(p)
                prop = self.miot_spec.specs.get(u)
                if prop and isinstance(prop, MiotProperty):
                    mph = MiioPropertyHelper(prop)
                    fmt = c.get('format')
                    try:
                        if fmt and hasattr(mph, fmt):
                            val = getattr(mph, fmt)(val)

                        elif d := c.get('dict', {}):
                            val = d.get(val, c.get('default', val))

                        elif tpl := c.get('template', {}):
                            tpl = CUSTOM_TEMPLATES.get(tpl, tpl)
                            tpl = cv.template(tpl)
                            tpl.hass = self.hass
                            val = tpl.render({'value': val, 'props': dic})

                        elif prop.value_list or prop.value_range:
                            val = int(val)

                        elif prop.format in ['bool']:
                            val = cv.boolean(val)

                        elif prop.format in ['uint8', 'uint16', 'uint32', 'uint64']:
                            val = int(val)

                        elif prop.format in ['float']:
                            val = round(float(val), 4)

                        elif r := c.get('value_ratio'):
                            val = round(float(val) * float(r), 3)

                    except (TypeError, ValueError, vol.Invalid):
                        val = dic.get(p)
                rls.append({
                    **v,
                    'code': 0,
                    'value': val,
                })
        return rls


class MiioPropertyHelper:
    def __init__(self, prop: MiotProperty, reverse=False):
        self.property = prop
        self.reverse = reverse

    def onoff(self, value):
        if self.reverse:
            return 'on' if value else 'off'
        return value is True or 'on' == f'{value}'.lower()
