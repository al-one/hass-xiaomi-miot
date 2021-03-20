import logging
import json
import time
import micloud
from micloud.micloudexception import MiCloudException  # noqa: F401

from homeassistant.const import *
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
        return self.request_miot_spec('prop/get', params)

    def set_props(self, params=None):
        return self.request_miot_spec('prop/set', params)

    def do_action(self, params=None):
        return self.request_miot_spec('action', params)

    def request_miot_spec(self, api, params=None):
        url = self._get_api_url(self.default_server) + '/miotspec/' + api
        rsp = self.request(url, {
            'data': json.dumps({
                'params': params or []
            })
        })
        exc = None
        try:
            rdt = json.loads(rsp)
        except TypeError as exc:
            rdt = {}
        except ValueError as exc:
            rdt = {}
        rls = rdt.get('result')
        if not rls:
            _LOGGER.warning(
                'Request miot spec: %s, params: %s to cloud result: %s failed: %s',
                api, params, rsp, exc,
            )
        else:
            _LOGGER.debug(
                'Request miot spec: %s, params: %s to cloud result: %s',
                api, params, rsp,
            )
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

    async def async_get_devices(self, renew=False):
        if not self.user_id:
            return None
        fnm = f'xiaomi_miot/devices-{self.user_id}.json'
        store = Store(self.hass, 1, fnm)
        now = time.time()
        dvs = None
        if not renew:
            dat = await store.async_load() or {}
            if isinstance(dat, dict):
                if dat.get('update_time', 0) > (now - 86400):
                    dvs = dat.get('devices') or []
        if not dvs:
            dvs = await self.hass.async_add_executor_job(self.get_devices)
            if dvs:
                dat = {
                    'update_time': now,
                    'devices': dvs,
                }
                await store.async_save(dat)
                _LOGGER.info('Got %s devices from xiaomi cloud', len(dvs))
        return dvs

    async def async_renew_devices(self):
        return await self.async_get_devices(renew=True)

    async def async_get_devices_by_key(self, key, renew=False, filters=None):
        dat = {}
        if filters is None:
            filters = {}
        fls = ['ssid', 'bssid', 'model']
        dvs = await self.async_get_devices(renew=renew) or []
        for d in dvs:
            if not isinstance(d, dict):
                continue
            if not d.get('mac'):
                d['mac'] = d.get('did')
            k = d.get(key)
            for f in fls:
                ft = filters.get(f'filter_{f}')
                if not ft:
                    continue
                ex = ft != 'include'
                fl = filters.get(f'{f}_list') or {}
                fv = d.get(f)
                if ex:
                    ok = fv not in fl
                else:
                    ok = fv in fl
                if not ok:
                    k = None
            if k:
                dat[k] = d
        return dat

    async def async_login(self):
        return await self.hass.async_add_executor_job(self.login)

    def to_config(self):
        return {
            CONF_USERNAME: self.username,
            CONF_PASSWORD: self.password,
            'server_country': self.default_server,
            'user_id': self.user_id,
            'service_token': self.service_token,
            'ssecurity': self.ssecurity,
        }

    @staticmethod
    async def from_token(hass, config: dict):
        mic = MiotCloud(
            hass,
            config.get(CONF_USERNAME),
            config.get(CONF_PASSWORD),
            config.get('server_country'),
        )
        mic.user_id = config.get('user_id')
        mic.service_token = config.get('service_token')
        mic.ssecurity = config.get('ssecurity')
        ret = await mic.async_login()
        return mic if ret else ret
