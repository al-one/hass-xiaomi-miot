import time
import requests
from functools import partial


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


def analytics_track_event(event, action, label, value=0, node_id=''):
    pms = {
        'id': '1280294351',
        'ei': '|'.join([event, action, label, f'{value}', node_id]),
        'p': 'https://miot-spec.com',
        't': 'Home Assistant',
        'rnd': int(time.time() / 2.67),
    }
    url = 'https://ei.cnzz.com/stat.htm'
    return requests.get(url, params=pms)


async def async_analytics_track_event(hass, *args, **kwargs):
    return await hass.async_add_executor_job(
        partial(analytics_track_event, *args, **kwargs)
    )
