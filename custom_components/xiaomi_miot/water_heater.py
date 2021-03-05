"""Support for Xiaomi water heaters."""
import logging

from homeassistant.const import *
from homeassistant.components.water_heater import (
    DOMAIN as ENTITY_DOMAIN,
    WaterHeaterEntity,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_OPERATION_MODE,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
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
        for srv in spec.get_services(ENTITY_DOMAIN):
            if not srv.get_property('mode', 'target_temperature'):
                continue
            cfg = {
                **config,
                'name': f"{config.get('name')} {srv.description}"
            }
            entities.append(MiotWaterHeaterEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotWaterHeaterEntity(MiotToggleEntity, WaterHeaterEntity):
    def __init__(self, config, miot_service: MiotService, **kwargs):
        name = config[CONF_NAME]
        host = config[CONF_HOST]
        token = config[CONF_TOKEN]

        self._miot_service = miot_service
        mapping = dict(kwargs.get('mapping') or {})
        mapping.update(miot_service.mapping())
        self._device = MiotDevice(mapping, host, token)
        _LOGGER.info('Initializing %s (%s, token %s...), miot mapping: %s', name, host, token[:5], mapping)

        super().__init__(name, self._device, miot_service, config=config)
        self._add_entities = config.get('add_entities') or {}

        self._prop_status = miot_service.get_property('status')
        self._prop_mode = miot_service.get_property('mode')
        self._prop_modes = miot_service.get_properties('mode', 'water_level')
        self._prop_temperature = miot_service.get_property('temperature', 'indoor_temperature')
        self._prop_target_temp = miot_service.get_property('target_temperature')
        self._prev_target_temp = None

        if self._prop_target_temp:
            self._supported_features |= SUPPORT_TARGET_TEMPERATURE
        if self._prop_modes:
            self._supported_features |= SUPPORT_OPERATION_MODE

        self._state_attrs.update({'entity_class': self.__class__.__name__})

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        if self._prop_power:
            if not self._prop_power.readable and self._prop_status:
                # https://github.com/al-one/hass-xiaomi-miot/issues/30
                val = self._prop_status.from_dict(self._state_attrs)
                if val is not None:
                    off = val in self._prop_status.list_search('Off')
                    self.update_attrs({
                        self._prop_power.full_name: not off,
                    })
            self._update_sub_entities(self._prop_power.name)

    @property
    def state(self):
        """Return the current state."""
        sta = self.current_operation
        mds = []
        if self._prop_mode:
            mds = self._prop_mode.list_descriptions()
        if sta is None or sta not in mds:
            if self._prop_status:
                val = self._prop_status.from_dict(self._state_attrs)
                if val is not None:
                    sta = self._prop_status.list_description(val)
        if sta is None and self._prop_power and self._prop_power.readable:
            sta = STATE_ON if self._prop_power.from_dict(self._state_attrs) else STATE_OFF
        if sta:
            sta = str(sta).lower()
        return sta

    @property
    def current_operation(self):
        """Return current operation ie. eco, electric, performance, ..."""
        for p in self._prop_modes:
            val = p.from_dict(self._state_attrs)
            if val is not None:
                return p.list_description(val)
        return None

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        for p in self._prop_modes:
            return p.list_descriptions() or []
        return None

    def set_operation_mode(self, mode):
        """Set new target operation mode."""
        for p in self._prop_modes:
            val = p.list_value(mode)
            return self.set_property(p.full_name, val)
        raise NotImplementedError()

    @property
    def current_temperature(self):
        """Return the current temperature."""
        if self._prop_temperature:
            return self._prop_temperature.from_dict(self._state_attrs)
        return None

    @property
    def temperature_unit(self):
        prop = self._prop_temperature or self._prop_target_temp
        if prop:
            if prop.unit in ['celsius', TEMP_CELSIUS]:
                return TEMP_CELSIUS
            if prop.unit in ['fahrenheit', TEMP_FAHRENHEIT]:
                return TEMP_FAHRENHEIT
            if prop.unit in ['kelvin', TEMP_KELVIN]:
                return TEMP_KELVIN
        return TEMP_CELSIUS

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        if self._prop_target_temp:
            val = kwargs.get(ATTR_TEMPERATURE)
            ret = self.set_property(self._prop_target_temp.full_name, val)
            if ret:
                self._prev_target_temp = val
            return ret
        raise NotImplementedError()

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if self._prop_target_temp:
            val = float(self._prop_target_temp.from_dict(self._state_attrs) or 0)
            if val:
                self._prev_target_temp = val
            elif self._prev_target_temp:
                val = self._prev_target_temp
            return val
        return None

    @property
    def target_temperature_high(self):
        """Return the highbound target temperature we try to reach."""
        if self._prop_target_temp:
            return self._prop_target_temp.range_max()
        return None

    @property
    def target_temperature_low(self):
        """Return the lowbound target temperature we try to reach."""
        if self._prop_target_temp:
            return self._prop_target_temp.range_min()
        return None

    @property
    def is_away_mode_on(self):
        """Return true if away mode is on."""
        return None

    def turn_away_mode_on(self):
        """Turn away mode on."""
        raise NotImplementedError()

    def turn_away_mode_off(self):
        """Turn away mode off."""
        raise NotImplementedError()
