"""Support for humidifier and dehumidifier."""
import logging

from homeassistant.const import *  # noqa: F401
from homeassistant.components.humidifier import (
    DOMAIN as ENTITY_DOMAIN,
    HumidifierEntity,
)
from homeassistant.components.humidifier.const import *

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotToggleEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)
from .fan import MiotModesSubEntity

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
MODE_OFF = 'Off'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
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


class MiotHumidifierEntity(MiotToggleEntity, HumidifierEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config)

        self._prop_power = miot_service.get_property('on')
        self._prop_mode = miot_service.get_property('mode')
        self._prop_fan_level = miot_service.get_property('fan_level')
        self._prop_water_level = miot_service.get_property('water_level')
        self._prop_target_humi = miot_service.get_property('target_humidity')
        self._prop_temperature = miot_service.get_property('temperature')
        self._prop_humidity = miot_service.get_property('relative_humidity', 'humidity')
        self._environment = miot_service.spec.get_service('environment')
        if self._environment:
            self._prop_temperature = self._environment.get_property('temperature') or self._prop_temperature
            self._prop_humidity = self._environment.get_property('relative_humidity', 'humidity') or self._prop_humidity

        if self._prop_mode or self._prop_fan_level or self._prop_water_level:
            self._supported_features = SUPPORT_MODES

        self._state_attrs.update({'entity_class': self.__class__.__name__})

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        add_fans = self._add_entities.get('fan')
        humidifier_mode = None
        for p in [self._prop_mode, self._prop_fan_level, self._prop_water_level]:
            if not p:
                continue
            if not humidifier_mode:
                humidifier_mode = p
                continue
            if p.name in self._subs:
                self._subs[p.name].update()
            elif add_fans:
                self._subs[p.name] = MiotModesSubEntity(self, p)
                add_fans([self._subs[p.name]])

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
            num = round(humidity / stp) * stp
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
        if self._prop_mode:
            val = self._prop_mode.from_dict(self._state_attrs)
            if val is not None:
                return self._prop_mode.list_description(val)
        if self._prop_fan_level:
            val = self._prop_fan_level.from_dict(self._state_attrs)
            if val is not None:
                return self._prop_fan_level.list_description(val)
        if self._prop_water_level:
            val = self._prop_water_level.from_dict(self._state_attrs)
            if val is not None:
                return self._prop_water_level.list_description(val)
        return None

    @property
    def available_modes(self):
        mds = [MODE_OFF]
        if self._prop_mode:
            mds.extend(self._prop_mode.list_description(None) or [])
        elif self._prop_fan_level:
            mds.extend(self._prop_fan_level.list_description(None) or [])
        elif self._prop_water_level:
            mds.extend(self._prop_water_level.list_description(None) or [])
        return mds

    def set_mode(self, mode: str):
        if mode == MODE_OFF:
            return self.turn_off()
        if self._prop_mode:
            val = self._prop_mode.list_value(mode)
            return self.set_property(self._prop_mode.full_name, val)
        if self._prop_fan_level:
            val = self._prop_fan_level.list_value(mode)
            return self.set_property(self._prop_fan_level.full_name, val)
        if self._prop_water_level:
            val = self._prop_water_level.list_value(mode)
            return self.set_property(self._prop_water_level.full_name, val)
        return False
