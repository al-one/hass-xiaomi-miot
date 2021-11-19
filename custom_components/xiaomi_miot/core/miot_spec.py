import logging
import requests
import platform
import time
import re

from homeassistant.const import *
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    TRANSLATION_LANGUAGES,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    ENTITY_CATEGORY_CONFIG,
    ENTITY_CATEGORY_DIAGNOSTIC,
)

_LOGGER = logging.getLogger(__name__)

# https://iot.mi.com/new/doc/guidelines-for-access/other-platform-access/control-api#MIOT%E7%8A%B6%E6%80%81%E7%A0%81
SPEC_ERRORS = {
    '000': 'Unknown',
    '001': 'Device does not exist',
    '002': 'Service does not exist',
    '003': 'Property does not exist',
    '004': 'Event does not exist',
    '005': 'Action does not exist',
    '006': 'Device description not found',
    '007': 'Device cloud not found',
    '008': 'Invalid IID (PID, SID, AID, etc.)',
    '009': 'Scene does not exist',
    '011': 'Device offline',
    '013': 'Property is not readable',
    '023': 'Property is not writable',
    '033': 'Property cannot be subscribed',
    '043': 'Property value error',
    '034': 'Action return value error',
    '015': 'Action execution error',
    '025': 'The number of action parameters does not match',
    '035': 'Action parameter error',
    '036': 'Device operation timeout',
    '100': 'The device cannot be operated in its current state',
    '101': 'IR device does not support this operation',
    '901': 'Token does not exist or expires',
    '902': 'Token is invalid',
    '903': 'Authorization expired',
    '904': 'Unauthorized voice device',
    '905': 'Device not bound',
    '999': 'Feature not online',
    '-4001': 'Property is not readable',
    '-4002': 'Property is not writable',
    '-4003': 'Property/Action/Event does not exist',
    '-4004': 'Other internal errors',
    '-4005': 'Property value error',
    '-4006': 'Action in parameters error',
    '-4007': 'did error',
}


class MiotSpecInstance:
    def __init__(self, dat: dict):
        self.raw = dat
        self.iid = int(dat.get('iid') or 0)
        self.type = str(dat.get('type') or '')
        self.name = self.name_by_type(self.type)
        self.description = dat.get('description') or ''

    @staticmethod
    def format_name(nam):
        nam = f'{nam}'.strip()
        nam = re.sub(r'\W+', '_', nam).lower()
        return nam

    @staticmethod
    def format_desc_name(des, nam):
        return MiotSpecInstance.format_name(nam if re.match(r'[^x00-xff]', des) else des)

    @staticmethod
    def name_by_type(typ):
        arr = f'{typ}:::'.split(':')
        nam = arr[3] or ''
        return MiotSpecInstance.format_name(nam)

    @property
    def translation_keys(self):
        return ['_globals']

    @property
    def translations(self):
        dic = TRANSLATION_LANGUAGES
        kls = self.translation_keys
        for k in kls:
            d = dic.get(k)
            if not isinstance(d, dict):
                continue
            dic = {**dic, **d}
        return dic

    def get_translation(self, des):
        dls = [
            des.lower(),
            des,
        ]
        tls = self.translations
        for d in dls:
            if d not in tls:
                continue
            ret = tls[d]
            if isinstance(ret, dict):
                if d not in ret:
                    continue
                ret = ret[d]
            return ret
        return des

    @staticmethod
    def spec_error(errno):
        err = f'{errno}'
        cod = err
        if err[:3] == '-70':
            cod = err[-3:]
        if cod in SPEC_ERRORS:
            err += f' {SPEC_ERRORS.get(cod)}'
        return err


