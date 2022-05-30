import re
import locale
import tzlocal
from datetime import timezone
from homeassistant.core import HomeAssistant
from homeassistant.util.dt import get_time_zone
from homeassistant.helpers.aiohttp_client import async_get_clientsession


def local_zone(hass=None):
    try:
        if isinstance(hass, HomeAssistant):
            return get_time_zone(hass.config.time_zone)
        return tzlocal.get_localzone()
    except KeyError:
        pass
    return timezone.utc


def in_china(hass=None):
    try:
        return f'{locale.getdefaultlocale()[0]}'[:3] == 'zh_'
    except (KeyError, Exception):
        if isinstance(hass, HomeAssistant):
            return hass.config.time_zone == 'Asia/Shanghai'
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
    ]


def is_offline_exception(exc):
    err = f'{exc}'
    ret = 'Unable to discover the device' in err
    if not ret:
        ret = 'OSError: [Errno 64] Host is down' in err
    if not ret:
        ret = 'OSError: [Errno 65] No route to host' in err
    return ret


async def async_analytics_track_event(hass, event, action, label, value=0, **kwargs):
    pms = {
        'model': label,
        'event': event,
        'action': action,
        'label': label,
        'value': value,
        'locale': locale.getdefaultlocale()[0],
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
