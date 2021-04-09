import logging
import requests
import re

from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)


class MiotSpec:
    def __init__(self, dat: dict):
        self.raw = dat
        self.type = str(dat.get('type') or '')
        self.name = self.name_by_type(self.type)
        self.description = dat.get('description') or ''
        self.services = []
        self.services_count = {}
        for s in (dat.get('services') or []):
            srv = MiotService(s, self)
            if not srv.name:
                continue
            self.services.append(srv)

    def services_mapping(self, *args, **kwargs):
        dat = None
        for s in self.get_services(*args, **kwargs):
            if dat is None:
                dat = {}
            nxt = s.mapping() or {}
            dat = {**nxt, **dat}
        return dat

    def get_services(self, *args, **kwargs):
        excludes = kwargs.get('excludes', [])
        excludes.append('device_information')
        return [
            s
            for s in self.services
            if (s.name in args or not args) and s.name not in excludes
        ]

    def get_service(self, *args):
        for s in self.services:
            if s.name in args:
                return s
        return None

    @staticmethod
    def name_by_type(typ):
        arr = f'{typ}:::'.split(':')
        nam = arr[3] or ''
        nam = re.sub(r'\W+', '_', nam)
        return nam

    @staticmethod
    async def async_from_model(hass, model, use_remote=False):
        typ = await MiotSpec.async_get_model_type(hass, model, use_remote)
        return await MiotSpec.async_from_type(hass, typ)

    @staticmethod
    async def async_get_model_type(hass, model, use_remote=False):
        if not model:
            return None
        url = 'https://miot-spec.org/miot-spec-v2/instances?status=released'
        fnm = 'xiaomi_miot/instances.json'
        store = Store(hass, 1, fnm)
        if not use_remote:
            dat = await store.async_load() or {}
        else:
            try:
                res = await hass.async_add_executor_job(requests.get, url)
                dat = res.json() or {}
                await store.async_save(dat)
            except ValueError:
                dat = {}
        typ = None
        for v in (dat.get('instances') or []):
            if model == v.get('model'):
                typ = v.get('type')
                break
        if typ is None and not use_remote:
            return await MiotSpec.async_get_model_type(hass, model, True)
        return typ

    @staticmethod
    async def async_from_type(hass, typ):
        url = f'https://miot-spec.org/miot-spec-v2/instance?type={typ}'
        fnm = f'xiaomi_miot/{typ}.json'
        store = Store(hass, 1, fnm)
        dat = await store.async_load() or {}
        if not dat.get('type'):
            try:
                res = await hass.async_add_executor_job(requests.get, url)
                dat = res.json() or {}
                await store.async_save(dat)
            except ValueError:
                dat = {}
        return MiotSpec(dat)


class MiotService:
    def __init__(self, dat: dict, spec: MiotSpec):
        self.spec = spec
        self.raw = dat
        self.iid = int(dat.get('iid') or 0)
        self.type = str(dat.get('type') or '')
        self.name = MiotSpec.name_by_type(self.type)
        self.unique_name = f'{self.name}-{self.iid}'
        self.description = dat.get('description') or self.name
        spec.services_count.setdefault(self.name, 0)
        spec.services_count[self.name] += 1
        self.properties = {}
        for p in (dat.get('properties') or []):
            prop = MiotProperty(p, self)
            if not prop.name:
                continue
            self.properties[prop.iid] = prop
        self.actions = {}
        for a in (dat.get('actions') or []):
            act = MiotAction(a, self)
            if not act.name:
                continue
            self.actions[act.iid] = act

    @property
    def name_count(self):
        return self.spec.services_count.get(self.name) or 0

    def mapping(self):
        dat = {}
        for p in self.properties.values():
            if not isinstance(p, MiotProperty):
                continue
            if not p.full_name:
                continue
            if not p.readable and not p.writeable:
                continue
            dat[p.full_name] = {
                'siid': self.iid,
                'piid': p.iid,
            }
        return dat

    def get_properties(self, *args):
        return [
            p
            for p in self.properties.values()
            if p.name in args
        ]

    def get_property(self, *args, only_format=None):
        if only_format:
            only_format = only_format if isinstance(only_format, list) else [only_format]
        for p in self.properties.values():
            if p.name in args:
                if only_format and p.format not in only_format:
                    continue
                return p
        return None

    def bool_property(self, *args):
        return self.get_property(*args, only_format='bool')

    def get_actions(self, *args):
        return [
            a
            for a in self.actions.values()
            if a.name in args
        ]

    def get_action(self, *args):
        for a in self.actions.values():
            if a.name in args:
                return a
        return None