# https://iot.mi.com/new/doc/design/spec/xiaoai
class MiotSpec(MiotSpecInstance):
    def __init__(self, dat: dict):
        super().__init__(dat)
        self.services = {}
        self.services_count = {}
        self.services_properties = {}
        self.custom_mapping = None
        self.custom_mapping_names = {}
        for s in (dat.get('services') or []):
            srv = MiotService(s, self)
            if not srv.name:
                continue
            self.services[srv.iid] = srv

    def services_mapping(self, *args, **kwargs):
        dat = None
        sls = self.get_services(*args, **kwargs)
        if self.custom_mapping:
            sis = list(map(lambda x: x.iid, sls))
            dat = {
                k: v
                for k, v in self.custom_mapping.items()
                if v.get('siid') in sis
            }
            return dat
        for s in sls:
            if dat is None:
                dat = {}
            nxt = s.mapping() or {}
            dat = {**nxt, **dat}
        return dat

    def set_custom_mapping(self, mapping: dict):
        self.custom_mapping = mapping
        self.custom_mapping_names = {}
        for k, v in mapping.items():
            u = self.unique_prop(v, valid=True)
            if not u:
                continue
            self.custom_mapping_names[u] = k
        for s in self.services.values():
            for p in s.properties.values():
                u = self.unique_prop(s.iid, p.iid)
                n = self.custom_mapping_names.get(u)
                if not n:
                    continue
                p.full_name = n

    def get_services(self, *args, **kwargs):
        excludes = kwargs.get('excludes', [])
        excludes.append('device_information')
        return [
            s
            for s in self.services.values()
            if s.name not in excludes and (not args or s.name in args or s.desc_name in args)
        ]

    def get_service(self, *args):
        for a in args:
            for s in self.services.values():
                if a not in [s.name, s.desc_name]:
                    continue
                return s
        return None

    def first_service(self):
        for s in self.services.values():
            return s
        return None

    def generate_entity_id(self, entity, suffix=None):
        mod = f'{self.type}::::'.split(':')[5]
        if not mod:
            return None
        mac = re.sub(r'[\W_]+', '', entity.unique_mac)
        eid = f'{mod}_{mac[-4:]}'
        if suffix:
            eid = f'{eid}_{suffix}'
        eid = re.sub(r'\W+', '_', eid).lower()
        return f'{DOMAIN}.{eid}'

    @staticmethod
    async def async_from_model(hass, model, use_remote=False):
        typ = await MiotSpec.async_get_model_type(hass, model, use_remote)
        return await MiotSpec.async_from_type(hass, typ)

    @staticmethod
    async def async_get_model_type(hass, model, use_remote=False):
        if not model:
            return None
        url = 'https://miot-spec.org/miot-spec-v2/instances?status=all'
        fnm = f'{DOMAIN}/instances.json'
        store = Store(hass, 1, fnm)
        now = int(time.time())
        dat = {}
        if not use_remote:
            dat = await store.async_load() or {}
            ptm = dat.pop('_updated_time', 0)
            if dat and now - ptm > 86400 * 7:
                dat = {}
        if not dat:
            try:
                res = await hass.async_add_executor_job(requests.get, url)
                dat = res.json() or {}
            except ValueError:
                dat = {}
            if dat:
                sdt = {
                    '_updated_time': now,
                }
                for v in (dat.get('instances') or []):
                    m = v.get('model')
                    o = sdt.get(m) or {}
                    if o:
                        if o.get('status') == 'released' and v.get('status') != o.get('status'):
                            continue
                        if v.get('version') < o.get('version'):
                            continue
                    v.pop('model', None)
                    sdt[m] = v
                await store.async_save(sdt)
                dat = sdt
                _LOGGER.info(
                    'Renew miot spec instances: %s, count: %s, model: %s',
                    fnm, len(sdt) - 1, model,
                )
        typ = None
        if 'instances' in dat:
            for v in (dat.get('instances') or []):
                if model == v.get('model'):
                    typ = v.get('type')
                    break
        elif model in dat:
            typ = dat[model].get('type')
        return typ

    @staticmethod
    async def async_from_type(hass, typ):
        url = f'https://miot-spec.org/miot-spec-v2/instance?type={typ}'
        fnm = f'{DOMAIN}/{typ}.json'
        if platform.system() == 'Windows':
            fnm = fnm.replace(':', '_')
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

    @staticmethod
    def unique_prop(siid, piid=None, aiid=None, eiid=None, valid=False):
        if isinstance(siid, dict):
            piid = piid or siid.get('piid')
            aiid = aiid or siid.get('aiid')
            eiid = eiid or siid.get('eiid')
            siid = siid.get('siid')
        typ = 'prop'
        iid = piid
        if aiid:
            typ = 'action'
            iid = aiid
        if eiid:
            typ = 'event'
            iid = eiid
        if valid and not iid:
            return None
        return f'{typ}.{siid}.{iid}'


