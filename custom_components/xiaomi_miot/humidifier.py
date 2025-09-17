"""Support for humidifier and dehumidifier."""
import logging
from bisect import bisect

from homeassistant.components.humidifier import (
    DOMAIN as ENTITY_DOMAIN,
    HumidifierEntity as BaseEntity,
    HumidifierEntityFeature,  # v2022.5
    HumidifierDeviceClass,
)

from . import (
    DOMAIN,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import MiotProperty

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
MODE_OFF = 'Off'


async def async_setup_entry(hass, config_entry, async_add_entities):
    HassEntry.init(hass, config_entry).new_adder(ENTITY_DOMAIN, async_add_entities)
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    bind_services_to_entries(hass, {})


class HumidifierEntity(XEntity, BaseEntity):
    _attr_mode = None
    _attr_available_modes = None
    _conv_power = None
    _conv_mode = None
    _conv_target_humidity = None
    _conv_current_humidity = None
    _target_humidity_ratio = 1
    _target_humidity_step = None

    def on_init(self):
        self._attr_available_modes = []
        self._target_humidity_ratio = self.custom_config_number('target_humidity_ratio', 1)

        for attr in self.conv.attrs:
            conv = self.device.find_converter(attr)
            prop = getattr(conv, 'prop', None) if conv else None
            if not isinstance(prop, MiotProperty):
                continue
            elif prop.in_list(['on']):
                self._conv_power = conv
                self._attr_available_modes.append(MODE_OFF)
                self._attr_supported_features |= HumidifierEntityFeature.MODES
            elif prop.in_list(['mode', 'fan_level']) and not self._conv_mode:
                self._conv_mode = conv
                self._attr_available_modes.extend(prop.list_descriptions())
                self._attr_supported_features |= HumidifierEntityFeature.MODES
            elif prop.in_list(['relative_humidity', 'humidity']):
                self._conv_current_humidity = conv
            elif prop.in_list(['target_humidity']):
                self._conv_target_humidity = conv
                if prop.value_range:
                    self._attr_min_humidity = prop.range_min()
                    self._attr_max_humidity = prop.range_max()
                    self._target_humidity_step = prop.range_step()
                elif prop.value_list:
                    vls = prop.list_value(None)
                    vls.sort()
                    self._attr_min_humidity = vls[0]
                    self._attr_max_humidity = vls[-1]
                if self._target_humidity_ratio:
                    self._attr_min_humidity = round(self._attr_min_humidity * self._target_humidity_ratio)
                    self._attr_max_humidity = round(self._attr_max_humidity * self._target_humidity_ratio)

        typ = f'{self.model} {self._miot_service.spec.type}'
        if 'dehumidifier' in typ or '.derh.' in typ:
            self._attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER
        else:
            self._attr_device_class = HumidifierDeviceClass.HUMIDIFIER

    def set_state(self, data: dict):
        if self._conv_mode:
            val = self._conv_mode.value_from_dict(data)
            if val is not None:
                self._attr_mode = val
        if self._conv_power:
            val = self._conv_power.value_from_dict(data)
            if val is not None:
                self._attr_is_on = bool(val)
                if not self._attr_is_on:
                    self._attr_mode = MODE_OFF
        if self._conv_target_humidity:
            val = self._conv_target_humidity.value_from_dict(data)
            if val is not None:
                self._attr_target_humidity = round(val * self._target_humidity_ratio)
        if self._conv_current_humidity:
            val = self._conv_current_humidity.value_from_dict(data)
            if val is not None:
                self._attr_current_humidity = val

    async def async_turn_on(self):
        if not self._conv_power:
            return
        await self.device.async_write({self._conv_power.full_name: True})

    async def async_turn_off(self):
        if not self._conv_power:
            return
        await self.device.async_write({self._conv_power.full_name: False})

    async def async_set_mode(self, mode: str):
        if mode == MODE_OFF:
            await self.async_turn_off()
            return
        data = {}
        if not self._attr_is_on and self._conv_power:
            data[self._conv_power.full_name] = True
        if self._conv_mode:
            data[self._conv_mode.full_name] = mode
        if data:
            await self.device.async_write(data)

    async def async_set_humidity(self, humidity: int):
        if not self._conv_target_humidity:
            return
        data = {}
        if not self._attr_is_on and self._conv_power:
            data[self._conv_power.full_name] = True

        prop = getattr(self._conv_target_humidity, 'prop', None)
        if self._target_humidity_step:
            humidity = round(humidity / self._target_humidity_step) * self._target_humidity_step
        elif prop and prop.value_list:
            vls = prop.list_value(None)
            vls.sort()
            idx = bisect(vls, humidity)
            humidity = vls[idx - 1] if idx > 0 else vls[0]
        if self._target_humidity_ratio:
            humidity = round(humidity / self._target_humidity_ratio)

        data[self._conv_target_humidity.full_name] = humidity
        await self.device.async_write(data)


XEntity.CLS[ENTITY_DOMAIN] = HumidifierEntity
