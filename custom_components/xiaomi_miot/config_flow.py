"""Config flow to configure Xiaomi Miot."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import *
from homeassistant.core import callback
from homeassistant.helpers.device_registry import format_mac

from miio import (
    Device as MiioDevice,
    DeviceException,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    DEFAULT_NAME,
)
from .core.miot_spec import MiotSpec

_LOGGER = logging.getLogger(__name__)


async def check_miio_device(hass, user_input, errors):
    host = user_input.get(CONF_HOST)
    token = user_input.get(CONF_TOKEN)
    try:
        device = MiioDevice(host, token)
        info = await hass.async_add_executor_job(device.info)
    except DeviceException:
        info = None
        errors['base'] = 'cannot_connect'
    _LOGGER.debug('Xiaomi Miot config flow: %s', {
        'user_input': user_input,
        'miio_info': info,
        'errors': errors,
    })
    if info is not None:
        if not user_input.get(CONF_MODEL):
            user_input[CONF_MODEL] = str(info.model or '')
        user_input['miio_info'] = dict(info.raw or {})
        miot_type = await MiotSpec.async_get_model_type(hass, user_input.get(CONF_MODEL))
        user_input['miot_type'] = miot_type
        user_input['unique_did'] = format_mac(info.mac_address)
    return user_input


class XiaomiMiotFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            await check_miio_device(self.hass, user_input, errors)
            if user_input.get('unique_did'):
                await self.async_set_unique_id(user_input['unique_did'])
                self._abort_if_unique_id_configured()
            if user_input.get('miio_info'):
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME),
                    data=user_input,
                )
        else:
            user_input = {}
        return self.async_show_form(
            step_id='user',
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, vol.UNDEFINED)): str,
                vol.Required(CONF_TOKEN, default=user_input.get(CONF_TOKEN, vol.UNDEFINED)):
                    vol.All(str, vol.Length(min=32, max=32)),
                vol.Optional(CONF_NAME, default=user_input.get(CONF_NAME, DEFAULT_NAME)): str,
            }),
            errors=errors,
        )

    async def async_step_zeroconf(self, discovery_info):
        name = discovery_info.get('name')
        host = discovery_info.get('host')
        mac_address = discovery_info.get('properties', {}).get('mac')
        if not name or not host or not mac_address:
            return self.async_abort(reason='not_xiaomi_miio')
        if not name.startswith('xiaomi'):
            _LOGGER.debug('Device %s discovered with host %s, not xiaomi device', name, host)
            return self.async_abort(reason='not_xiaomi_miio')
        unique_id = format_mac(mac_address)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured({CONF_HOST: host})
        # pylint: disable=no-member # https://github.com/PyCQA/pylint/issues/3167
        self.context.update({
            'title_placeholders': {'name': f'{name}({host})'}
        })
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return OptionsFlowHandler(entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        errors = {}
        if isinstance(user_input, dict):
            cfg = {}
            opt = {}
            for k, v in user_input.items():
                if k in [CONF_HOST, CONF_TOKEN, CONF_NAME]:
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
                vol.Optional('miot_cloud', default=user_input.get('miot_cloud', False)): bool,
            }),
            errors=errors,
        )