# https://miot-spec.org/miot-spec-v2/spec/services
class MiotService(MiotSpecInstance):
    def __init__(self, dat: dict, spec: MiotSpec):
        self.spec = spec
        super().__init__(dat)
        self.unique_name = f'{self.name}-{self.iid}'
        self.desc_name = self.format_desc_name(self.description, self.name)
        self.friendly_desc = self.get_translation(self.description)
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
            if p.name in args or p.desc_name in args
        ]

    def get_property(self, *args, only_format=None):
        if only_format:
            only_format = only_format if isinstance(only_format, list) else [only_format]
        for a in args:
            for p in self.properties.values():
                if a not in [p.name, p.desc_name]:
                    continue
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

    def unique_prop(self, **kwargs):
        return self.spec.unique_prop(self.iid, **kwargs)

    def generate_entity_id(self, entity):
        return self.spec.generate_entity_id(entity, self.description)

    @property
    def translation_keys(self):
        return ['_globals', self.name]

    @property
    def entity_icon(self):
        icon = None
        name = self.name
        if name in ['washer']:
            icon = 'mdi:washing-machine'
        elif name in ['fish_tank']:
            icon = 'mdi:fishbowl'
        elif name in ['pet_drinking_fountain']:
            icon = 'mdi:fountain'
        return icon


