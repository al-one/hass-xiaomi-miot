"""Support for Xiaomi Miot."""
import logging
import asyncio
from datetime import timedelta
from functools import partial
import voluptuous as vol

from homeassistant import core, config_entries
from homeassistant.const import *
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import ToggleEntity
from homeassistant.helpers.entity_component import EntityComponent
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.config_validation import (  # noqa: F401
    PLATFORM_SCHEMA,
    PLATFORM_SCHEMA_BASE,
    make_entity_service_schema,
)

from miio import (
    Device as MiioDevice,
    DeviceException,
)
from miio.miot_device import MiotDevice

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'xiaomi_miot'
SCAN_INTERVAL = timedelta(seconds=60)
DEFAULT_NAME = 'Xiaomi Miot'
CONF_MODEL = 'model'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_TOKEN): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_MODEL, default=''): cv.string,
        vol.Optional(CONF_MODE, default=''): cv.string,
    }
)

XIAOMI_MIIO_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
    },
)

SERVICE_TO_METHOD_BASE = {
    'send_command': {
        'method': 'async_command',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Required('method'): cv.string,
                vol.Optional('params', default=[]): cv.ensure_list,
            },
        ),
    },
    'set_property': {
        'method': 'async_set_property',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Required('field'): cv.string,
                vol.Required('value'): cv.match_all,
            },
        ),
    },
}


async def async_setup(hass, config: dict):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault('entities', {})
    component = EntityComponent(_LOGGER, DOMAIN, hass, SCAN_INTERVAL)
    hass.data[DOMAIN]['component'] = component
    await component.async_setup(config)
    bind_services_to_entries(hass, SERVICE_TO_METHOD_BASE)
    return True


async def async_setup_entry(hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry):
    hass.data[DOMAIN].setdefault('configs', {})
    entry_id = config_entry.entry_id
    unique_id = config_entry.unique_id
    info = config_entry.data.get('miio_info') or {}
    platforms = ['climate']
    plats = []
    config = {}
    for k in [CONF_HOST, CONF_TOKEN, CONF_NAME, CONF_MODE, CONF_MODE]:
        config[k] = config_entry.data.get(k)
    model = config.get(CONF_MODEL) or info.get(CONF_MODEL) or ''
    config[CONF_MODEL] = model
    mode = config.get(CONF_MODE) or ''
    for m in mode.split(','):
        if m in platforms:
            plats.append(m)
            config[CONF_MODE] = ''
    if not plats:
        if model.find('aircondition') > 0:
            plats = ['climate']
        else:
            plats = []
    hass.data[DOMAIN]['configs'][unique_id] = config
    _LOGGER.debug('Xiaomi Miot async_setup_entry %s', {
        'entry_id': entry_id,
        'unique_id': unique_id,
        'config': config,
        'plats': plats,
        'miio': info,
    })
    for plat in plats:
        hass.async_create_task(hass.config_entries.async_forward_entry_setup(config_entry, plat))
    return True


def bind_services_to_entries(hass, services):
    async def async_service_handler(service):
        method = services.get(service.service)
        fun = method['method']
        params = {
            key: value
            for key, value in service.data.items()
            if key != ATTR_ENTITY_ID
        }
        target_devices = []
        entity_ids = service.data.get(ATTR_ENTITY_ID)
        if entity_ids:
            target_devices = [
                dvc
                for dvc in hass.data[DOMAIN]['entities'].values()
                if dvc.entity_id in entity_ids
            ]
        _LOGGER.debug('Xiaomi Miot async_service_handler %s', {
            'targets': [dvc.entity_id for dvc in target_devices],
            'method': fun,
            'params': params,
        })
        update_tasks = []
        for dvc in target_devices:
            if not hasattr(dvc, fun):
                _LOGGER.info('%s have no method: %s', dvc.entity_id, fun)
                continue
            await getattr(dvc, fun)(**params)
            update_tasks.append(dvc.async_update_ha_state(True))
        if update_tasks:
            await asyncio.wait(update_tasks)

    for srv, obj in services.items():
        schema = obj.get('schema', XIAOMI_MIIO_SERVICE_SCHEMA)
        hass.services.async_register(DOMAIN, srv, async_service_handler, schema=schema)


