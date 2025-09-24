import logging
import aiohttp
import asyncio
import json
import time
import string
import random
import base64
import locale
import hashlib
import micloud
import requests
from datetime import datetime
from functools import partial
from typing import Optional
from urllib import parse

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.components import persistent_notification

from .const import DOMAIN, CONF_XIAOMI_CLOUD
from .utils import RC4, local_zone, logger_filter
from micloud import miutils
from micloud.micloudexception import MiCloudException

try:
    from micloud.micloudexception import MiCloudAccessDenied
except (ModuleNotFoundError, ImportError):
    class MiCloudAccessDenied(MiCloudException):
        """ micloud==0.4 """

_LOGGER = logging.getLogger(__name__)
_LOGGER.addFilter(logger_filter)

ACCOUNT_BASE = 'https://account.xiaomi.com'
UA = "Android-7.1.1-1.0.0-ONEPLUS A3010-136-%s APP/xiaomi.smarthome APPV/62830"


class MiotCloud(micloud.MiCloud):
    user_id = None
    cuser_id = None
    ssecurity = None
    pass_token = None
    service_token = None
    failed_logins = 0
    session = None
    async_session: Optional[aiohttp.ClientSession] = None

    def __init__(self, hass, username, password, country=None, sid=None):
        try:
            super().__init__(username, password)
            timezone = datetime.now(local_zone(hass)).strftime('%z')
            self.timezone = 'GMT{0}:{1}'.format(timezone[:-2], timezone[-2:])
            self.locale = locale.getlocale()[0]
        except Exception:
            self.timezone = 'GMT+08:00'
            self.locale = 'zh_CN'

        self.hass = hass
        self.username = username
        self.password = password
        self.default_server = country or 'cn'
        self.sid = sid or 'xiaomiio'
        self.agent_id = self.get_random_string(16)
        self.client_id = self.agent_id
        self.useragent = UA % self.client_id
        self.http_timeout = int(hass.data[DOMAIN].get('config', {}).get('http_timeout') or 10)
        self.login_times = 0
        self.cookies = {}
        self.attrs = {}

    @property
    def unique_id(self):
        uid = self.user_id or self.username
        return f'{uid}-{self.default_server}-{self.sid}'

    async def async_get_properties_for_mapping(self, did, mapping: dict):
        pms = []
        rmp = {}
        for k, v in mapping.items():
            if not isinstance(v, dict):
                continue
            s = v.get('siid')
            p = v.get('piid')
            pms.append({'did': str(did), 'siid': s, 'piid': p})
            rmp[f'prop.{s}.{p}'] = k
        rls = await self.async_get_props(pms)
        if not rls:
            return None
        dls = []
        for v in rls:
            s = v.get('siid')
            p = v.get('piid')
            k = rmp.get(f'prop.{s}.{p}')
            if not k:
                continue
            v['prop'] = k
            dls.append(v)
        return dls

    async def async_get_props(self, params=None):
        return await self.async_request_miot_spec('prop/get', params)

    async def async_set_props(self, params=None):
        return await self.async_request_miot_spec('prop/set', params)

    async def async_do_action(self, params=None):
        return await self.async_request_miot_spec('action', params)

    async def async_request_miot_spec(self, api, params=None):
        rdt = await self.async_request_api('miotspec/' + api, {
            'params': params or [],
        }) or {}
        rls = rdt.get('result')
        if not rls and rdt.get('code'):
            raise MiCloudException(json.dumps(rdt))
        return rls

    async def async_get_user_device_data(self, did, key, typ='prop', raw=False, **kwargs):
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
        rdt = await self.async_request_api('user/get_user_device_data', params, timeout=timeout) or {}
        return rdt if raw else rdt.get('result')

    async def async_get_last_device_data(self, did, key, typ='prop', **kwargs):
        kwargs['raw'] = False
        kwargs['limit'] = 1
        rls = await self.async_get_user_device_data(did, key, typ, **kwargs) or [None]
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
        if self.service_token:
            api = 'v2/message/v2/check_new_msg'
            dat = {
                'begin_at': int(time.time()) - 60,
            }
            try:
                rdt = await self.async_request_api(api, dat, method='POST') or {}
                eno = rdt.get('code', 0)
                msg = rdt.get('message', '')
                if eno in [2, 3]:
                    pass
                elif 'auth err' in msg:
                    pass
                elif msg in ['invalid signature', 'SERVICETOKEN_EXPIRED']:
                    pass
                else:
                    return True
            except requests.exceptions.ConnectionError:
                return None
            except requests.exceptions.Timeout:
                return None
            # auth err
            _LOGGER.info('Xiaomi auth failed, try relogin. %s', rdt)
        nid = f'xiaomi-miot-auth-warning-{self.user_id}'
        need_verify = None
        try:
            if await self.async_relogin():
                persistent_notification.dismiss(self.hass, nid)
                return True
        except MiCloudNeedVerify as exc:
            need_verify = exc
        if notify:
            lnk = f'/config/integrations/integration/{DOMAIN}'
            persistent_notification.create(
                self.hass,
                f'Xiaomi account: {self.user_id} auth failed, '
                f'Your Xiaomi account login status has expired, Please login again through [integrated configuration]({lnk}).\n'
                f'你的小米账号登陆状态已失效，但本次需要手动验证，请通过[集成配置]({lnk})重新登陆。',
                'Xiaomi Miot Warning',
                nid,
            )
            _LOGGER.error(
                'Xiaomi account: %s auth failed, Please update option for this integration to refresh token.\n%s',
                self.user_id,
                rdt,
            )
        elif need_verify:
            raise need_verify
        else:
            _LOGGER.warning('Retry login xiaomi account failed: %s', self.username)
        return False

    async def async_request_api(self, api, data, method='POST', crypt=True, debug=True, **kwargs):
        if not self.service_token:
            await self.async_login()

        params = {}
        if data is not None:
            params['data'] = self.json_encode(data)
        raw = kwargs.pop('raw', self.sid != 'xiaomiio')
        rsp = None
        try:
            if raw:
                rsp = await self.hass.async_add_executor_job(
                    partial(self.request_raw, api, data, method, **kwargs)
                )
            elif crypt:
                rsp = await self.async_request_rc4_api(api, params, method, **kwargs)
            else:
                rsp = await self.hass.async_add_executor_job(
                    partial(self.request, self.get_api_url(api), params, **kwargs)
                )
            rdt = json.loads(rsp)
            if debug:
                _LOGGER.debug(
                    'Request miot api: %s %s result: %s',
                    api, data, rsp,
                )
            self.attrs['timeouts'] = 0
        except asyncio.TimeoutError as exc:
            rdt = None
            self.attrs.setdefault('timeouts', 0)
            self.attrs['timeouts'] += 1
            if 5 < self.attrs['timeouts'] <= 10:
                _LOGGER.error('Request xiaomi api: %s %s timeout, exception: %s', api, data, exc)
        except (TypeError, ValueError):
            rdt = None
        code = rdt.get('code') if rdt else None
        if code == 3:
            self._logout()
            _LOGGER.warning('Unauthorized while request to %s, response: %s, logged out.', api, rsp)
        elif code or not rdt:
            fun = _LOGGER.info if rdt else _LOGGER.warning
            fun('Request xiaomi api: %s %s failed, response: %s', api, data, rsp)
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

    async def get_device_list(self):
        rdt = await self.async_request_api('home/device_list', {
            'getVirtualModel': True,
            'getHuamiDevices': 1,
            'get_split_device': False,
            'support_smart_home': True,
        }, debug=False, timeout=60) or {}
        result = rdt.get('result')
        if result:
            return result['list']
        _LOGGER.warning('Got xiaomi devices for %s failed: %s', self.username, rdt)
        return None

    async def get_all_devices(self, homes=None):
        devices = {
            d['did']: d
            for d in await self.get_device_list() or []
        }
        if not isinstance(homes, list):
            return await self.get_device_list() or []
        for home in homes:
            hid = int(home.get('id', 0))
            uid = int(home.get('uid', 0))
            start_did = ''
            has_more = True
            while has_more:
                rdt = await self.async_request_api('v2/home/home_device_list', {
                    'home_owner': uid,
                    'home_id': hid,
                    'limit': 300,
                    'start_did': start_did,
                    'get_split_device': False,
                    'support_smart_home': True,
                    'get_cariot_device': True,
                    'get_third_device': True,
                }, debug=False, timeout=20) or {}
                result = rdt.get('result') or {}
                if not result:
                    _LOGGER.warning('Got xiaomi devices for %s failed: %s', self.username, rdt)
                for d in result.get('device_info') or []:
                    did = d.get('did')
                    devices.setdefault(did, {}).update(d)
                start_did = result.get('max_did') or ''
                has_more = result.get('has_more') and start_did
        return list(devices.values())

    async def get_home_devices(self):
        rdt = await self.async_request_api('v2/homeroom/gethome_merged', {
            'fg': True,
            'fetch_share': True,
            'fetch_share_dev': True,
            'fetch_cariot': True,
            'limit': 300,
            'app_ver': 7,
            'plat_form': 0,
        }, debug=False, timeout=60) or {}
        result = rdt.get('result') or {}
        if not result:
            _LOGGER.warning('Got xiaomi home devices for %s failed: %s', self.username, rdt)
        devices = result.setdefault('devices', {})
        for h in result.get('homelist', []):
            for r in h.get('roomlist', []):
                for did in r.get('dids', []):
                    devices[did] = {
                        'home_id': h.get('id'),
                        'room_id': r.get('id'),
                        'home_name': h.get('name'),
                        'room_name': r.get('name'),
                    }
        return result

    async def async_get_devices(self, renew=False, return_all=False):
        if not self.user_id:
            return None
        fnm = f'xiaomi_miot/devices-{self.user_id}-{self.default_server}.json'
        store = Store(self.hass, 1, fnm)
        now = time.time()
        cds = []
        dvs = []
        try:
            dat = await store.async_load() or {}
        except ValueError:
            await store.async_remove()
            dat = {}
        if isinstance(dat, dict):
            cds = dat.get('devices') or []
            if not renew and dat.get('update_time', 0) > (now - 86400):
                dvs = cds
        if not dvs:
            try:
                hls = await self.get_home_devices()
                dvs = await self.get_all_devices(hls.get('homelist', []))
                if dvs:
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
        if return_all:
            return dat
        return dvs

    async def async_renew_devices(self):
        return await self.async_get_devices(renew=True)

    async def async_get_devices_by_key(self, key, renew=False, filters=None):
        dat = {}
        if filters is None:
            filters = {}
        fls = ['ssid', 'bssid', 'home_id', 'model', 'did']
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

    async def async_get_homerooms(self, renew=False):
        dat = await self.async_get_devices(renew=renew, return_all=True) or {}
        return dat.get('homes') or []

    async def async_get_beaconkey(self, did):
        dat = {'did': did, 'pdid': 1}
        rdt = await self.async_request_api('v2/device/blt_get_beaconkey', dat) or {}
        return rdt.get('result', rdt)

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

    async def async_login(self, login_data=None):
        if self.login_times > 5:
            await self.async_stored_auth(remove=True)
        if self.login_times > 10:
            raise MiCloudException(
                'Too many failures when login to Xiaomi, '
                'please reload/config xiaomi_miot component.'
            )
        self.login_times += 1
        ret = await self.hass.async_add_executor_job(self._login_request, login_data)
        if ret:
            self.hass.data[DOMAIN]['sessions'][self.unique_id] = self
            await self.async_stored_auth(save=True)
            self.login_times = 0
        return ret

    async def async_relogin(self):
        self._logout()
        return await self.async_login()

    def _logout(self):
        self.service_token = None
        self.async_session = None

    def _login_request(self, login_data=None):
        self._init_session(True)
        location = ''
        auth = self.attrs.pop('login_data', {})
        if not login_data:
            pass
        elif ticket := login_data.get('verify_ticket'):
            resp = self.verify_ticket(ticket)
            location = resp.get('location', '')
            if location:
                self.account_get(location, allow_redirects=True)
                auth = self._login_step1()
                location = auth.get('location', '')
        elif auth:
            auth.update(login_data)
        else:
            auth = self._login_step1()
        if not location:
            location = self._login_step2(**auth)
        response = self._login_step3(location)
        http_code = response.status_code
        if http_code == 200:
            return True
        elif http_code == 403:
            raise MiCloudAccessDenied(f'Login to xiaomi error: {response.text} ({http_code})')
        else:
            _LOGGER.error(
                'Xiaomi login request returned status %s, reason: %s, content: %s',
                http_code, response.reason, response.text,
            )
            raise MiCloudException(f'Login to xiaomi error: {response.text} ({http_code})')

    def _login_step1(self):
        self.cookies.update({'sdkVersion': '3.8.6', 'deviceId': self.client_id})
        try:
            auth = self.account_get(
                '/pass/serviceLogin',
                params={'sid': self.sid, '_json': 'true'},
                headers={'User-Agent': self.useragent},
            )
        except Exception as exc:
            raise MiCloudException(f'Error getting xiaomi login sign. Cannot parse response. {exc}')
        if auth.get('code') == 0:
            self.user_id = auth.get('userId', self.user_id)
            self.cuser_id = auth.get('cUserId', self.cuser_id)
            self.ssecurity = auth.get('ssecurity', self.ssecurity)
            self.pass_token = auth.get('passToken', self.pass_token)
            self.async_session = None
        return auth

    def _login_step2(self, captcha=None, **kwargs):
        url = '/pass/serviceLoginAuth2'
        post = {
            'user': self.username,
            'hash': hashlib.md5(self.password.encode()).hexdigest().upper(),
            'callback': kwargs.get('callback') or '',
            'sid': kwargs.get('sid') or self.sid,
            'qs': kwargs.get('qs') or '',
            '_sign': kwargs.get('_sign') or '',
        }
        params = {'_json': 'true'}
        cookies = {}
        if captcha:
            post['captCode'] = captcha
            params['_dc'] = int(time.time() * 1000)
            cookies['ick'] = self.attrs.pop('captchaIck', '')
        response = self.account_post(url, data=post, params=params, cookies=cookies, response=True)
        auth = self.json_decode(response.text) or {}
        code = auth.get('code')
        # 20003 InvalidUserNameException
        # 22009 PackageNameDeniedException
        # 70002 InvalidCredentialException
        # 70016 InvalidCredentialException with captchaUrl / Password error
        # 81003 NeedVerificationException
        # 87001 InvalidResponseException captCode error
        # other NeedCaptchaException
        location = auth.get('location')
        if not location:
            if ntf := auth.get('notificationUrl'):
                if ntf[:4] != 'http':
                    ntf = f'{ACCOUNT_BASE}{ntf}'
                self.attrs['verify_url'] = ntf
                raise MiCloudNeedVerify('need_verify').with_url(ntf)
            if cap := auth.get('captchaUrl'):
                if cap[:4] != 'http':
                    cap = f'{ACCOUNT_BASE}{cap}'
                if self._get_captcha(cap):
                    self.attrs['login_data'] = kwargs
            _LOGGER.error(
                'Xiaomi serviceLoginAuth2: %s' %
                [url, self.login_times, {**post, 'hash': '*'}, cookies, response.text],
            )
            raise MiCloudAccessDenied(f'Login to xiaomi error: {response.text}')
        self.user_id = str(auth.get('userId', ''))
        self.cuser_id = auth.get('cUserId')
        self.ssecurity = auth.get('ssecurity')
        self.pass_token = auth.get('passToken')
        if self.sid != 'xiaomiio':
            sign = f'nonce={auth.get("nonce")}&{auth.get("ssecurity")}'
            sign = hashlib.sha1(sign.encode()).digest()
            sign = base64.b64encode(sign).decode()
            location += '&clientSign=' + parse.quote(sign)
        _LOGGER.info('Xiaomi serviceLoginAuth2: %s', [auth, self.cookies])
        return location

    def _login_step3(self, location):
        self.session.headers.update({'content-type': 'application/x-www-form-urlencoded'})
        response = self.account_get(location, response=True)
        cookies = response.cookies
        service_token = cookies.get('serviceToken')
        if service_token:
            self.service_token = service_token
            self.user_id = cookies.get('userId', self.user_id)
            self.cuser_id = cookies.get('cUserId', self.cuser_id)
            self.async_session = None
        else:
            err = {
                'location': location,
                'status_code': response.status_code,
                'cookies': cookies.get_dict(),
                'response': response.text,
            }
            raise MiCloudAccessDenied(f'Login to xiaomi error: {err}')
        return response

    def _get_captcha(self, url):
        response = self.session.get(url)
        if ick := response.cookies.get('ick'):
            self.attrs['captchaIck'] = ick
            self.attrs['captchaImg'] = base64.b64encode(response.content).decode()
        return ick

    def check_identity_list(self, url, path='fe/service/identity/authStart'):
        if path not in url:
            return None
        resp = self.account_get(url.replace(path, 'identity/list'), response=True)
        identity_session = resp.cookies.get('identity_session')
        if not identity_session:
            return False
        data = self.json_decode(resp.text) or {}
        flag = data.get('flag', 4)
        options = data.get('options', [flag])
        return options

    def verify_ticket(self, ticket):
        url = self.attrs.get('verify_url')
        if not url:
            return {}
        options = self.check_identity_list(url) or []
        for flag in options:
            api = {
                4: '/identity/auth/verifyPhone',
                8: '/identity/auth/verifyEmail',
            }.get(flag)
            if not api:
                continue
            data = self.account_post(
                api,
                params={
                    '_dc': int(time.time() * 1000),
                },
                data={
                    '_flag': flag,
                    'ticket': ticket,
                    'trust': 'true',
                    '_json': 'true',
                },
                cookies={
                    'identity_session': self.attrs.get('identity_session'),
                },
            )
            if data.get('code') == 0:
                self.attrs.pop('identity_session', None)
                return data
        return {}

    def account_get(self, url, method='GET', **kwargs):
        return self.account_post(url, method, **kwargs)

    def account_post(self, url, method='POST', **kwargs):
        if url[:4] != 'http':
            url = f'{ACCOUNT_BASE}{url}'
        kwargs['cookies'] = {
            **self.cookies,
            **kwargs.get('cookies', {}),
        }
        kwargs.setdefault('headers', {'User-Agent': self.useragent})
        response = kwargs.pop('response', None)
        resp = self.session.request(method, url, **kwargs)
        try:
            data = self.json_decode(resp.text) or {}
        except Exception:
            data = {
                'code': resp.status_code,
                'response': resp.text,
            }
        cookies = resp.cookies.get_dict()
        self.cookies.update(cookies)
        log = _LOGGER.warning if data.get('code') else _LOGGER.info
        log('Account request: %s' % [url, kwargs, resp.text, cookies])
        if response:
            return resp
        return data

    def json_decode(self, text):
        return json.loads(text.replace('&&&START&&&', ''))

    def to_config(self):
        return {
            CONF_USERNAME: self.username,
            CONF_PASSWORD: self.password,
            'server_country': self.default_server,
            'user_id': self.user_id,
            'service_token': self.service_token,
            'ssecurity': self.ssecurity,
            'sid': self.sid,
            'device_id': self.client_id,
        }

    @staticmethod
    async def from_token(hass, config: dict, login=None):
        mic = await hass.async_add_executor_job(
            MiotCloud,
            hass,
            config.get(CONF_USERNAME),
            config.get(CONF_PASSWORD),
            config.get('server_country'),
            config.get('sid'),
        )
        mic.user_id = str(config.get('user_id') or '')
        if a := hass.data[DOMAIN].get('sessions', {}).get(mic.unique_id):
            mic = a
            mic.merger_config(config)
        if not mic.service_token:
            sdt = await mic.async_stored_auth(save=False)
            config.update(sdt)
            mic.service_token = config.get('service_token')
            mic.ssecurity = config.get('ssecurity')
            did = config.get('device_id') or ''
            if did and len(did) <= 32:
                mic.client_id = did
                mic.useragent = UA % did
        if login is None:
            if not mic.service_token:
                login = True
        if login:
            await mic.async_login()
        else:
            hass.data[DOMAIN]['sessions'][mic.unique_id] = mic
        return mic

    def merger_config(self, config: dict, changed=None):
        if self.username != config.get(CONF_USERNAME):
            self.username = config.get(CONF_USERNAME)
            changed = True
        if self.password != config.get(CONF_PASSWORD):
            self.password = config.get(CONF_PASSWORD)
            changed = True
        if changed:
            self.async_session = None
            self.service_token = None
            self.ssecurity = None
            self.cookies = {}
            self.attrs = {}
        return self

    async def async_change_sid(self, sid: str, login=None):
        config = {
            **self.to_config(),
            'sid': sid,
            'service_token': None,
            'ssecurity': None,
        }
        mic = await self.from_token(self.hass, config, login)
        return mic

    async def async_stored_auth(self, uid=None, save=False, remove=False):
        if not uid:
            uid = self.user_id or self.username
        fnm = f'xiaomi_miot/auth-{uid}-{self.default_server}.json'
        if self.sid != 'xiaomiio':
            fnm = fnm.replace('.json', f'-{self.sid}.json')
        store = Store(self.hass, 1, fnm)
        if remove:
            await store.async_remove()
        try:
            old = await store.async_load() or {}
        except ValueError:
            if not remove:
                await store.async_remove()
            old = {}
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

    def api_session(self, **kwargs):
        if not self.service_token or not self.user_id:
            raise MiCloudException('Cannot execute request. service token or userId missing. Make sure to login.')

        if kwargs.get('async'):
            session = self.async_session
            if not session or session.closed:
                session = async_create_clientsession(
                    self.hass,
                    headers=self.api_headers(),
                    cookies=self.api_cookies(),
                )
                self.async_session = session
        else:
            session = requests.Session()
            session.headers.update(self.api_headers())
            session.cookies.update(self.api_cookies())
        return session

    def api_headers(self):
        return {
            'X-XIAOMI-PROTOCAL-FLAG-CLI': 'PROTOCAL-HTTP2',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': self.useragent,
        }

    def api_cookies(self):
        return {
            'userId': str(self.user_id),
            'yetAnotherServiceToken': self.service_token,
            'serviceToken': self.service_token,
            'locale': str(self.locale),
            'timezone': str(self.timezone),
            'is_daylight': str(time.daylight),
            'dst_offset': str(time.localtime().tm_isdst * 60 * 60 * 1000),
            'channel': 'MI_APP_STORE',
        }

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
                _LOGGER.warning('Error while executing request to %s: %s', url, rsp or response.status_code)
            elif 'message' not in rsp:
                try:
                    rsp = MiotCloud.decrypt_data(signed_nonce, rsp)
                except ValueError:
                    _LOGGER.warning('Error while decrypting response of request to %s :%s', url, rsp)
            return rsp
        except requests.exceptions.HTTPError as exc:
            _LOGGER.warning('Error while executing request to %s: %s', url, exc)
        except MiCloudException as exc:
            _LOGGER.warning('Error while decrypting response of request to %s :%s', url, exc)

    async def async_request_rc4_api(self, api, params: dict, method='POST', **kwargs):
        url = self.get_api_url(api)
        session = self.api_session(**{'async': True})
        timeout = aiohttp.ClientTimeout(total=kwargs.get('timeout', self.http_timeout))
        headers = {
            'MIOT-ENCRYPT-ALGORITHM': 'ENCRYPT-RC4',
            'Accept-Encoding': 'identity',
        }
        try:
            params = self.rc4_params(method, url, params)
            if method == 'GET':
                response = await session.get(url, params=params, timeout=timeout, headers=headers)
            else:
                response = await session.post(url, data=params, timeout=timeout, headers=headers)
            rsp = await response.text()
            if not rsp or 'error' in rsp or 'invalid' in rsp:
                _LOGGER.warning('Error while executing request to %s: %s', url, rsp or response.status)
            elif 'message' not in rsp:
                try:
                    signed_nonce = self.signed_nonce(params['_nonce'])
                    rsp = MiotCloud.decrypt_data(signed_nonce, rsp)
                except ValueError:
                    _LOGGER.warning('Error while decrypting response of request to %s :%s', url, rsp)
            return rsp
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            _LOGGER.warning('Error while executing request to %s: %s', url, exc)

    def request_raw(self, url, data=None, method='GET', **kwargs):
        self.session = self.api_session()
        url = self.get_api_url(url)
        kwargs.setdefault('params' if method == 'GET' else 'data', data)
        kwargs.setdefault('timeout', self.http_timeout)
        try:
            response = self.session.request(method, url, **kwargs)
            if response.status_code == 401:
                self._logout()
                _LOGGER.warning('Unauthorized while executing request to %s, logged out.', url)
            rsp = response.text
            if not rsp or 'error' in rsp or 'invalid' in rsp:
                log = _LOGGER.info if 'remote/ubus' in url else _LOGGER.warning
                log('Error while executing request to %s: %s', url, rsp or response.status_code)
            return rsp
        except requests.exceptions.HTTPError as exc:
            _LOGGER.warning('Error while executing request to %s: %s', url, exc)
        return None

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
        path = parse.urlparse(url).path
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

    @staticmethod
    def all_clouds(hass):
        cls = {}
        for k, v in hass.data[DOMAIN].items():
            if isinstance(v, dict):
                v = v.get(CONF_XIAOMI_CLOUD)
            if isinstance(v, MiotCloud):
                cls[v.unique_id] = v
        return list(cls.values())

    @staticmethod
    def get_random_string(length):
        seq = string.ascii_uppercase + string.digits
        return ''.join((random.choice(seq) for _ in range(length)))


class MiCloudNeedVerify(MiCloudException):
    url = None

    def with_url(self, url):
        self.url = url
        return self
