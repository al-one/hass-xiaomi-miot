"""Config flow to configure Xiaomi Miot."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import *
from homeassistant.helpers.device_registry import format_mac
import homeassistant.helpers.config_validation as cv

from miio import (
    Device as MiioDevice,
    DeviceException,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    DEFAULT_NAME,
    SUPPORTED_DOMAINS,
)

_LOGGER = logging.getLogger(__name__)

MIIO_CONFIG_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_TOKEN): vol.All(str, vol.Length(min=32, max=32)),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
    vol.Optional(CONF_MODE, default=[]): cv.multi_select(SUPPORTED_DOMAINS),
})


class XiaomiMiotFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
        self.host = None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input.get(CONF_HOST):
                self.host = user_input[CONF_HOST]
            token = user_input.get(CONF_TOKEN)
            device = MiioDevice(self.host, token)
            try:
                info = device.info()
            except DeviceException:
                info = None
                errors['base'] = 'cannot_connect'
            _LOGGER.debug('Xiaomi Miot async_step_user %s', {
                'user_input': user_input,
                'info': info,
                'errors': errors,
            })
            if info is not None:
                unique_id = format_mac(info.mac_address)
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                user_input['miio_info'] = dict(info.raw or {})
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME),
                    data=user_input,
                )
        return self.async_show_form(
            step_id='user',
            data_schema=MIIO_CONFIG_SCHEMA,
            errors=errors,
        )

    async def async_step_zeroconf(self, discovery_info):
        name = discovery_info.get('name')
        self.host = discovery_info.get('host')
        mac_address = discovery_info.get('properties', {}).get('mac')
        if not name or not self.host or not mac_address:
            return self.async_abort(reason='not_xiaomi_miio')
        if not name.startswith('xiaomi'):
            _LOGGER.debug('Device %s discovered with host %s, not xiaomi device', name, self.host)
            return self.async_abort(reason='not_xiaomi_miio')
        unique_id = format_mac(mac_address)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured({CONF_HOST: self.host})
        # pylint: disable=no-member # https://github.com/PyCQA/pylint/issues/3167
        self.context.update({
            'title_placeholders': {'name': f'{name}({self.host})'}
        })
        return await self.async_step_user()
