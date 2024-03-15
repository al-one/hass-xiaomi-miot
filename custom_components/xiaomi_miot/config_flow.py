"""Config flow to configure Xiaomi Miot."""
import logging
import re
import copy
import requests
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_USERNAME,
)
from homeassistant.core import callback, split_entity_id
from homeassistant.util import yaml
from homeassistant.components import persistent_notification
from homeassistant.helpers.device_registry import format_mac
import homeassistant.helpers.config_validation as cv

from . import (
    DOMAIN,
    CONF_MODEL,
    CONF_CONN_MODE,
    CONF_SERVER_COUNTRY,
    CONF_CONFIG_VERSION,
    DEFAULT_NAME,
    DEFAULT_CONN_MODE,
    init_integration_data,
    get_customize_via_entity,
    get_customize_via_model,
)
from .core.utils import in_china, async_analytics_track_event
from .core.const import SUPPORTED_DOMAINS, CLOUD_SERVERS, CONF_XIAOMI_CLOUD
from .core.miot_spec import MiotSpec
from .core.xiaomi_cloud import (
    MiotCloud,
    MiCloudException,
    MiCloudAccessDenied,
)

from miio import (
    Device as MiioDevice,
    DeviceException,
)

_LOGGER = logging.getLogger(__name__)
DEFAULT_INTERVAL = 30

# 0.1 support multiple integration to add the same device
# 0.2 new entity id format (model_mac[-4:]_suffix)
# 0.3 washer modes via select
ENTRY_VERSION = 0.3

CONN_MODES = {
    'auto': 'Automatic (自动模式)',
    'local': 'Local (本地模式)',
    'cloud': 'Cloud (云端模式)',
}


async def check_miio_device(hass, user_input, errors):
    host = user_input.get(CONF_HOST)
    token = user_input.get(CONF_TOKEN)
    try:
        device = MiioDevice(host, token)
        info = await hass.async_add_executor_job(device.info)
    except DeviceException:
        device = None
        info = None
        errors['base'] = 'cannot_connect'
    _LOGGER.debug('Xiaomi Miot config flow: %s', {
        'user_input': user_input,
        'miio_info': info,
        'errors': errors,
    })
    model = ''
    if info is not None:
        if not user_input.get(CONF_MODEL):
            model = str(info.model or '')
            user_input[CONF_MODEL] = model
        user_input['miio_info'] = dict(info.raw or {})
        miot_type = await MiotSpec.async_get_model_type(hass, model)
        if not miot_type:
            miot_type = await MiotSpec.async_get_model_type(hass, model, use_remote=True)
        user_input['miot_type'] = miot_type
        user_input['unique_did'] = format_mac(info.mac_address)
        if miot_type and device:
            try:
                pms = [
                    {'did': 'miot', 'siid': 2, 'piid': 1},
                    {'did': 'miot', 'siid': 2, 'piid': 2},
                    {'did': 'miot', 'siid': 3, 'piid': 1},
                ]
                results = device.get_properties(pms, property_getter='get_properties') or []
                for prop in results:
                    if not isinstance(prop, dict):
                        continue
                    if prop.get('code') == 0:
                        # Collect supported models in LAN
                        await async_analytics_track_event(
                            hass, 'miot', 'local', model,
                            firmware=info.firmware_version,
                            results=results,
                        )
                        break
            except DeviceException:
                pass
    return user_input


