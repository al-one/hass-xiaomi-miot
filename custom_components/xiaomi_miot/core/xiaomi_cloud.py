import logging
import json
import micloud
from micloud.micloudexception import MiCloudException  # noqa: F401

from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)


class MiotCloud(micloud.MiCloud):
    def __init__(self, hass, username, password, country=None):
        super().__init__(username, password)
        self.hass = hass
        self.default_server = country or 'cn'

    def get_properties_for_mapping(self, did, mapping: dict):
        pms = []
        rmp = {}
        for k, v in mapping.items():
            if not isinstance(v, dict):
                continue
            s = v.get('siid')
            p = v.get('piid')
            pms.append({'did': str(did), 'siid': s, 'piid': p})
            rmp.setdefault(s, {})
            rmp[f'{s}{p}'] = k
        rls = self.get_props(pms)
        if not rls:
            return None
        dls = []
        for v in rls:
            s = v.get('siid')
            p = v.get('piid')
            k = rmp.get(f'{s}{p}')
            if not k:
                continue
            v['did'] = k
            dls.append(v)
        return dls

    def get_props(self, params=None):
        url = self._get_api_url(self.default_server) + '/miotspec/prop/get'
        rsp = self.request(url, {
            'data': json.dumps({
                'datasource': 1,
                'params': params or []
            })
        })
        try:
            rdt = json.loads(rsp)
            exc = None
        except ValueError as exc:
            rdt = {}
        rls = rdt.get('result')
        if not rls:
            _LOGGER.debug('Get miot props: %s from cloud failed: %s %s', params, rsp, exc)
        return rls

    def set_props(self, params=None):
        url = self._get_api_url(self.default_server) + '/miotspec/prop/set'
        rsp = self.request(url, {
            'data': json.dumps({
                'params': params or []
            })
        })
        try:
            rdt = json.loads(rsp)
            exc = None
        except ValueError as exc:
            rdt = {}
        rls = rdt.get('result')
        if not rls:
            _LOGGER.debug('Set miot props: %s to cloud failed: %s %s', params, rsp, exc)
        return rls

    async def async_get_device(self, mac=None, host=None):
        dvs = await self.async_get_devices() or []
        for d in dvs:
            if not isinstance(d, dict):
                continue
            if mac and mac == d.get('mac'):
                return d
            if host and host == d.get('localip'):
                return d
        return None

    async def async_get_devices(self):
        if not self.user_id:
            return None
        fnm = f'xiaomi_miot/devices-{self.user_id}.json'
        store = Store(self.hass, 1, fnm)
        dat = await store.async_load() or {}
        if not dat:
            dat = await self.hass.async_add_executor_job(self.get_devices)
            if dat:
                await store.async_save(dat)
        return dat

    async def async_get_devices_by_key(self, key):
        dat = {}
        dvs = await self.async_get_devices() or []
        for d in dvs:
            if not isinstance(d, dict):
                continue
            k = d.get(key)
            if k:
                dat[k] = d
        return dat
