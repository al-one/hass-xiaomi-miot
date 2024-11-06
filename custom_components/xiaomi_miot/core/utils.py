import os
import re
import json
import locale
import tzlocal
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.util import language as language_util
from homeassistant.util.dt import DEFAULT_TIME_ZONE, get_time_zone
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, DEVICE_CUSTOMIZES, DATA_CUSTOMIZE
from .translation_languages import TRANSLATION_LANGUAGES


def get_value(obj, key, def_value=None, sep='.'):
    keys = f'{key}'.split(sep)
    result = obj
    for k in keys:
        if result is None:
            return None
        if isinstance(result, dict):
            result = result.get(k, def_value)
        elif isinstance(result, (list, tuple)):
            try:
                result = result[int(k)]
            except Exception:
                result = def_value
    return result

def get_customize_via_model(model, key=None, default=None):
    cfg = {}
    for m in wildcard_models(model):
        cus = DEVICE_CUSTOMIZES.get(m) or {}
        if key is not None and key not in cus:
            continue
        if cus:
            cfg = {**cus, **cfg}
    return cfg if key is None else cfg.get(key, default)

def get_customize_via_entity(entity, key=None, default=None):
    if key is None:
        default = {}
    if not isinstance(entity, Entity):
        return default
    cfg = {}
    if entity.hass and entity.entity_id:
        cfg = {
            **(entity.hass.data[DATA_CUSTOMIZE].get(entity.entity_id) or {}),
            **(entity.hass.data[DOMAIN].get(DATA_CUSTOMIZE, {}).get(entity.entity_id) or {}),
        }
        if key is not None and key in cfg:
            return cfg.get(key)
    mls = []
    if model := getattr(entity, 'model', None):
        if hasattr(entity, 'customize_keys'):
            mls.extend(entity.customize_keys)
        mls.append(model)
    for mod in mls:
        cus = get_customize_via_model(mod)
        cfg = {**cus, **cfg}
    return cfg if key is None else cfg.get(key, default)

class CustomConfigHelper:
    def custom_config(self, key=None, default=None):
        raise NotImplementedError

    def custom_config_bool(self, key=None, default=None):
        val = self.custom_config(key, default)
        try:
            val = cv.boolean(val)
        except vol.Invalid:
            val = default
        return val

    def custom_config_number(self, key=None, default=None):
        num = default
        val = self.custom_config(key)
        if val is not None:
            try:
                num = float(f'{val}')
            except (TypeError, ValueError):
                num = default
        return num

    def custom_config_integer(self, key=None, default=None):
        num = self.custom_config_number(key, default)
        if num is not None:
            num = int(num)
        return num

    def custom_config_list(self, key=None, default=None):
        lst = self.custom_config(key)
        if lst is None:
            return default
        if not isinstance(lst, list):
            lst = f'{lst}'.split(',')
            lst = list(map(lambda x: x.strip(), lst))
        return lst

    def custom_config_json(self, key=None, default=None):
        dic = self.custom_config(key)
        if dic:
            if not isinstance(dic, (dict, list)):
                try:
                    dic = json.loads(dic or '{}')
                except (TypeError, ValueError):
                    dic = None
            if isinstance(dic, (dict, list)):
                return dic
        return default


def get_manifest(field=None, default=None):
    manifest = {}
    with open(f'{os.path.dirname(__file__)}/../manifest.json') as fil:
        manifest = json.load(fil) or {}
    return manifest.get(field, default) if field else manifest

async def async_get_manifest(hass: HomeAssistant, field=None, default=None):
    return await hass.async_add_executor_job(get_manifest, field, default)

def local_zone(hass=None):
    try:
        if isinstance(hass, HomeAssistant):
            return get_time_zone(hass.config.time_zone)
        return tzlocal.get_localzone()
    except KeyError:
        pass
    return DEFAULT_TIME_ZONE


def in_china(hass=None):
    if isinstance(hass, HomeAssistant):
        if hass.config.time_zone in ['Asia/Shanghai', 'Asia/Hong_Kong']:
            return True
    try:
        return f'{locale.getdefaultlocale()[0]}'[:3] == 'zh_'
    except (KeyError, Exception):
        pass
    return False


def wildcard_models(model):
    if not model:
        return []
    if ':' in model:
        return [model]
    wil = re.sub(r'\.[^.]+$', '.*', model)
    return [
        model,
        wil,
        re.sub(r'^[^.]+\.', '*.', wil),
        '*',
    ]


def get_translation(key, keys=None):
    dic = get_translations(*(keys or []))
    val = dic.get(key, key)
    if isinstance(val, str):
        return val
    return key


def get_translations(*keys):
    dic = {
        **TRANSLATION_LANGUAGES,
        **(TRANSLATION_LANGUAGES.get('_globals', {})),
    }
    for k in keys:
        tls = TRANSLATION_LANGUAGES.get(k)
        if not isinstance(tls, dict):
            continue
        dic.update(tls)
    return dic

def get_translation_langs(hass: HomeAssistant, langs=None):
    lang = hass.config.language
    if not langs:
        return [lang]
    if 'en' not in langs:
        langs.append('en')
    return language_util.matches(lang, langs)


def is_offline_exception(exc):
    err = f'{exc}'
    ret = 'Unable to discover the device' in err
    if not ret:
        ret = 'No response from the device' in err
    if not ret:
        ret = 'OSError: [Errno 64] Host is down' in err
    if not ret:
        ret = 'OSError: [Errno 65] No route to host' in err
    return ret


def update_attrs_with_suffix(attrs, new_dict):
    updated_attrs = {}
    for key, value in new_dict.items():
        if key in attrs:
            suffix = 2
            while f"{key}_{suffix}" in attrs:
                suffix += 1
            updated_key = f"{key}_{suffix}"
        else:
            updated_key = key

        updated_attrs[updated_key] = value
    attrs.update(updated_attrs)


async def async_analytics_track_event(hass: HomeAssistant, event, action, label, value=0, **kwargs):
    pms = {
        'model': label,
        'event': event,
        'action': action,
        'label': label,
        'value': value,
        'locale': locale.getdefaultlocale()[0],
        'tz': hass.config.time_zone,
        'ver': await async_get_manifest(hass, 'version', ''),
        **kwargs,
    }
    url = 'https://hacc.miot-spec.com/api/track'
    try:
        session = async_get_clientsession(hass)
        return await session.post(url, data=pms, timeout=3)
    except (Exception, ValueError):
        return False


class RC4:
    _idx = 0
    _jdx = 0
    _ksa: list

    def __init__(self, pwd):
        self.init_key(pwd)

    def init_key(self, pwd):
        cnt = len(pwd)
        ksa = list(range(256))
        j = 0
        for i in range(256):
            j = (j + ksa[i] + pwd[i % cnt]) & 255
            ksa[i], ksa[j] = ksa[j], ksa[i]
        self._ksa = ksa
        self._idx = 0
        self._jdx = 0
        return self

    def crypt(self, data):
        if isinstance(data, str):
            data = data.encode()
        ksa = self._ksa
        i = self._idx
        j = self._jdx
        out = []
        for byt in data:
            i = (i + 1) & 255
            j = (j + ksa[i]) & 255
            ksa[i], ksa[j] = ksa[j], ksa[i]
            out.append(byt ^ ksa[(ksa[i] + ksa[j]) & 255])
        self._idx = i
        self._jdx = j
        self._ksa = ksa
        return bytearray(out)

    def init1024(self):
        self.crypt(bytes(1024))
        return self
