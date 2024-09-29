"""Support button entity for Xiaomi Miot."""
import logging

from homeassistant.components.button import (
    DOMAIN as ENTITY_DOMAIN,
    ButtonEntity as BaseEntity,
)

from . import (
    DOMAIN,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    MiotPropertySubEntity,
    BaseSubEntity,
    async_setup_config_entry,
)
from .core.miot_spec import (
    MiotProperty,
    MiotAction,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    HassEntry.init(hass, config_entry).new_adder(ENTITY_DOMAIN, async_add_entities)
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})


class ButtonEntity(XEntity, BaseEntity):
    def on_init(self):
        self._attr_available = True
        if des := getattr(self.conv, 'description', None):
            self._attr_name = f'{self._attr_name} {des}'

    def set_state(self, data: dict):
        pass

    async def async_press(self):
        pms = getattr(self.conv, 'value', None)
        if self._miot_action and self._miot_action.ins:
            pms = self.custom_config_list('action_params', pms)
        await self.device.async_write({self.attr: pms})

XEntity.CLS[ENTITY_DOMAIN] = ButtonEntity


class MiotButtonSubEntity(MiotPropertySubEntity, BaseEntity):
    def __init__(self, parent, miot_property: MiotProperty, value, option=None):
        super().__init__(parent, miot_property, option, domain=ENTITY_DOMAIN)
        self._miot_property_value = value
        self._miot_property_desc = None
        if miot_property.value_list:
            self._miot_property_desc = miot_property.list_description(value)
        if self._miot_property_desc is None:
            self._miot_property_desc = value
        self._name = f'{self._name} {self._miot_property_desc}'.strip()
        self.entity_id = f'{self.entity_id}_{self._miot_property_value}'.strip()
        self._unique_id = f'{self._unique_id}-value{self._miot_property_value}'.strip()
        self._extra_attrs.update({
            'property_value': self._miot_property_value,
            'value_description': self._miot_property_desc,
        })
        self._available = True

    def update(self, data=None):
        if data:
            self.update_attrs(data, update_parent=False)

    def press(self):
        """Press the button."""
        return self.set_parent_property(self._miot_property_value)


class MiotButtonActionSubEntity(BaseSubEntity, BaseEntity):
    def __init__(self, parent, miot_action: MiotAction, option=None):
        self._miot_action = miot_action
        super().__init__(parent, miot_action.full_name, option, domain=ENTITY_DOMAIN)
        self._name = f'{parent.device_name} {miot_action.friendly_desc}'.strip()
        self._unique_id = f'{parent.unique_did}-{miot_action.unique_name}'
        self.entity_id = miot_action.service.spec.generate_entity_id(self, miot_action.name)
        self._extra_attrs.update({
            'service_description': miot_action.service.description,
            'action_description': miot_action.description,
        })
        self._available = True

    def update(self, data=None):
        if data:
            self.update_attrs(data, update_parent=False)

    def press(self):
        """Press the button."""
        pms = []
        for pid in self._miot_action.ins:
            prop = self._miot_action.service.properties.get(pid)
            val = self.custom_config(prop.name)
            if prop.is_integer and val is not None:
                val = int(val)
            pms.append(val)
        return self.call_parent('call_action', self._miot_action, pms)


class ButtonSubEntity(BaseEntity, BaseSubEntity):
    def __init__(self, parent, attr, option=None):
        BaseSubEntity.__init__(self, parent, attr, option)
        self._available = True
        self._press_action = self._option.get('press_action')
        self._press_kwargs = self._option.get('press_kwargs') or {}
        self._state_attrs = self._option.get('state_attrs') or {}

    def update(self, data=None):
        return

    def press(self):
        """Press the button."""
        if not self._press_action:
            raise NotImplementedError()
        kws = {
            'attr': self._attr,
            **self._press_kwargs,
        }
        if ret := self._press_action(**kws):
            self.schedule_update_ha_state()
        return ret
