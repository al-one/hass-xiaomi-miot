"""Buttons for the CDDZ PC03W boot card integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_FORCE_OFF,
    CMD_FORCE_RESTART,
    CMD_RESTART,
    DOMAIN,
    STATE_ON,
)
from .coordinator import CddzCoordinator
from .entity import CddzEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CddzCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            CddzCommandButton(
                coordinator,
                "restart",
                "重启",
                "mdi:restart",
                CMD_RESTART,
            ),
            CddzCommandButton(
                coordinator,
                "force_restart",
                "强制重启",
                "mdi:restart-alert",
                CMD_FORCE_RESTART,
                enabled_default=False,
            ),
            CddzCommandButton(
                coordinator,
                "force_off",
                "强制关机",
                "mdi:power-off",
                CMD_FORCE_OFF,
                enabled_default=False,
            ),
        ]
    )


class CddzCommandButton(CddzEntity, ButtonEntity):
    """A setting.ctrl command exposed as a button."""

    def __init__(
        self,
        coordinator: CddzCoordinator,
        key: str,
        name: str,
        icon: str,
        command: int,
        enabled_default: bool = True,
    ) -> None:
        super().__init__(coordinator, f"button_{key}")
        self._attr_name = name
        self._attr_icon = icon
        self._command = command
        self._attr_entity_registry_enabled_default = enabled_default

    @property
    def available(self) -> bool:
        # Restart / force commands only make sense while the PC is fully on.
        return super().available and self.pc_state == STATE_ON

    async def async_press(self) -> None:
        await self.coordinator.async_send_ctrl(self._command)