# https://miot-spec.org/miot-spec-v2/spec/properties
class MiotProperty(MiotSpecInstance):
    def __init__(self, dat: dict, service: MiotService):
        self.service = service
        self.siid = service.iid
        super().__init__(dat)
        self.unique_name = f'{service.unique_name}.{self.name}-{self.iid}'
        self.unique_prop = self.service.unique_prop(piid=self.iid)
        self.desc_name = self.format_desc_name(self.description, self.name)
        self.friendly_desc = self.short_desc
        self.format = dat.get('format') or ''
        self.access = dat.get('access') or []
        self.unit = dat.get('unit') or ''
        self.value_list = dat.get('value-list') or []
        self.value_range = dat.get('value-range') or []
        self.full_name = ''
        if self.name and service.name:
            if self.name == service.name:
                self.full_name = self.name
            else:
                self.full_name = f'{service.name}.{self.name}'
            if service.name_count > 1:
                self.full_name = f'{service.unique_name}.{self.name}'
            if self.full_name in service.spec.services_properties:
                self.full_name = f'{service.unique_name}.{self.desc_name}'
            if self.full_name in service.spec.services_properties:
                self.full_name = self.unique_name
            if not (self.readable or self.writeable):
                self.full_name = self.name
            elif len(self.full_name) >= 32:
                # miot did length must less than 32
                self.full_name = f'{self.desc_name}-{self.siid}-{self.iid}'
            service.spec.services_properties[self.full_name] = {
                'siid': self.siid,
                'piid': self.iid,
            }

    @property
    def short_desc(self):
        sde = self.service.description.strip()
        pde = self.description.strip()
        des = pde
        if sde != pde:
            des = f'{sde} {pde}'.strip()
        ret = self.get_translation(des)
        if ret != des:
            return ret
        ret = self.get_translation(pde)
        if ret != pde:
            return f'{sde} {ret}'.strip()
        arr = des.split(' ')
        return ' '.join(dict(zip(arr, arr)).keys())

    @property
    def readable(self):
        return 'read' in self.access

    @property
    def writeable(self):
        return 'write' in self.access

    def generate_entity_id(self, entity):
        eid = self.service.spec.generate_entity_id(entity, self.description)
        eid = re.sub(r'_(\d(?:_|$))', r'\1', eid)  # issue#153
        return eid

    @property
    def translation_keys(self):
        return [
            '_globals',
            self.service.name,
            self.name,
            f'{self.service.name}.{self.name}',
        ]

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
        if des is not None and self.value_range:
            try:
                val = int(des)
            except (TypeError, ValueError):
                val = None
            return val
        rls = []
        for v in self.value_list:
            val = v.get('value')
            vde = v.get('description')
            if des is None:
                rls.append(val)
            elif des == vde or des == self.get_translation(vde):
                return val
        return rls if des is None else None

    def list_description(self, val):
        rls = []
        for v in self.value_list:
            des = self.get_translation(v.get('description'))
            if val is None:
                if des == '':
                    des = v.get('value')
                rls.append(des)
            elif val == v.get('value'):
                return des
        if self.value_range:
            if val is None:
                # range to list
                return self.list_descriptions()
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
                    lst.append(f'{rmx}')
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
                self.format_name(des),
                self.get_translation(des),
            ]
            for d in dls:
                if d not in args:
                    continue
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

    @property
    def unit_of_measurement(self):
        name = self.name
        unit = self.unit
        aliases = {
            'celsius': TEMP_CELSIUS,
            'fahrenheit': TEMP_FAHRENHEIT,
            'kelvin': TEMP_KELVIN,
            'percentage': PERCENTAGE,
            'lux': LIGHT_LUX,
            'μg/m3': CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
            'mg/m3': CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER,
            'p/m3': CONCENTRATION_PARTS_PER_CUBIC_METER,
        }
        names = {
            'power_consumption': ENERGY_WATT_HOUR,
            'pm2_5_density': CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
            'tds_in': CONCENTRATION_PARTS_PER_MILLION,
            'tds_out': CONCENTRATION_PARTS_PER_MILLION,
        }
        if name in names:
            unit = names[name]
        elif not unit or unit in ['none', 'null']:
            unit = None
        elif unit in aliases:
            unit = aliases[unit]
        return unit

    @property
    def state_class(self):
        names = {
            'tds_in': STATE_CLASS_MEASUREMENT,
            'tds_out': STATE_CLASS_MEASUREMENT,
            'filter_used_flow': STATE_CLASS_TOTAL_INCREASING,
        }
        if self.name in names:
            return names[self.name]
        return None

    @property
    def device_class(self):
        ret = None
        name = self.full_name
        props = {
            'atmospheric_pressure': DEVICE_CLASS_PRESSURE,
            'temperature': DEVICE_CLASS_TEMPERATURE,
            'relative_humidity': DEVICE_CLASS_HUMIDITY,
            'humidity': DEVICE_CLASS_HUMIDITY,
            'battery_level': DEVICE_CLASS_BATTERY,
            'battery': DEVICE_CLASS_BATTERY,
            'illumination': DEVICE_CLASS_ILLUMINANCE,
            'voltage': DEVICE_CLASS_VOLTAGE,
            'electric_current': DEVICE_CLASS_CURRENT,
            'electric_power': DEVICE_CLASS_POWER,
        }
        vls = vars()
        if 'DEVICE_CLASS_CO2' in vls:
            # v2021.4
            props.update({
                'co2_density': 'carbon_dioxide',
                'co_density': 'carbon_monoxide',
                'co2': 'carbon_dioxide',
            })
        if 'DEVICE_CLASS_PM25' in vls:
            # v2021.9
            props.update({
                'pm2_5_density': 'pm25',
                'pm25': 'pm25',
                'pm10': 'pm10',
            })
        if self.name in props:
            ret = props[self.name]
        else:
            for k, v in props.items():
                if k not in name:
                    continue
                ret = v
                break
        return ret

    @property
    def entity_icon(self):
        icon = None
        name = self.name
        icons = {
            'on': 'mdi:power',
            'mode': 'mdi:menu',
            'washing_strength': 'mdi:waves',
            'nozzle_position': 'mdi:spray',
            'spin_speed': 'mdi:speedometer',
            'target_temperature': 'mdi:coolant-temperature',
            'target_water_level': 'mdi:water-plus',
            'drying_level': 'mdi:tumble-dryer',
            'co2_density': 'mdi:molecule-co2',
            'smoke_concentration': 'mdi:smoking',
            'tds_in': 'mdi:water',
            'tds_out': 'mdi:water-check',
            'filter_used_time': 'mdi:clock',
            'filter_used_flow': 'mdi:water-percent',
        }
        if name in ['heat_level']:
            icon = 'mdi:radiator'
            if self.service.name in ['seat']:
                icon = 'mdi:car-seat-heater'
        elif name in icons:
            icon = icons[name]
        elif self.service.name in ['oven', 'microwave_oven']:
            icon = 'mdi:microwave'
        elif self.service.name in ['health_pot']:
            return 'mdi:coffee'
        return icon

    @property
    def entity_category(self):
        cate = None
        name = self.name
        names = {
            'battery_level': ENTITY_CATEGORY_DIAGNOSTIC,
            'fan_init_power_opt': ENTITY_CATEGORY_CONFIG,
            'init_power_opt': ENTITY_CATEGORY_CONFIG,
            'off_delay_time': ENTITY_CATEGORY_CONFIG,
        }
        if name in names:
            cate = names[name]
        return cate