class MiioEntity(ToggleEntity):
    def __init__(self, name, device):
        self._device = device
        try:
            self._miio_info = device.info()
        except DeviceException as exc:
            _LOGGER.error("Device %s unavailable or token incorrect: %s", name, exc)
            raise PlatformNotReady from exc
        self._unique_did = dr.format_mac(self._miio_info.mac_address)
        self._unique_id = self._unique_did
        self._name = name
        self._model = self._miio_info.model or ''
        self._state = None
        self._available = False
        self._state_attrs = {
            CONF_MODEL: self._model,
            'lan_ip': self._miio_info.network_interface.get('localIp'),
            'mac_address': self._miio_info.mac_address,
            'firmware_version': self._miio_info.firmware_version,
            'hardware_version': self._miio_info.hardware_version,
            'entity_class': self.__class__.__name__,
        }
        self._supported_features = 0
        self._props = ['power']
        self._success_result = ['ok']

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return self._name

    @property
    def available(self):
        return self._available

    @property
    def is_on(self):
        return self._state

    @property
    def device_state_attributes(self):
        return self._state_attrs

    @property
    def supported_features(self):
        return self._supported_features

    @property
    def device_info(self):
        return {
            'identifiers': {(DOMAIN, self._unique_did)},
            'name': self._name,
            'model': self._model,
            'manufacturer': (self._model or 'Xiaomi').split('.', 1)[0],
            'sw_version': self._miio_info.firmware_version,
        }

    async def _try_command(self, mask_error, func, *args, **kwargs):
        try:
            result = await self.hass.async_add_executor_job(partial(func, *args, **kwargs))
            _LOGGER.debug('Response received from %s: %s', self._name, result)
            return result == self._success_result
        except DeviceException as exc:
            if self._available:
                _LOGGER.error(mask_error, exc)
                self._available = False
            return False

    async def async_command(self, method, params=[], mask_error=None):
        _LOGGER.debug('Send miio command to %s: %s(%s)', self._name, method, params)
        if mask_error is None:
            mask_error = f'Send miio command to {self._name}: {method} failed: %s'
        result = await self._try_command(mask_error, self._device.send, method, params)
        if not result:
            _LOGGER.info('Send miio command to %s failed: %s(%s)', self._name, method, params)
        return result

    async def async_update(self):
        try:
            attrs = await self.hass.async_add_executor_job(partial(self._device.get_properties, self._props))
        except DeviceException as ex:
            if self._available:
                self._available = False
                _LOGGER.error('Got exception while fetching the state for %s: %s', self._name, ex)
            return
        attrs = dict(zip(self._props, attrs))
        _LOGGER.debug('Got new state from %s: %s', self._name, attrs)
        self._available = True
        self._state = attrs.get('power') == 'on'
        self._state_attrs.update(attrs)

    async def async_turn_on(self, **kwargs):
        await self._try_command('Turning on failed.', self._device.on)

    async def async_turn_off(self, **kwargs):
        await self._try_command('Turning off failed.', self._device.off)


class MiotEntity(MiioEntity):
    def __init__(self, name, device):
        super().__init__(name, device)
        self._success_result = 0

    async def _try_command(self, mask_error, func, *args, **kwargs):
        try:
            results = await self.hass.async_add_executor_job(partial(func, *args, **kwargs))
            for result in results:
                break
            _LOGGER.debug('Response received from miot %s: %s', self._name, result)
            return result.get('code', 1) == self._success_result
        except DeviceException as exc:
            if self._available:
                _LOGGER.error(mask_error, exc)
                self._available = False
            return False

    async def async_command(self, method, params=[], mask_error=None):
        _LOGGER.debug('Send miot command to %s: %s(%s)', self._name, method, params)
        if mask_error is None:
            mask_error = f'Send miot command to {self._name}: {method} failed: %s'
        result = await self._try_command(mask_error, self._device.send, method, params)
        if not result:
            _LOGGER.info('Send miot command to %s failed: %s(%s)', self._name, method, params)
        return result

    async def async_update(self):
        try:
            results = await self.hass.async_add_executor_job(partial(self._device.get_properties_for_mapping))
        except DeviceException as ex:
            if self._available:
                self._available = False
                _LOGGER.error('Got exception while fetching the state for %s: %s', self._name, ex)
            return
        attrs = {
            prop['did']: prop['value'] if prop['code'] == 0 else None
            for prop in results
        }
        _LOGGER.debug('Got new state from %s: %s', self._name, attrs)
        self._available = True
        self._state = True if attrs.get('power') else False
        self._state_attrs.update(attrs)

    async def async_set_property(self, field, value):
        return await self._try_command(
            f'Miot set_property failed. {field}: {value} %s',
            self._device.set_property,
            field,
            value,
        )

    async def async_turn_on(self, **kwargs):
        await self.async_set_property('power', True)

    async def async_turn_off(self, **kwargs):
        await self.async_set_property('power', False)
