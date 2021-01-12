"""Support for Xiaomi Water Purifier (Yunmi)."""
import logging
from functools import partial

from homeassistant.const import *
from homeassistant.helpers.entity import Entity
from miio.waterpurifier_yunmi import WaterPurifierYunmi

from . import (
    DOMAIN,
    CONF_MODEL,
    PLATFORM_SCHEMA,
    MiioEntity,
    BaseSubEntity,
    DeviceException,
    bind_services_to_entries,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'sensor.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    config = hass.data[DOMAIN]['configs'].get(config_entry.entry_id, dict(config_entry.data))
    await async_setup_platform(hass, config, async_add_entities)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    config.setdefault('add_entities', {})
    config['add_entities']['sensor'] = async_add_entities
    model = str(config.get(CONF_MODEL) or '')
    entities = []
    if model.find('waterpuri') >= 0:
        entity = WaterPurifierYunmiEntity(config)
        entities.append(entity)
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class WaterPurifierYunmiEntity(MiioEntity, Entity):
    def __init__(self, config):
        name = config[CONF_NAME]
        host = config[CONF_HOST]
        token = config[CONF_TOKEN]
        _LOGGER.info('Initializing with host %s (token %s...)', host, token[:5])

        self._device = WaterPurifierYunmi(host, token)
        self._add_entities = config.get('add_entities')
        super().__init__(name, self._device)
        self._state_attrs.update({'entity_class': self.__class__.__name__})
        self._subs = {
            'tds_in':  {'keys': ['tds_warn_thd'], 'unit': CONCENTRATION_PARTS_PER_MILLION, 'icon': 'mdi:water'},
            'tds_out': {'keys': ['tds_warn_thd'], 'unit': CONCENTRATION_PARTS_PER_MILLION, 'icon': 'mdi:water-check'},
            'temperature': {'class': DEVICE_CLASS_TEMPERATURE, 'unit': TEMP_CELSIUS},
        }
        for i in [1, 2, 3]:
            self._subs.update({
                f'f{i}_remaining': {
                    'keys': [f'f{i}_totalflow', f'f{i}_usedflow'],
                    'unit': PERCENTAGE,
                    'icon': 'mdi:water-percent',
                },
                f'f{i}_remain_days': {
                    'keys': [f'f{i}_totaltime', f'f{i}_usedtime'],
                    'unit': TIME_DAYS,
                    'icon': 'mdi:clock',
                },
            })

    @property
    def state(self):
        return self._state

    @property
    def icon(self):
        return 'mdi:water-pump'

    @property
    def unit_of_measurement(self):
        return CONCENTRATION_PARTS_PER_MILLION

    async def async_update(self):
        try:
            status = await self.hass.async_add_executor_job(partial(self._device.status))
        except DeviceException as ex:
            if self._available:
                self._available = False
                _LOGGER.error('Got exception while fetching the state for %s: %s', self.entity_id, ex)
            return
        attrs = status.data or {}
        _LOGGER.debug('Got new state from %s: %s', self.entity_id, attrs)
        self._available = True
        self._state = int(attrs.get('tds_out', 0))
        self._state_attrs.update(attrs)
        for i in [1, 2, 3]:
            self._state_attrs.update({
                f'f{i}_remaining':   round(100 - 100 * attrs[f'f{i}_usedtime'] / attrs[f'f{i}_totaltime']),
                f'f{i}_remain_days': round((attrs[f'f{i}_totaltime'] - attrs[f'f{i}_usedtime']) / 24),
            })
        self._state_attrs.update({
            'errors': '|'.join(status.operation_status.errors),
        })
        add_entities = self._add_entities.get('sensor', None)
        for k, v in self._subs.items():
            if 'entity' in v:
                v['entity'].update()
            elif add_entities:
                v['entity'] = WaterPurifierYunmiSubEntity(self, k, v)
                add_entities([v['entity']])


class WaterPurifierYunmiSubEntity(BaseSubEntity):
    def __init__(self, parent: WaterPurifierYunmiEntity, attr, option=None):
        super().__init__(parent, attr, option)
