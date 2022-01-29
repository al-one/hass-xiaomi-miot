import logging
import json
import time
import base64
import hashlib
import micloud
import requests
from datetime import datetime
from functools import partial
from urllib.parse import urlparse

from homeassistant.const import *
from homeassistant.helpers.storage import Store
from homeassistant.components import persistent_notification

from .utils import RC4
from micloud import miutils
from micloud.micloudexception import MiCloudException

try:
    from micloud.micloudexception import MiCloudAccessDenied
except (ModuleNotFoundError, ImportError):
    class MiCloudAccessDenied(MiCloudException):
        """ micloud==0.4 """

_LOGGER = logging.getLogger(__name__)


class MiotCloud(micloud.MiCloud):
    def __init__(self, hass, username, password, country=None):
        super().__init__(username, password)
        self.hass = hass
        self.default_server = country or 'cn'
        self.http_timeout = 10
        self.attrs = {}

    def get_properties_for_mapping(self, did, mapping: dict):
        pms = []
        rmp = {}
        for k, v in mapping.items():
            if not isinstance(v, dict):
                continue
            s = v.get('siid')
            p = v.get('piid')
            pms.append({'did': str(did), 'siid': s, 'piid': p})
            rmp[f'prop.{s}.{p}'] = k
        rls = self.get_props(pms)
        if not rls:
            return None
        dls = []
        for v in rls:
            s = v.get('siid')
            p = v.get('piid')
            k = rmp.get(f'prop.{s}.{p}')
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
        timeout = kwargs.pop('timeout', self.http_timeout)
        params = {
            'did': did,
            'key': key,
            'type': typ,
            'time_start': now - 86400 * 7,
            'time_end': now + 60,
            'limit': 5,
            **kwargs,
        }
        rdt = self.request_miot_api('user/get_user_device_data', params, timeout=timeout) or {}
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
        rdt = None
        try:
            rdt = await self.hass.async_add_executor_job(
                partial(self.get_user_device_data, '1', 'check_auth', raw=True, timeout=30)
            ) or {}
            nid = f'xiaomi-miot-auth-warning-{self.user_id}'
            eno = rdt.get('code', 0)
            if eno != 3:
                return True
        except requests.exceptions.ConnectionError:
            return None
        # auth err
        self.service_token = None
        self.ssecurity = None
        if await self.async_login():
            await self.async_stored_auth(self.user_id, save=True)
            persistent_notification.dismiss(self.hass, nid)
            return True
        if notify:
            persistent_notification.create(
                self.hass,
                f'Xiaomi account: {self.user_id} auth failed, '
                'Please update option for this integration to refresh token.\n'
                f'小米账号：{self.user_id} 登陆失效，请重新保存集成选项以更新登陆信息。',
                'Xiaomi Miot Warning',
                nid,
            )
            _LOGGER.error(
                'Xiaomi account: %s auth failed, Please update option for this integration to refresh token.\n%s',
                self.user_id,
                rdt,
            )
        else:
            _LOGGER.warning('Retry login xiaomi account failed: %s', self.username)
        return False

    async def async_request_api(self, *args, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.request_miot_api, *args, **kwargs)
        )

    def request_miot_api(self, api, data, method='POST', crypt=True, debug=True, **kwargs):
        params = {}
        if data is not None:
            params['data'] = self.json_encode(data)
        if crypt:
            rsp = self.request_rc4_api(api, params, method, **kwargs)
        else:
            rsp = self.request(self.get_api_url(api), params, **kwargs)
        try:
            rdt = json.loads(rsp)
            if debug:
                _LOGGER.debug(
                    'Request miot api: %s %s result: %s',
                    api, data, rsp,
                )
        except (TypeError, ValueError):
            rdt = None
        if not rdt or rdt.get('code'):
            fun = _LOGGER.info if rdt else _LOGGER.warning
            fun(
                'Request miot api: %s %s failed, result: %s',
                api, data, rsp,
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
            'getHuamiDevices': 1,
            'get_split_device': False,
            'support_smart_home': True,
        }, debug=False, timeout=60) or {}
        if rdt and 'result' in rdt:
            return rdt['result']['list']
        _LOGGER.warning('Got xiaomi cloud devices for %s failed: %s', self.username, rdt)
        return None

    def get_home_devices(self):
        rdt = self.request_miot_api('homeroom/gethome', {
            'fetch_share_dev': True,
        }, debug=False, timeout=60) or {}
        rdt = rdt.get('result') or {}
        rdt.setdefault('devices', {})
        for h in rdt.get('homelist', []):
            for r in h.get('roomlist', []):
                for did in r.get('dids', []):
                    rdt['devices'][did] = {
                        'home_id': h.get('id'),
                        'room_id': r.get('id'),
                        'home_name': h.get('name'),
                        'room_name': r.get('name'),
                    }
        return rdt

    async def async_get_devices(self, renew=False):
        if not self.user_id:
            return None
        fnm = f'xiaomi_miot/devices-{self.user_id}-{self.default_server}.json'
        store = Store(self.hass, 1, fnm)
        now = time.time()
        cds = []
        dat = await store.async_load() or {}
        if isinstance(dat, dict):
            if dat.get('update_time', 0) > (now - 86400):
                cds = dat.get('devices') or []
        dvs = None if renew else cds
        if not dvs:
            try:
                dvs = await self.hass.async_add_executor_job(self.get_device_list)
                if dvs:
                    hls = await self.hass.async_add_executor_job(self.get_home_devices)
                    if hls:
                        hds = hls.get('devices') or {}
                        dvs = [
                            {**d, **(hds.get(d.get('did')) or {})}
                            for d in dvs
                        ]
                    dat = {
                        'update_time': now,
                        'devices': dvs,
                        'homes': hls.get('homelist', []),
                    }
                    await store.async_save(dat)
                    _LOGGER.info('Got %s devices from xiaomi cloud', len(dvs))
            except requests.exceptions.ConnectionError as exc:
                if not cds:
                    raise exc
                dvs = cds
                _LOGGER.warning('Get xiaomi devices filed: %s, use cached %s devices.', exc, len(cds))
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
            if self.is_hide(d):
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

    @staticmethod
    def is_hide(d):
        did = d.get('did', '')
        pid = d.get('pid', '')
        if pid == '21':
            prt = d.get('parent_id')
            if prt and prt in did:
                # issues/263
                return True
        return False

    async def async_login(self):
        return await self.hass.async_add_executor_job(self._login_request)

    def _login_request(self):
        self._init_session()
        sign = self._login_step1()
        if not sign.startswith('http'):
            location = self._login_step2(sign)
        else:
            location = sign  # we already have login location
        response3 = self._login_step3(location)
        if response3.status_code == 403:
            raise MiCloudAccessDenied('Access denied. Did you set the correct username/password ?')
        elif response3.status_code == 200:
            return True
        else:
            _LOGGER.warning(
                'Xiaomi login request returned status %s, reason: %s, content: %s',
                response3.status_code, response3.reason, response3.text,
            )
            raise MiCloudException(f'Login to xiaomi error: {response3.text} ({response3.status_code})')

    def _login_step2(self, sign):
        url = "https://account.xiaomi.com/pass/serviceLoginAuth2"
        post_data = {
            'sid': "xiaomiio",
            'hash': hashlib.md5(self.password.encode()).hexdigest().upper(),
            'callback': "https://sts.api.io.mi.com/sts",
            'qs': '%3Fsid%3Dxiaomiio%26_json%3Dtrue',
            'user': self.username,
            '_json': 'true'
        }
        if sign:
            post_data['_sign'] = sign
        response = self.session.post(url, data=post_data)
        response_json = json.loads(response.text.replace('&&&START&&&', ''))
        location = response_json.get('location')
        if not location:
            self.attrs['notificationUrl'] = response_json.get('notificationUrl')
            raise MiCloudAccessDenied(f'Login to xiaomi error: {response.text}')
        self.user_id = str(response_json.get('userId'))
        self.ssecurity = response_json.get('ssecurity')
        self.cuser_id = response_json.get('cUserId')
        self.pass_token = response_json.get('passToken')
        return location

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
    async def from_token(hass, config: dict, login=True):
        mic = MiotCloud(
            hass,
            config.get(CONF_USERNAME),
            config.get(CONF_PASSWORD),
            config.get('server_country'),
        )
        mic.user_id = str(config.get('user_id') or '')
        sdt = await mic.async_stored_auth(mic.user_id, save=False)
        config.update(sdt)
        mic.service_token = config.get('service_token')
        mic.ssecurity = config.get('ssecurity')
        if login:
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

    def api_session(self):
        if not self.service_token or not self.user_id:
            raise MiCloudException('Cannot execute request. service token or userId missing. Make sure to login.')

        session = requests.Session()
        session.headers.update({
            'X-XIAOMI-PROTOCAL-FLAG-CLI': 'PROTOCAL-HTTP2',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': self.useragent,
        })
        session.cookies.update({
            'userId': str(self.user_id),
            'yetAnotherServiceToken': self.service_token,
            'serviceToken': self.service_token,
            'locale': str(self.locale),
            'timezone': str(self.timezone),
            'is_daylight': str(time.daylight),
            'dst_offset': str(time.localtime().tm_isdst * 60 * 60 * 1000),
            'channel': 'MI_APP_STORE'
        })
        return session

    def request(self, url, params, **kwargs):
        self.session = self.api_session()
        timeout = kwargs.get('timeout', self.http_timeout)
        try:
            nonce = miutils.gen_nonce()
            signed_nonce = miutils.signed_nonce(self.ssecurity, nonce)
            signature = miutils.gen_signature(url.replace('/app/', '/'), signed_nonce, nonce, params)
            post_data = {
                'signature': signature,
                '_nonce': nonce,
                'data': params['data'],
            }
            response = self.session.post(url, data=post_data, timeout=timeout)
            return response.text
        except requests.exceptions.HTTPError as exc:
            _LOGGER.error('Error while executing request to %s: %s', url, exc)
        except MiCloudException as exc:
            _LOGGER.error('Error while decrypting response of request to %s: %s', url, exc)

    def request_rc4_api(self, api, params: dict, method='POST', **kwargs):
        self.session = self.api_session()
        self.session.headers.update({
            'MIOT-ENCRYPT-ALGORITHM': 'ENCRYPT-RC4',
            'Accept-Encoding': 'identity',
        })
        url = self.get_api_url(api)
        timeout = kwargs.get('timeout', self.http_timeout)
        try:
            params = self.rc4_params(method, url, params)
            signed_nonce = self.signed_nonce(params['_nonce'])
            if method == 'GET':
                response = self.session.get(url, params=params, timeout=timeout)
            else:
                response = self.session.post(url, data=params, timeout=timeout)
            rsp = response.text
            if not rsp or 'error' in rsp or 'invalid' in rsp:
                _LOGGER.warning('Error while executing request to %s :%s', url, rsp)
            elif 'message' not in rsp:
                try:
                    rsp = MiotCloud.decrypt_data(signed_nonce, rsp)
                except ValueError:
                    _LOGGER.warning('Error while decrypting response of request to %s :%s', url, rsp)
            return rsp
        except requests.exceptions.HTTPError as exc:
            _LOGGER.warning('Error while executing request to %s :%s', url, exc)
        except MiCloudException as exc:
            _LOGGER.warning('Error while decrypting response of request to %s :%s', url, exc)

    def get_api_by_host(self, host, api=''):
        srv = self.default_server.lower()
        if srv and srv != 'cn':
            host = f'{srv}.{host}'
        api = str(api).lstrip('/')
        return f'https://{host}/{api}'

    def get_api_url(self, api):
        if api[:6] == 'https:' or api[:5] == 'http:':
            url = api
        else:
            api = str(api).lstrip('/')
            url = self._get_api_url(self.default_server) + '/' + api
        return url

    def rc4_params(self, method, url, params: dict):
        nonce = miutils.gen_nonce()
        signed_nonce = self.signed_nonce(nonce)
        params['rc4_hash__'] = MiotCloud.sha1_sign(method, url, params, signed_nonce)
        for k, v in params.items():
            params[k] = MiotCloud.encrypt_data(signed_nonce, v)
        params.update({
            'signature': MiotCloud.sha1_sign(method, url, params, signed_nonce),
            'ssecurity': self.ssecurity,
            '_nonce': nonce,
        })
        return params

    def signed_nonce(self, nonce):
        return miutils.signed_nonce(self.ssecurity, nonce)

    @staticmethod
    def json_encode(data):
        return json.dumps(data, separators=(',', ':'))

    @staticmethod
    def sha1_sign(method, url, dat: dict, nonce):
        path = urlparse(url).path
        if path[:5] == '/app/':
            path = path[4:]
        arr = [str(method).upper(), path]
        for k, v in dat.items():
            arr.append(f'{k}={v}')
        arr.append(nonce)
        raw = hashlib.sha1('&'.join(arr).encode('utf-8')).digest()
        return base64.b64encode(raw).decode()

    @staticmethod
    def encrypt_data(pwd, data):
        return base64.b64encode(RC4(base64.b64decode(pwd)).init1024().crypt(data)).decode()

    @staticmethod
    def decrypt_data(pwd, data):
        return RC4(base64.b64decode(pwd)).init1024().crypt(base64.b64decode(data))
