"""Binary sensors for the CDDZ PC03W boot card integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CddzCoordinator
from .entity import CddzEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CddzCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PcPoweredBinarySensor(coordinator)])


class PcPoweredBinarySensor(CddzEntity, BinarySensorEntity):
    """Whether the PC is powered on (including the power-on transition)."""

    _attr_name = "电脑已开机"
    _attr_icon = "mdi:desktop-tower-monitor"
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator: CddzCoordinator) -> None:
        super().__init__(coordinator, "pc_powered")

    @property
    def is_on(self) -> bool:
        return self.is_pc_on