# https://miot-spec.org/miot-spec-v2/spec/actions
class MiotAction(MiotSpecInstance):
    def __init__(self, dat: dict, service: MiotService):
        self.service = service
        self.siid = service.iid
        super().__init__(dat)
        self.unique_prop = self.service.unique_prop(aiid=self.iid)
        self.full_name = f'{service.name}.{self.name}'
        self.ins = dat.get('in') or []
        self.out = dat.get('out') or []

    def in_params_from_attrs(self, dat: dict, with_piid=True):
        pms = []
        for pid in self.ins:
            prop = self.service.properties.get(pid)
            val = dat.get(prop.full_name) if prop else None
            pms.append({
                'piid': pid,
                'value': val,
            } if with_piid else val)
        return pms

    def in_params(self, params: list):
        pms = []
        for pid in self.ins:
            try:
                val = params.pop(0)
            except IndexError:
                break
            if not (isinstance(val, dict) and 'piid' in val):
                val = {
                    'piid': pid,
                    'value': val,
                }
            pms.append(val)
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


class MiotResults:
    def __init__(self, results, mapping=None):
        self._results = results
        self.mapping = mapping or {}
        self.results = []
        for v in results or []:
            if not isinstance(v, dict):
                continue
            r = MiotResult(v)
            self.results.append(r)

    @property
    def is_empty(self):
        return len(self.results) < 1

    @property
    def is_valid(self):
        return not self.is_empty if self._results else isinstance(self._results, list)

    @property
    def first(self):
        if self.is_empty:
            return None
        return self.results[0]

    def to_attributes(self, attrs=None):
        rmp = {}
        for k, v in self.mapping.items():
            s = v.get('siid')
            p = v.get('piid')
            rmp[f'prop.{s}.{p}'] = k
        if attrs is None:
            attrs = {}
        adt = {}
        for prop in self.results:
            s = prop.siid
            p = prop.piid
            k = rmp.get(f'prop.{s}.{p}', prop.did)
            if k is None:
                continue
            e = prop.code
            ek = f'{k}.error'
            if e == 0:
                adt[k] = prop.value
                if ek in attrs:
                    attrs.pop(ek, None)
            else:
                adt[ek] = prop.spec_error
        return adt

    def __str__(self):
        return f'{self._results}'


class MiotResult:
    def __init__(self, result: dict):
        self.result = result
        self.code = result.get('code')
        self.value = result.get('value')
        self.did = result.get('did')
        self.siid = result.get('siid')
        self.piid = result.get('piid')

    def get(self, key, default=None):
        return self.result.get(key, default)

    @property
    def is_success(self):
        return self.code == 0

    @property
    def spec_error(self):
        return MiotSpec.spec_error(self.code)

    def __str__(self):
        return f'{self.result}'
