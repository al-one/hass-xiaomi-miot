import logging
import json
import time
import micloud
from datetime import datetime
from functools import partial
from micloud.micloudexception import MiCloudException  # noqa: F401

from homeassistant.const import *
from homeassistant.helpers.storage import Store
from homeassistant.components import persistent_notification

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
        rdt = self.request_miot_api('miotspec/' + api, {
            'params': params or [],
        }) or {}
        return rdt.get('result')

    def get_user_device_data(self, did, key, typ='prop', raw=False, **kwargs):
        now = int(time.time())
        params = {
            "uid": self.user_id,
            "did": did,
            "key": key,
            "type": typ,
            "time_start": now - 86400 * 7,
            "time_end": now + 60,
            "limit": 5,
            **kwargs,
        }
        rdt = self.request_miot_api('user/get_user_device_data', params) or {}
        return rdt if raw else rdt.get('result')

    def get_last_device_data(self, did, key, typ='prop', **kwargs):
        kwargs['raw'] = False
        kwargs['limit'] = 1
        rls = self.get_user_device_data(did, key, typ, **kwargs) or [None]
        rdt = rls.pop(0) or {}
        if kwargs.get('not_value'):
            return rdt
        val = rdt.get('value')
        if val is None:
            return None
        try:
            vls = json.loads(val)
        except (TypeError, ValueError):
            vls = [val]
        return vls.pop(0)

    async def async_check_auth(self, notify=False):
        rdt = await self.hass.async_add_executor_job(
            partial(self.get_user_device_data, '1', 'check_auth', raw=True)
        ) or {}
        nid = f'xiaomi-miot-auth-warning-{self.user_id}'
        eno = rdt.get('code', 0)
        if eno != 3:
            return True
        # auth err
        self.user_id = None
        self.service_token = None
        self.ssecurity = None
        if await self.async_login():
            await self.async_stored_auth(self.user_id, save=True)
            persistent_notification.dismiss(self.hass, nid)
            return True
        if notify:
            persistent_notification.create(
                self.hass,
                f'Xiaomi cloud: {self.user_id} auth failed, '
                'Please update option for this integration to refresh token.\n'
                f'小米账号：{self.user_id} 登陆失效，请重新保存集成选项以更新登陆信息。',
                'Xiaomi Miot Warning',
                nid,
            )
            _LOGGER.error(
                'Xiaomi cloud: %s auth failed, Please update option for this integration to refresh token.\n%s',
                self.user_id,
                rdt,
            )
        else:
            _LOGGER.warning('Retry login xiaomi cloud failed: %s', self.username)
        return False

    def request_miot_api(self, api, data: dict, debug=True):
        url = self._get_api_url(self.default_server) + '/' + api
        rsp = self.request(url, {
            'data': json.dumps(data, separators=(',', ':')),
        })
        try:
            rdt = json.loads(rsp)
            if debug:
                _LOGGER.debug(
                    'Request miot api: %s %s result: %s',
                    api, data, rsp,
                )
        except (TypeError, ValueError) as exc:
            rdt = None
            _LOGGER.warning(
                'Request miot api: %s %s result: %s failed: %s',
                api, data, rsp, exc,
            )
        return rdt

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

    def get_device_list(self):
        rdt = self.request_miot_api('home/device_list', {
            'getVirtualModel': True,
            'getHuamiDevices': 0,
        }, debug=False) or {}
        if rdt and 'result' in rdt:
            return rdt['result']['list']
        _LOGGER.warning('Got xiaomi cloud devices for %s failed: %s', self.username, rdt)
        return None

    async def async_get_devices(self, renew=False):
        if not self.user_id:
            return None
        fnm = f'xiaomi_miot/devices-{self.user_id}-{self.default_server}.json'
        store = Store(self.hass, 1, fnm)
        now = time.time()
        dvs = None
        if not renew:
            dat = await store.async_load() or {}
            if isinstance(dat, dict):
                if dat.get('update_time', 0) > (now - 86400):
                    dvs = dat.get('devices') or []
        if not dvs:
            dvs = await self.hass.async_add_executor_job(self.get_device_list)
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
        fls = ['ssid', 'bssid', 'model', 'did']
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
        sdt = await mic.async_stored_auth(mic.user_id, save=False)
        config.update(sdt)
        mic.service_token = config.get('service_token')
        mic.ssecurity = config.get('ssecurity')
        await mic.async_login()
        return mic

    async def async_stored_auth(self, uid=None, save=False):
        if uid is None:
            uid = self.username
        fnm = f'xiaomi_miot/auth-{uid}-{self.default_server}.json'
        store = Store(self.hass, 1, fnm)
        old = await store.async_load() or {}
        if save:
            cfg = self.to_config()
            cfg.pop(CONF_PASSWORD, None)
            if cfg.get('service_token') == old.get('service_token'):
                cfg['update_at'] = old.get('update_at')
            else:
                cfg['update_at'] = f'{datetime.fromtimestamp(int(time.time()))}'
            await store.async_save(cfg)
            return cfg
        return old