async def check_xiaomi_account(hass, user_input, errors, renew_devices=False):
    dvs = []
    mic = None
    try:
        mic = await MiotCloud.from_token(hass, user_input, login=False)
        mic.login_times = 0
        await mic.async_login(captcha=user_input.get('captcha'))
        if not await mic.async_check_auth(False):
            raise MiCloudException('Login failed')
        user_input['xiaomi_cloud'] = mic
        dvs = await mic.async_get_devices(renew=renew_devices) or []
        if renew_devices:
            await MiotSpec.async_get_model_type(hass, 'xiaomi.miot.auto', use_remote=True)
    except (MiCloudException, MiCloudAccessDenied, Exception) as exc:
        err = f'{exc}'
        errors['base'] = 'cannot_login'
        if isinstance(exc, MiCloudAccessDenied) and mic:
            if url := mic.attrs.pop('notificationUrl', None):
                err = f'The login of Xiaomi account needs security verification. [Click here]({url}) to continue!\n' \
                      f'本次登录小米账号需要安全验证，[点击这里]({url})继续！你需要在与HA宿主机同局域网的设备下完成安全验证，' \
                      '如果你使用的是云服务器，将无法验证通过。'
                persistent_notification.create(
                    hass,
                    err,
                    f'Login to Xiaomi: {mic.username}',
                    f'{DOMAIN}-login',
                )
            elif url := mic.attrs.pop('captchaImg', None):
                err = f'Captcha:\n![captcha](data:image/jpeg;base64,{url})'
                user_input['xiaomi_cloud'] = mic
                user_input['captchaIck'] = mic.attrs.get('captchaIck')
        if isinstance(exc, requests.exceptions.ConnectionError):
            errors['base'] = 'cannot_reach'
        elif 'ZoneInfoNotFoundError' in err:
            errors['base'] = 'tzinfo_error'
        hass.data[DOMAIN]['placeholders'] = {'tip': f'⚠️ {err}'}
        unm = mic.username if mic else user_input.get(CONF_USERNAME)
        _LOGGER.error('Setup xiaomi cloud for user: %s failed: %s', unm, exc)
    if not errors:
        user_input['devices'] = dvs
        persistent_notification.dismiss(hass, f'{DOMAIN}-login')
    return user_input


async def get_cloud_filter_schema(hass, user_input, errors, schema=None, via_did=False):
    if not schema:
        schema = vol.Schema({})
    dvs = user_input.get('devices') or []
    if not dvs:
        errors['base'] = 'none_devices'
    else:
        grp = {}
        vls = {}
        fls = ['did'] if via_did else ['model', 'home_id', 'ssid', 'bssid']
        for d in dvs:
            for f in fls:
                v = d.get(f)
                if v is None:
                    continue
                grp.setdefault(v, 0)
                grp[v] += 1
                vls.setdefault(f, {})
                des = '<empty>' if v == '' else v
                if f == 'home_id':
                    des = d.get('home_name') or des
                if f in ['did']:
                    if MiotCloud.is_hide(d):
                        continue
                    dip = d.get('localip')
                    if not dip or d.get('pid') not in ['0', '8', '', None]:
                        dip = d.get('model')
                    vls[f][v] = f'{d.get("name")} ({dip})'
                elif f in ['model']:
                    dnm = f'{d.get("name")}'
                    if grp[v] > 1:
                        dnm += f' * {grp[v]}'
                    vls[f][v] = f'{des} ({dnm})'
                else:
                    vls[f][v] = f'{des} ({grp[v]})'
        ies = {
            'exclude': 'Exclude (排除)',
            'include': 'Include (包含)',
        }
        for f in fls:
            if not vls.get(f):
                continue
            fk = f'filter_{f}'
            fl = f'{f}_list'
            lst = vls.get(f, {})
            lst = dict(sorted(lst.items()))
            ols = [
                v
                for v in user_input.get(fl, [])
                if v in lst
            ]
            schema = schema.extend({
                vol.Required(fk, default=user_input.get(fk, 'exclude')): vol.In(ies),
                vol.Optional(fl, default=ols): cv.multi_select(lst),
            })
        hass.data[DOMAIN]['prev_input'] = user_input
    tip = ''
    if user_input.get(CONF_CONN_MODE) == 'local':
        url = 'https://github.com/al-one/hass-xiaomi-miot/issues/100#issuecomment-855183156'
        if user_input.get(CONF_SERVER_COUNTRY) == 'cn':
            tip = '⚠️ 在本地模式下，所有包含的设备都将通过本地miot协议连接，如果包含了不支持本地miot协议的设备，其实体会不可用，' \
                  f'建议只选择[支持本地模式的设备]({url})。'
        else:
            tip = '⚠️ In the local mode, all included devices will be connected via the local miot protocol.' \
                  'If the devices that does not support the local miot protocol are included,' \
                  'they will be unavailable. It is recommended to include only ' \
                  f'[the devices that supports the local mode]({url}).'
    hass.data[DOMAIN]['placeholders'] = {'tip': tip}
    return schema


class XiaomiMiotFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return OptionsFlowHandler(entry)

    async def async_step_user(self, user_input=None):
        self.context['last_step'] = False
        init_integration_data(self.hass)
        errors = {}
        if user_input is None:
            user_input = {}
        else:
            action = user_input.get('action')
            if action in ['account', 'cloud']:
                return await self.async_step_cloud()
            elif action in ['customizing_entity', 'customizing_device']:
                self.context['customizing_via'] = action
                return await self.async_step_customizing()
            else:
                return await self.async_step_token()
        prev_action = user_input.get('action', 'account')
        if prev_action == 'cloud':
            prev_action = 'account'
        actions = {
            'account': 'Add devices using Mi Account (账号集成)',
            'token': 'Add device using host/token (局域网集成)',
        }
        if self.hass.data[DOMAIN].get('entities', {}):
            actions.update({
                'customizing_entity': 'Customizing entity (自定义实体)',
                'customizing_device': 'Customizing device (自定义设备)',
            })
        return self.async_show_form(
            step_id='user',
            data_schema=vol.Schema({
                vol.Required('action', default=prev_action): vol.In(actions),
            }),
            errors=errors,
            last_step=self.context.get('last_step'),
        )

    async def async_step_token(self, user_input=None):
        errors = {}
        if user_input is None:
            user_input = {}
        else:
            await check_miio_device(self.hass, user_input, errors)
            if user_input.get('unique_did'):
                await self.async_set_unique_id(user_input['unique_did'])
                self._abort_if_unique_id_configured()
            if user_input.get('miio_info'):
                user_input[CONF_CONFIG_VERSION] = ENTRY_VERSION
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME),
                    data=user_input,
                )
        return self.async_show_form(
            step_id='token',
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, vol.UNDEFINED)): str,
                vol.Required(CONF_TOKEN, default=user_input.get(CONF_TOKEN, vol.UNDEFINED)):
                    vol.All(str, vol.Length(min=32, max=32)),
                vol.Optional(CONF_NAME, default=user_input.get(CONF_NAME, DEFAULT_NAME)): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=user_input.get(CONF_SCAN_INTERVAL, DEFAULT_INTERVAL)):
                    cv.positive_int,
            }),
            errors=errors,
        )

    async def async_step_cloud(self, user_input=None):
        # pylint: disable=invalid-name
        self.CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL
        errors = {}
        if user_input is None:
            user_input = {}
        else:
            await check_xiaomi_account(self.hass, user_input, errors, renew_devices=True)
            if not errors:
                return await self.async_step_cloud_filter(user_input)
        schema = {}
        if user_input.get('captchaIck'):
            schema.update({
                vol.Required('captcha', default=''): str,
            })
        schema.update({
            vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, vol.UNDEFINED)): str,
            vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, vol.UNDEFINED)): str,
            vol.Required(CONF_SERVER_COUNTRY, default=user_input.get(CONF_SERVER_COUNTRY, 'cn')):
                vol.In(CLOUD_SERVERS),
            vol.Required(CONF_CONN_MODE, default=user_input.get(CONF_CONN_MODE, 'auto')):
                vol.In(CONN_MODES),
            vol.Optional('filter_models', default=user_input.get('filter_models', False)): bool,
        })
        return self.async_show_form(
            step_id='cloud',
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders=self.hass.data[DOMAIN].pop('placeholders', {'tip': ''}),
        )

    async def async_step_cloud_filter(self, user_input=None):
        errors = {}
        schema = vol.Schema({})
        if user_input is None:
            user_input = {}
        if 'devices' in user_input:
            via_did = not user_input.get('filter_models')
            schema = await get_cloud_filter_schema(self.hass, user_input, errors, schema, via_did=via_did)
        elif 'prev_input' in self.hass.data[DOMAIN]:
            prev_input = self.hass.data[DOMAIN].pop('prev_input', None) or {}
            cfg = prev_input['xiaomi_cloud'].to_config() or {}
            cfg.update({
                CONF_CONN_MODE: prev_input.get(CONF_CONN_MODE),
                **(user_input or {}),
            })
            cfg[CONF_CONFIG_VERSION] = ENTRY_VERSION
            _LOGGER.debug('Setup xiaomi cloud: %s', {**cfg, CONF_PASSWORD: '*', 'service_token': '*'})
            return self.async_create_entry(
                title=f"Xiaomi: {cfg.get('user_id')}",
                data=cfg,
            )
        else:
            errors['base'] = 'unknown'
        return self.async_show_form(
            step_id='cloud_filter',
            data_schema=schema,
            errors=errors,
            description_placeholders=self.hass.data[DOMAIN].pop('placeholders', {'tip': ''}),
        )

    async def async_step_customizing(self, user_input=None):
        tip = ''
        via = self.context.get('customizing_via') or 'customizing_entity'
        self.context['customizing_via'] = via
        entry = await self.async_set_unique_id(f'{DOMAIN}-customizes')
        entry_data = copy.deepcopy(dict(entry.data) if entry else {})
        customizes = {}
        errors = {}
        schema = {}
        user_input = user_input or {}
        bool2selects = [
            'auto_cloud',
            'ignore_offline',
            'miot_local',
            'miot_cloud',
            'miot_cloud_write',
            'miot_cloud_action',
            'check_lan',
            'unreadable_properties',
        ]
        main_options = {
            'bool2selects': cv.multi_select({}),
            'interval_seconds': cv.string,
            'chunk_properties': cv.string,
            'sensor_properties': cv.string,
            'binary_sensor_properties': cv.string,
            'switch_properties': cv.string,
            'number_properties': cv.string,
            'select_properties': cv.string,
            'cover_properties': cv.string,
            'sensor_attributes': cv.string,
            'binary_sensor_attributes': cv.string,
            'button_actions': cv.string,
            'button_properties': cv.string,
            'light_services': cv.string,
            'fan_services': cv.string,
            'exclude_miot_services': cv.string,
            'exclude_miot_properties': cv.string,
            'main_miot_services': cv.string,
            'cloud_delay_update': cv.string,
        }
        options = {
            'entity_category': cv.string,
        }

        last_step = self.context.pop('last_step', False)
        customize_key = self.context.pop('customize_key', None)
        if last_step and customize_key:
            reset = user_input.pop('reset_customizes', None)
            b2s = user_input.pop('bool2selects', None) or []
            for k in b2s:
                user_input[k] = True
            entry_data.setdefault(via, {})
            entry_data[via][customize_key] = {
                k: v
                for k, v in user_input.items()
                if v not in [' ', '', None, vol.UNDEFINED]
            }
            if reset:
                entry_data[via].pop(customize_key, None)
            if entry:
                self.hass.config_entries.async_update_entry(entry, data=entry_data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                tip = f'```yaml\n{yaml.dump(entry_data)}\n```'
                return self.async_abort(
                    reason='config_saved',
                    description_placeholders={'tip': tip},
                )
            return self.async_create_entry(title='Xiaomi: Customizes', data=entry_data)

        elif via == 'customizing_entity':
            if entity := user_input.get('entity'):
                customizes = entry_data.get(via, {}).get(entity) or {}
                ent = self.hass.data[DOMAIN].get('entities', {}).get(entity)
                model = ent.model or ''
                for k, v in (get_customize_via_entity(ent) or {}).items():
                    customizes.setdefault(k, v)
                state = self.hass.states.get(entity)
                tip = f'{state.name}\n{entity}'
                if model:
                    tip += f'\n[{model}](https://home.miot-spec.com/spec/{model})'
                if not hasattr(ent, 'parent_entity'):
                    options = {**main_options, **options}
                get_customize_options(self.hass, options, bool2selects, entity_id=entity, model=model)
                if options:
                    self.context['last_step'] = True
                    self.context['customize_key'] = entity
            elif domain := user_input.get('domain'):
                entities = {}
                for state in sorted(
                        self.hass.states.async_all(domain),
                        key=lambda item: item.entity_id,
                ):
                    entity = state.entity_id
                    ent = self.hass.data[DOMAIN].get('entities', {}).get(entity)
                    if not ent:
                        continue
                    if user_input.get('only_main_entity') and hasattr(ent, 'parent_entity'):
                        continue
                    entities[entity] = f'{state.name} ({entity})'
                if entities:
                    schema.update({
                        vol.Required('entity'): vol.In(entities),
                    })
                else:
                    tip = f'None entities in `{domain}`'
            else:
                schema.update({
                    vol.Required('domain', default=user_input.get('domain', vol.UNDEFINED)): vol.In(SUPPORTED_DOMAINS),
                    vol.Optional('only_main_entity', default=user_input.get('only_main_entity', True)): cv.boolean,
                })

        elif via == 'customizing_device':
            model = user_input.get('model_specified') or user_input.get('model')
            if model:
                customizes = entry_data.get(via, {}).get(model) or {}
                for k, v in (get_customize_via_model(model) or {}).items():
                    customizes.setdefault(k, v)
                if '*' in model or ':' in model:
                    tip = model
                else:
                    tip = f'[{model}](https://home.miot-spec.com/spec/{model})'
                if ':' not in model:
                    options = {**main_options, **options}
                get_customize_options(self.hass, options, bool2selects, model=model)
                if options:
                    self.context['last_step'] = True
                    self.context['customize_key'] = model
            else:
                models = {}
                uds = {}
                for v in self.hass.data[DOMAIN].values():
                    if isinstance(v, dict):
                        if mod := v.get('miio_info', {}).get(CONF_MODEL):
                            models.append(mod)
                        v = v.get(CONF_XIAOMI_CLOUD)
                    if isinstance(v, MiotCloud):
                        mic = v
                        if mic.user_id not in uds:
                            uds[mic.user_id] = await mic.async_get_devices_by_key('model') or {}
                            models.update(uds[mic.user_id])
                if models:
                    models = sorted(models.keys())
                    schema.update({
                        vol.Required('model'): vol.In(models),
                    })
                schema.update({
                    vol.Optional('model_specified'): str,
                })

        if last_step := self.context.get('last_step', last_step):
            doc = 'https://github.com/al-one/hass-xiaomi-miot/issues/600'
            if in_china(self.hass):
                tip = f'[📚 自定义选项说明文档]({doc})\n\n------\n{tip}'
            else:
                tip = f'[❓ Need Help]({doc})\n\n------\n{tip}'
            if not options:
                tip += f'\n\n无可用的自定义选项。' if in_china(self.hass) else f'\n\nNo customizable options are available.'

            if 'bool2selects' in options:
                options['bool2selects'] = cv.multi_select(dict(zip(bool2selects, bool2selects)))
                customizes['bool2selects'] = [
                    k
                    for k in bool2selects
                    if customizes.get(k)
                ]
            schema.update({
                vol.Optional(k, default=customizes.get(k, vol.UNDEFINED), description=k): v
                for k, v in options.items()
            })
            schema.update({
                vol.Optional('reset_customizes', default=False): cv.boolean,
            })
            customizes.pop('bool2selects', None)
            customizes.pop('extend_miot_specs', None)
            if customizes:
                tip += f'\n```yaml\n{yaml.dump(customizes)}\n```'

        return self.async_show_form(
            step_id='customizing',
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={'tip': tip},
            last_step=last_step,
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        data = self.config_entry.data
        if CONF_USERNAME in data:
            return await self.async_step_cloud()

        if 'customizing_entity' in data or 'customizing_device' in data:
            tip = f'```yaml\n{yaml.dump(dict(data))}\n```'
            return self.async_abort(
                reason='show_customizes',
                description_placeholders={'tip': tip},
            )

        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        errors = {}
        if isinstance(user_input, dict):
            cfg = {}
            opt = {}
            for k, v in user_input.items():
                if k in [CONF_HOST, CONF_TOKEN, CONF_NAME, CONF_SCAN_INTERVAL]:
                    cfg[k] = v
                else:
                    opt[k] = v
            await check_miio_device(self.hass, user_input, errors)
            if user_input.get('miio_info'):
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data={**self.config_entry.data, **cfg}
                )
                return self.async_create_entry(title='', data=opt)
        else:
            user_input = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id='user',
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, vol.UNDEFINED)): str,
                vol.Required(CONF_TOKEN, default=user_input.get(CONF_TOKEN, vol.UNDEFINED)):
                    vol.All(str, vol.Length(min=32, max=32)),
                vol.Optional(CONF_SCAN_INTERVAL, default=user_input.get(CONF_SCAN_INTERVAL, DEFAULT_INTERVAL)):
                    cv.positive_int,
                vol.Optional('miot_cloud', default=user_input.get('miot_cloud', False)): bool,
            }),
            errors=errors,
        )

    async def async_step_cloud(self, user_input=None):
        errors = {}
        prev_input = {
            **self.config_entry.data,
            **self.config_entry.options,
        }
        if isinstance(user_input, dict):
            user_input = {
                **self.config_entry.data,
                **self.config_entry.options,
                **user_input,
            }
            renew = not not user_input.pop('renew_devices', False)
            await check_xiaomi_account(self.hass, user_input, errors, renew_devices=renew)
            if not errors:
                user_input['filter_models'] = prev_input.get('filter_models') and True
                if prev_input.get('filter_model'):
                    user_input['filter_models'] = True
                return await self.async_step_cloud_filter(user_input)
        else:
            user_input = prev_input
        schema = {}
        if user_input.get('captchaIck'):
            schema.update({
                vol.Required('captcha', default=''): str,
            })
        schema.update({
            vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, vol.UNDEFINED)): str,
            vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, vol.UNDEFINED)): str,
            vol.Required(CONF_SERVER_COUNTRY, default=user_input.get(CONF_SERVER_COUNTRY, 'cn')):
                vol.In(CLOUD_SERVERS),
            vol.Required(CONF_CONN_MODE, default=user_input.get(CONF_CONN_MODE, DEFAULT_CONN_MODE)):
                vol.In(CONN_MODES),
            vol.Optional('renew_devices', default=user_input.get('renew_devices', False)): bool,
            vol.Optional('disable_message', default=user_input.get('disable_message', False)): bool,
            vol.Optional('disable_scene_history', default=user_input.get('disable_scene_history', False)): bool,
        })
        return self.async_show_form(
            step_id='cloud',
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders=self.hass.data[DOMAIN].pop('placeholders', {'tip': ''}),
        )

    async def async_step_cloud_filter(self, user_input=None):
        errors = {}
        schema = vol.Schema({})
        if user_input is None:
            user_input = {}
        if 'devices' in user_input:
            user_input = {**self.config_entry.data, **self.config_entry.options, **user_input}
            via_did = not user_input.get('filter_models')
            schema = await get_cloud_filter_schema(self.hass, user_input, errors, schema, via_did=via_did)
        elif 'prev_input' in self.hass.data[DOMAIN]:
            prev_input = self.hass.data[DOMAIN].pop('prev_input', None) or {}
            cfg = prev_input['xiaomi_cloud'].to_config() or {}
            cfg.update({
                CONF_CONN_MODE: prev_input.get(CONF_CONN_MODE),
                'disable_message': prev_input.get('disable_message'),
                'disable_scene_history': prev_input.get('disable_scene_history'),
                **(user_input or {}),
            })
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, **cfg}
            )
            _LOGGER.debug('Setup xiaomi cloud: %s', {**cfg, CONF_PASSWORD: '*', 'service_token': '*'})
            return self.async_create_entry(title='', data={})
        else:
            errors['base'] = 'unknown'
        return self.async_show_form(
            step_id='cloud_filter',
            data_schema=schema,
            errors=errors,
            description_placeholders=self.hass.data[DOMAIN].pop('placeholders', {'tip': ''}),
        )