class MiotProperty:
    def __init__(self, dat: dict, service: MiotService):
        self.service = service
        self.raw = dat
        self.iid = int(dat.get('iid') or 0)
        self.type = str(dat.get('type') or '')
        self.name = MiotSpec.name_by_type(self.type)
        self.full_name = ''
        if self.name and service.name:
            if self.name == service.name:
                self.full_name = self.name
            else:
                self.full_name = f'{service.name}.{self.name}'
                if len(self.full_name) >= 32:
                    # miot did length must less than 32
                    self.full_name = self.name
            if service.name_count > 1:
                self.full_name = f'{service.name}-{service.iid}.{self.name}'
        self.unique_name = f'{service.unique_name}.{self.name}-{self.iid}'
        self.description = dat.get('description') or self.name
        self.format = dat.get('format') or ''
        self.access = dat.get('access') or []
        self.unit = dat.get('unit') or ''
        self.value_list = dat.get('value-list') or []
        self.value_range = dat.get('value-range') or []

    @property
    def readable(self):
        return 'read' in self.access

    @property
    def writeable(self):
        return 'write' in self.access

    def from_dict(self, dat: dict, default=None):
        return dat.get(self.full_name, default)

    def description_to_dict(self, dat: dict):
        if not self.value_list:
            return None
        val = self.from_dict(dat)
        if val is None:
            return val
        des = self.list_description(val)
        if des:
            dat[f'{self.full_name}_desc'] = des
        return des

    def list_value(self, des):
        rls = []
        for v in self.value_list:
            val = v.get('value')
            if des is None:
                rls.append(val)
            elif des == v.get('description'):
                return val
        return rls if des is None else None

    def list_description(self, val):
        rls = []
        for v in self.value_list:
            des = v.get('description')
            if val is None:
                if des == '':
                    des = v.get('value')
                rls.append(des)
            elif val == v.get('value'):
                return des
        if self.value_range:
            if val is None:
                # range to list
                return self.list_description(None)
            else:
                return val
        return rls if val is None else None

    def list_descriptions(self, max_length=200):
        if self.value_range:
            lst = []
            cur = self.range_min()
            rmx = self.range_max()
            stp = self.range_step()
            cnt = 0
            while cur <= rmx:
                cnt += 1
                if cnt > max_length:
                    lst.append(rmx)
                    break
                lst.append(f'{cur}')
                cur += stp
            return lst
        return self.list_description(None)

    def list_search(self, *args, **kwargs):
        rls = []
        get_first = kwargs.get('get_first')
        for v in self.value_list:
            des = str(v.get('description') or '')
            dls = [
                des,
                des.lower(),
                re.sub(r'\W+', '_', des),
            ]
            for d in dls:
                if d in args:
                    if get_first:
                        return v.get('value')
                    rls.append(v.get('value'))
        return rls if not get_first else None

    def list_first(self, *args):
        return self.list_search(*args, get_first=True)

    def range_min(self):
        if self.value_range:
            return self.value_range[0]
        return None

    def range_max(self):
        if len(self.value_range) > 1:
            return self.value_range[1]
        return None

    def range_step(self):
        if len(self.value_range) > 2:
            return self.value_range[2]
        return None


class MiotAction:
    def __init__(self, dat: dict, service: MiotService):
        self.service = service
        self.raw = dat
        self.iid = int(dat.get('iid') or 0)
        self.type = str(dat.get('type') or '')
        self.name = MiotSpec.name_by_type(self.type)
        self.full_name = f'{service.name}.{self.name}'
        self.description = dat.get('description') or self.name
        self.ins = dat.get('in') or []
        self.out = dat.get('out') or []

    def in_params_from_attrs(self, dat: dict):
        pms = []
        for pid in self.ins:
            prop = self.service.properties.get(pid)
            pms.append({
                'piid': pid,
                'value': dat.get(prop.full_name) if prop else None,
            })
        return pms

    def in_params(self, params: list):
        pms = []
        for pid in self.ins:
            pms.append({
                'piid': pid,
                'value': params.pop(0),
            })
        return pms

    def out_results(self, out=None):
        kls = []
        for pid in self.out:
            prop = self.service.properties.get(pid)
            if prop:
                kls.append(prop.full_name)
        if out is None:
            out = []
        if len(kls) == len(out):
            return dict(zip(kls, out))
        return None
