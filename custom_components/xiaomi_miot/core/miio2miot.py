import time
import logging
import voluptuous as vol
from typing import Tuple
from functools import partial

from .utils import is_offline_exception
from .miot_spec import (MiotSpec, MiotProperty, MiotAction)
from .templates import CUSTOM_TEMPLATES
from .miio2miot_specs import MIIO_TO_MIOT_SPECS
import homeassistant.helpers.config_validation as cv

from miio import DeviceException
from miio.utils import (
    rgb_to_int,
    int_to_rgb,
)

_LOGGER = logging.getLogger(__name__)


class Miio2MiotHelper:
    def __init__(self, hass, config: dict, miot_spec: MiotSpec, from_model=None):
        self.hass = hass
        if ext := config.get('extend_model'):
            if m2m := Miio2MiotHelper.from_model(hass, ext, miot_spec):
                sps = {**m2m.config.get('miio_specs', {})}
                sps.update(config.get('miio_specs', {}))
                config = {**m2m.config, **config, 'miio_specs': sps}
        self.config = config
        self.miot_spec = miot_spec
        self.specs = config.get('miio_specs', {})
        self.model = from_model or config.get('model', None)
        self.miio_props = []
        for k, v in self.specs.items():
            if p := v.get('prop'):
                self.miio_props.append(p)
        self.extend_miio_props(config.get('miio_props', []))
        self.miio_props_values = {}

    @staticmethod
    def from_model(hass, model, miot_spec, from_model=None):
        if not from_model:
            from_model = model
        cfg = MIIO_TO_MIOT_SPECS.get(model) or {}
        if isinstance(cfg, str):
            return Miio2MiotHelper.from_model(hass, cfg, miot_spec, from_model)
        if cfg:
            cfg.setdefault('model', model)
            return Miio2MiotHelper(hass, cfg, miot_spec, from_model)
        return None

    def extend_miio_props(self, props: list):
        self.miio_props.extend(props)
        self.miio_props = list(dict(zip(self.miio_props, self.miio_props)).keys())
        return self.miio_props

    def get_miio_props(self, device):
        dic = {}
        if not self.config.get('without_props'):
            try:
                num = int(self.config.get('chunk_properties'))
            except (TypeError, ValueError):
                num = None
            try:
                vls = device.get_properties(self.miio_props, max_properties=num)
                dic.update(dict(zip(self.miio_props, vls)))
            except (DeviceException, OSError) as exc:
                if is_offline_exception(exc):
                    raise exc
                _LOGGER.error('%s: Got MiioException: %s while get_properties(%s)', self.model, exc, self.miio_props)
        if cls := self.config.get('miio_commands'):
            for c in cls:
                if dly := c.get('delay', 0):
                    time.sleep(dly)
                pms = c.get('params', [])
                try:
                    vls = device.send(c['method'], pms)
                except (DeviceException, OSError) as exc:
                    if is_offline_exception(exc):
                        raise exc
                    _LOGGER.error('%s: Got MiioException: %s while %s(%s)', self.model, exc, c['method'], pms)
                    continue
                kls = c.get('values', [])
                if kls is True:
                    kls = c.get('params', [])
                if tpl := c.get('template'):
                    tpl = CUSTOM_TEMPLATES.get(tpl, tpl)
                    tpl = cv.template(tpl)
                    tpl.hass = self.hass
                    pdt = tpl.render({'results': vls})
                    if isinstance(pdt, dict):
                        dic.update(pdt)
                elif kls:
                    if isinstance(vls, dict):
                        vls = list(vls.values())
                    i = 0
                    for k in kls:
                        if i >= len(vls):
                            break
                        dic[k] = vls[i]
                        i += 1
        if tpl := self.config.get('miio_template'):
            tpl = CUSTOM_TEMPLATES.get(tpl, tpl)
            tpl = cv.template(tpl)
            tpl.hass = self.hass
            pdt = tpl.render({'props': dic})
            if isinstance(pdt, dict):
                dic.update(pdt)
        self.miio_props_values = dic
        _LOGGER.info('%s: Got miio props for miot: %s', self.model, dic)
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
                        if tpl := c.get('template', {}):
                            tpl = CUSTOM_TEMPLATES.get(tpl, tpl)
                            tpl = cv.template(tpl)
                            tpl.hass = self.hass
                            val = tpl.render({
                                'value': val,
                                'props': dic,
                                'dict': c.get('dict', {}),
                                'min': prop.range_min(),
                                'max': prop.range_max(),
                                'step': prop.range_step(),
                                'description': prop.list_description(val) if prop.value_list else None,
                            })

                        elif fmt and hasattr(mph, fmt):
                            val = getattr(mph, fmt)(val)

                        elif d := c.get('dict', {}):
                            val = d.get(val, c.get('default', val))

                        elif prop.format in ['bool']:
                            val = cv.boolean(val)

                        elif r := c.get('value_ratio'):
                            val = round(float(val) * float(r), 3)

                        elif prop.format in ['float']:
                            val = round(float(val), 4)

                        elif prop.is_integer:
                            val = int(val)

                    except (TypeError, ValueError, vol.Invalid):
                        val = dic.get(p)
                rls.append({
                    **v,
                    'code': 0,
                    'value': val,
                })
        return rls

    def has_setter(self, siid, piid=None, aiid=None):
        key = MiotSpec.unique_prop(siid=siid, piid=piid, aiid=aiid)
        ret = self.specs.get(key, {}).get('setter')
        return ret

    def set_property(self, device, siid, piid, value):
        key = MiotSpec.unique_prop(siid=siid, piid=piid)
        cfg = self.specs.get(key, {})
        setter = cfg.get('setter')
        if setter is True:
            setter = None
            if prop := cfg.get('prop'):
                setter = f'set_{prop}'
        pms = [value]
        prop = self.miot_spec.specs.get(key)
        if prop and isinstance(prop, MiotProperty):
            mph = MiioPropertyHelper(prop, reverse=True)
            fmt = cfg.get('format')
            if tpl := cfg.get('set_template'):
                tpl = CUSTOM_TEMPLATES.get(tpl, tpl)
                tpl = cv.template(tpl)
                tpl.hass = self.hass
                pms = tpl.render({
                    'value': value,
                    'props': self.miio_props_values,
                    'dict': cfg.get('dict', {}),
                    'min': prop.range_min(),
                    'max': prop.range_max(),
                    'step': prop.range_step(),
                    'description': prop.list_description(value) if prop.value_list else None,
                }) or []
                if isinstance(pms, dict) and 'method' in pms:
                    setter = pms.get('method', setter)
                    pms = pms.get('params', [])
            elif fmt and hasattr(mph, fmt):
                pms = [getattr(mph, fmt)(value)]
            elif d := cfg.get('dict', {}):
                for dk, dv in d.items():
                    if dv == value:
                        pms = [dk]
                        break
        pms = cv.ensure_list(pms)
        if not setter:
            _LOGGER.warning('%s: Set miio prop via miot failed: %s', self.model, [key, setter, cfg])
            return None
        _LOGGER.info('%s: Set miio prop via miot: %s', self.model, [key, setter, pms])
        ret = device.send(setter, pms) or ['']
        iok = ret == ['ok']
        if self.config.get('ignore_result'):
            iok = ret or isinstance(ret, list)
        cbk = cfg.get('set_callback')
        if iok and cbk:
            cbk(prop=cfg.get('prop'), config=cfg, setter=setter, params=pms, props=self.miio_props_values)
        return {
            'code': 0 if iok else 1,
            'siid': siid,
            'piid': piid,
            'result': ret,
        }

    def call_action(self, device, siid, aiid, params):
        key = MiotSpec.unique_prop(siid=siid, aiid=aiid)
        cfg = self.specs.get(key, {})
        setter = cfg.get('setter')
        pms = cv.ensure_list(params)
        act = self.miot_spec.specs.get(key)
        if act and isinstance(act, MiotAction):
            if tpl := cfg.get('set_template'):
                tpl = CUSTOM_TEMPLATES.get(tpl, tpl)
                tpl = cv.template(tpl)
                tpl.hass = self.hass
                pms = tpl.render({
                    'params': pms,
                    'props': self.miio_props_values,
                }) or []
                if isinstance(pms, dict) and 'method' in pms:
                    setter = pms.get('method', setter)
                    pms = pms.get('params', [])
            pms = cv.ensure_list(pms)
        if not setter:
            _LOGGER.warning('%s: Call miio method via miot action failed: %s', self.model, [key, setter, cfg])
            return None
        _LOGGER.info('%s: Call miio method via miot action: %s', self.model, [key, setter, pms])
        ret = device.send(setter, pms) or ['']
        iok = ret == ['ok']
        if self.config.get('ignore_result'):
            iok = ret or isinstance(ret, list)
        return {
            'code': 0 if iok else 1,
            'siid': siid,
            'aiid': aiid,
            'result': ret,
        }

    def entity_attrs(self):
        adt = {}
        eas = self.config.get('entity_attrs', [])
        if isinstance(eas, list):
            eas = {
                k: k
                for k in eas
            }
        for k, p in eas.items():
            v = self.miio_props_values.get(p)
            if v is not None:
                adt[k] = v
        return adt

    def only_miio_props(self, props: list):
        rls = []
        for p in props:
            rls.append(self.miio_props_values.get(p))
        return rls


class MiioPropertyHelper:
    def __init__(self, prop: MiotProperty, reverse=False):
        self.property = prop
        self.reverse = reverse

    def onoff(self, value):
        if self.reverse:
            return 'on' if value else 'off'
        return value is True or 'on' == f'{value}'.lower()

    def rgb(self, value):
        is_tuple = isinstance(value, Tuple)
        if self.reverse:
            if not is_tuple:
                value = int_to_rgb(value)
            value = list(value)
        elif is_tuple:
            return rgb_to_int(value)
        return value