def get_customize_options(hass, options={}, bool2selects=[], entity_id='', model=''):  # noqa
    entity = None
    domain = ''
    if entity_id:
        entity = hass.data[DOMAIN].get('entities', {}).get(entity_id)
        domain, _ = split_entity_id(entity_id)
    attrs = entity.extra_state_attributes if entity else {}
    entity_class = attrs.get('entity_class')

    if domain == 'sensor':
        if entity_class in ['MiotSensorEntity']:
            options.update({
                'state_property': cv.string,
            })
        options.update({
            'value_ratio': cv.string,
            'state_class': cv.string,
            'device_class': cv.string,
            'unit_of_measurement': cv.string,
        })
        if entity_class in ['MihomeMessageSensor']:
            options.update({
                'filter_home': cv.string,
                'exclude_type': cv.string,
            })
        if entity_class in ['XiaoaiConversationSensor']:
            options.update({
                'interval_seconds': cv.string,
            })

    if domain == 'binary_sensor' or re.search(r'motion|magnet', model, re.I):
        bool2selects.extend(['reverse_state'])
        options.update({
            'state_property': cv.string,
            'motion_timeout': cv.string,
        })

    if domain == 'switch' or re.search(r'plug', model, re.I):
        bool2selects.extend(['reverse_state'])
        options.update({
            'descriptions_for_on': cv.string,
            'descriptions_for_off': cv.string,
            'stat_power_cost_key': cv.string,
            'stat_power_cost_type': cv.string,
        })
        if entity_class in ['MiotSwitchActionSubEntity']:
            options.update({
                'feeding_measure': cv.string,
            })

    if domain == 'light' or re.search(r'light', model, re.I):
        bool2selects.extend(['color_temp_reverse'])
        options.update({
            'brightness_for_on': cv.string,
            'brightness_for_off': cv.string,
        })

    if domain == 'fan' or re.search(r'\.fan\.|airpurifier|airfresh', model, re.I):
        options.update({
            'disable_preset_modes': cv.string,
            'speed_property': cv.string,
            'percentage_property': cv.string,
        })

    if domain == 'camera' or re.search(r'camera|videodoll', model, re.I):
        bool2selects.extend([
            'keep_streaming', 'use_rtsp_stream', 'use_alarm_playlist',
            'use_motion_stream', 'sub_motion_stream',
        ])
        options.update({
            'video_attribute': cv.string,
            'motion_stream_slice': cv.string,
        })

    if domain == 'climate' or re.search(r'aircondition|acpartner|airrtc', model, re.I):
        bool2selects.extend(['ignore_fan_switch', 'target2current_temp'])
        options.update({
            'bind_sensor': cv.string,
            'turn_on_hvac': cv.string,
            'current_temp_property': cv.string,
        })

    if domain == 'cover' or re.search(r'airer|curtain|wopener', model, re.I):
        bool2selects.extend([
            'motor_reverse', 'auto_position_reverse', 'position_reverse',
            'disable_target_position', 'target2current_position',
        ])
        options.update({
            'closed_position': cv.string,
            'deviated_position': cv.string,
            'open_texts': cv.string,
            'close_texts': cv.string,
        })

    if domain == 'media_player' or re.search(r'\.tv\.|tvbox|projector', model, re.I):
        bool2selects.extend(['turn_off_screen', 'xiaoai_silent'])
        options.update({
            'miot_did': cv.string,
            'bind_xiaoai': cv.string,
            'sources_via_apps': cv.string,
            'sources_via_keycodes': cv.string,
            'screenshot_compress': cv.string,
            'television_name': cv.string,
            'mitv_lan_host': cv.string,
        })

    if domain == 'number':
        bool2selects.extend(['restore_state'])

    if domain == 'humidifier':
        options.update({
            'mode_property': cv.string,
        })

    if domain == 'device_tracker' or re.search(r'watch', model, re.I):
        options.update({
            'coord_type': cv.string,
        })
        bool2selects.extend(['disable_location_name'])

    if domain == 'text' and re.search(r'execute_text_directive', entity_id, re.I):
        bool2selects.extend(['silent_execution'])

    if 'yeelink.' in model:
        options.update({
            'yeelight_smooth_on': cv.string,
            'yeelight_smooth_off': cv.string,
        })

    return options
