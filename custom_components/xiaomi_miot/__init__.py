"""Support for Xiaomi Miot."""
import logging
import asyncio
from datetime import timedelta
from functools import partial
import voluptuous as vol

from homeassistant import core, config_entries
from homeassistant.const import *
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import (
    Entity,
    ToggleEntity,
)
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

SUPPORTED_DOMAINS = [
    "sensor",
    "switch",
    "light",
    "fan",
    "climate",
    "cover",
]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_TOKEN): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_MODEL, default=''): cv.string,
        vol.Optional(CONF_MODE, default=[]): cv.ensure_list,
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
    hass.data[DOMAIN].setdefault('configs', {})
    component = EntityComponent(_LOGGER, DOMAIN, hass, SCAN_INTERVAL)
    hass.data[DOMAIN]['component'] = component
    await component.async_setup(config)
    bind_services_to_entries(hass, SERVICE_TO_METHOD_BASE)
    return True


async def async_setup_entry(hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry):
    entry_id = config_entry.entry_id
    unique_id = config_entry.unique_id
    info = config_entry.data.get('miio_info') or {}
    config = {}
    for k in [CONF_HOST, CONF_TOKEN, CONF_NAME, CONF_MODEL, CONF_MODE]:
        config[k] = config_entry.data.get(k)
    model = str(config.get(CONF_MODEL) or info.get(CONF_MODEL) or '')
    config[CONF_MODEL] = model
    modes = config.get(CONF_MODE, [])
    if not isinstance(modes, list):
        modes = str(modes).split(',')
    modes = [
        m
        for m in modes
        if m in SUPPORTED_DOMAINS
    ]
    config[CONF_MODE] = modes
    config['config_entry'] = config_entry
    hass.data[DOMAIN]['configs'][entry_id] = config
    hass.data[DOMAIN]['configs'][unique_id] = config
    _LOGGER.debug('Xiaomi Miot async_setup_entry %s', {
        'entry_id': entry_id,
        'unique_id': unique_id,
        'config': config,
        'miio': info,
    })
    for d in SUPPORTED_DOMAINS:
        hass.async_create_task(hass.config_entries.async_forward_entry_setup(config_entry, d))
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


class MiioEntity(Entity):
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
            _LOGGER.debug('Response received from miio %s: %s', self._name, result)
            return result == self._success_result
        except DeviceException as exc:
            if self._available:
                _LOGGER.error(mask_error, exc)
                self._available = False
            return False

    def send_command(self, method, params=[]):
        _LOGGER.debug('Send miio command to %s: %s(%s)', self._name, method, params)
        try:
            result = self._device.send(method, params)
        except DeviceException as ex:
            _LOGGER.error('Send miio command to %s: %s(%s) failed: %s', self._name, method, params, ex)
            return False
        ret = result == self._success_result
        if not ret:
            _LOGGER.info('Send miio command to %s failed: %s(%s), result: %s', self._name, method, params, result)
        return ret

    async def async_command(self, method, params=[]):
        return await self.hass.async_add_executor_job(self.send_command, method, params)

    async def async_update(self):
        try:
            attrs = await self.hass.async_add_executor_job(self._device.get_properties, self._props)
        except DeviceException as ex:
            if self._available:
                self._available = False
            _LOGGER.error('Got exception while fetching the state for %s (%s): %s', self._name, self._props, ex)
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

    def update_attrs(self, attrs: dict, update_parent=False):
        self._state_attrs.update(attrs or {})
        if update_parent and hasattr(self, '_parent'):
            if self._parent and hasattr(self._parent, 'update_attrs'):
                getattr(self._parent, 'update_attrs')(attrs or {}, False)
        return self._state_attrs


class MiotEntity(MiioEntity):
    def __init__(self, name, device):
        super().__init__(name, device)
        self._success_result = 0

    async def _try_command(self, mask_error, func, *args, **kwargs):
        result = None
        try:
            results = await self.hass.async_add_executor_job(partial(func, *args, **kwargs)) or []
            for result in results:
                break
            _LOGGER.debug('Response received from miot %s: %s', self._name, result)
            if isinstance(result, dict):
                return dict(result or {}).get('code', 1) == self._success_result
            else:
                return result == ['ok']
        except DeviceException as exc:
            if self._available:
                _LOGGER.error(mask_error, exc)
                self._available = False
            return False

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

    def set_property(self, field, value):
        _LOGGER.debug('Set miot property to %s: %s(%s)', self._name, field, value)
        result = None
        try:
            results = self._device.set_property(field, value) or []
            for result in results:
                break
        except DeviceException as ex:
            _LOGGER.error('Send miot property to %s: %s(%s) failed: %s', self._name, field, value, ex)
            return False
        ret = dict(result or {}).get('code', 1) == self._success_result
        if not ret:
            _LOGGER.info('Send miot property to %s failed: %s(%s), result: %s', self._name, field, value, result)
        return ret

    async def async_set_property(self, field, value):
        return await self.hass.async_add_executor_job(self.set_property, field, value)

    async def async_turn_on(self, **kwargs):
        await self.async_set_property('power', True)

    async def async_turn_off(self, **kwargs):
        await self.async_set_property('power', False)


class BaseSubEntity(Entity):
    def __init__(self, parent, attr, option=None):
        self._unique_id = f'{parent.unique_id}-{attr}'
        self._name = f'{parent.name} {attr}'
        self._state = STATE_UNKNOWN
        self._available = False
        self._parent = parent
        self._attr = attr
        self._option = dict(option or {})
        self._supported_features = int(self._option.get('supported_features', 0))
        self._state_attrs = {}

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def available(self):
        return self._available

    @property
    def supported_features(self):
        return self._supported_features

    @property
    def device_state_attributes(self):
        return self._state_attrs

    @property
    def device_class(self):
        return self._option.get('device_class', self._option.get('class'))

    @property
    def device_info(self):
        return self._parent.device_info

    @property
    def icon(self):
        return self._option.get('icon')

    @property
    def unit_of_measurement(self):
        return self._option.get('unit')

    def update(self):
        attrs = self._parent.device_state_attributes or {}
        if self._attr in attrs:
            self._available = True
            self._state = attrs.get(self._attr)
            keys = self._option.get('keys', [])
            if isinstance(keys, list):
                keys.append(self._attr)
            self._state_attrs = {}.update(attrs) if keys is True else {
                k: v
                for k, v in attrs.items()
                if k in keys
            }

    def update_attrs(self, attrs: dict, update_parent=True):
        self._state_attrs.update(attrs or {})
        if update_parent:
            if self._parent and hasattr(self._parent, 'update_attrs'):
                getattr(self._parent, 'update_attrs')(attrs or {}, False)
        return self._state_attrs

    def call_parent(self, method, *args, **kwargs):
        ret = None
        for f in cv.ensure_list(method):
            if hasattr(self._parent, f):
                ret = getattr(self._parent, f)(*args, **kwargs)
                break
        if ret:
            self.update()
        return ret


class ToggleSubEntity(BaseSubEntity, ToggleEntity):
    def __init__(self, parent, attr='power', option=None):
        super().__init__(parent, attr, option)

    def update(self):
        super().update()
        if self._available:
            attrs = self._state_attrs
            self._state = attrs.get(self._attr) == 'on'

    @property
    def state(self):
        return STATE_ON if self._state else STATE_OFF

    @property
    def is_on(self):
        return self._state

    def turn_on(self, **kwargs):
        self.call_parent('turn_on', **kwargs)

    def turn_off(self, **kwargs):
        self.call_parent('turn_off', **kwargs)
