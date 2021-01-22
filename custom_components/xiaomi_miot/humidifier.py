"""Support for humidifier and dehumidifier."""
import logging
from enum import Enum

from homeassistant.const import *
from homeassistant.components.humidifier import (
    DOMAIN as ENTITY_DOMAIN,
    HumidifierEntity,
)
from homeassistant.components.humidifier.const import *

from . import (
    DOMAIN,
    CONF_MODEL,
    MiotDevice,
    MiotToggleEntity,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
MODE_OFF = 'Off'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    config = hass.data[DOMAIN]['configs'].get(config_entry.entry_id, dict(config_entry.data))
    await async_setup_platform(hass, config, async_add_entities)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    config.setdefault('add_entities', {})
    config['add_entities'][ENTITY_DOMAIN] = async_add_entities
    model = str(config.get(CONF_MODEL) or '')
    entities = []
    miot = config.get('miot_type')
    if miot:
        spec = await MiotSpec.async_from_type(hass, miot)
        for srv in spec.get_services(ENTITY_DOMAIN, 'dehumidifier'):
            if not srv.get_property('on'):
                continue
            cfg = {
                **config,
                'name': f"{config.get('name')} {srv.description}"
            }
            entities.append(MiotHumidifierEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotDehumidifierModes(Enum):
    Off = -1
    TargetHumid = 0
    DryCloth = 1


class MiotHumidifierEntity(MiotToggleEntity, HumidifierEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        name = config[CONF_NAME]
        host = config[CONF_HOST]
        token = config[CONF_TOKEN]

        self._miot_service = miot_service
        mapping = miot_service.spec.services_mapping(
            ENTITY_DOMAIN, 'dehumidifier', 'environment', 'indicator_light',
            'function', 'alarm', 'physical_controls_locked', 'screen', 'others',
        )
        mapping.update(miot_service.mapping())
        _LOGGER.info('Initializing with host %s (token %s...), miot mapping: %s', host, token[:5], mapping)

        self._device = MiotDevice(host, token)
        super().__init__(name, self._device, miot_service)

        self._prop_power = miot_service.get_property('on')
        self._prop_mode = miot_service.get_property('mode')
        self._prop_fan_level = miot_service.get_property('fan_level')
        self._prop_water_level = miot_service.get_property('water_level')
        self._prop_target_humi = miot_service.get_property('target_humidity')
        self._prop_temperature = None
        self._prop_humidity = None
        self._environment = miot_service.spec.get_service('environment')
        if self._environment:
            self._prop_temperature = self._environment.get_property('temperature')
            self._prop_humidity = self._environment.get_property('relative_humidity', 'humidity')

        if self._prop_mode:
            self._supported_features = SUPPORT_MODES

        self._state_attrs.update({'entity_class': self.__class__.__name__})

    @property
    def device_class(self):
        typ = f'{self._model} {self._miot_service.spec.type}'
        if typ.find(DEVICE_CLASS_DEHUMIDIFIER) >= 0:
            return DEVICE_CLASS_DEHUMIDIFIER
        return DEVICE_CLASS_HUMIDIFIER

    @property
    def target_humidity(self):
        if self._prop_target_humi:
            return int(self._prop_target_humi.from_dict(self._state_attrs, 0))
        return None

    def set_humidity(self, humidity: int):
        if not self._prop_target_humi:
            return False
        num = humidity
        if self._prop_target_humi.value_range:
            stp = self._prop_target_humi.range_step()
            cur = self._prop_target_humi.range_min()
            rmx = self._prop_target_humi.range_max()
            num = cur
            while cur <= rmx and cur <= humidity:
                num = cur
                cur += stp
        elif self._prop_target_humi.value_list:
            num = None
            vls = self._prop_target_humi.list_value(None)
            vls.sort()
            for n in vls:
                if humidity >= n or num is None:
                    num = n
        if num is None:
            return False
        return self._device.set_property(self._prop_target_humi.full_name, num)

    @property
    def min_humidity(self):
        if self._prop_target_humi:
            return self._prop_target_humi.range_min()
        return None

    @property
    def max_humidity(self):
        if self._prop_target_humi:
            return self._prop_target_humi.range_max()
        return None

    @property
    def mode(self):
        if not self.is_on:
            return MODE_OFF
        if self._prop_fan_level:
            val = self._prop_fan_level.from_dict(self._state_attrs)
            if val is not None:
                return self._prop_fan_level.list_description(val)
        return None

    @property
    def available_modes(self):
        mds = [MODE_OFF]
        if self._prop_fan_level:
            mds.extend(self._prop_fan_level.list_description(None) or [])
        return mds

    def set_mode(self, mode: str):
        if mode == MODE_OFF:
            return self.turn_off()
        if self._prop_fan_level:
            val = self._prop_fan_level.list_value(mode)
            return self.set_property(self._prop_fan_level.full_name, val)
        return False
