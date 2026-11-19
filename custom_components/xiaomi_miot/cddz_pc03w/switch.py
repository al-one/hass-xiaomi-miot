"""Switches for the CDDZ PC03W boot card integration."""

from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_POWER_OFF,
    CMD_POWER_ON,
    DOMAIN,
    STATE_LABELS,
    STATE_OFF,
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
            PcPowerSwitch(coordinator),
            SettingSwitch(
                coordinator,
                "child_lock",
                "机箱按钮童锁",
                "mdi:lock-outline",
            ),
            SettingSwitch(
                coordinator,
                "xa_voice",
                "小爱语音控制",
                "mdi:microphone",
            ),
            SettingSwitch(
                coordinator,
                "hibernate",
                "休眠关机",
                "mdi:sleep",
            ),
        ]
    )


class PcPowerSwitch(CddzEntity, SwitchEntity):
    """PC power, using the same ctrl commands as the Mi Home plugin."""

    _attr_name = "电脑电源"
    _attr_icon = "mdi:power"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: CddzCoordinator) -> None:
        super().__init__(coordinator, "power")

    @property
    def is_on(self) -> bool | None:
        state = self.pc_state
        if state == STATE_ON:
            return True
        if state == STATE_OFF:
            return False
        return None

    @property
    def extra_state_attributes(self) -> dict[str, int | str | None]:
        return {
            "state_code": self.pc_state,
            "state": STATE_LABELS.get(self.pc_state) if self.pc_state is not None else None,
        }

    async def async_turn_on(self, **kwargs) -> None:
        if self.pc_state != STATE_OFF:
            state = STATE_LABELS.get(self.pc_state, "未知")
            raise HomeAssistantError(
                f"电脑当前状态为“{state}”，不是“已关机”，已拒绝开机指令"
            )
        await self.coordinator.async_send_ctrl(CMD_POWER_ON)

    async def async_turn_off(self, **kwargs) -> None:
        if self.pc_state != STATE_ON:
            state = STATE_LABELS.get(self.pc_state, "未知")
            raise HomeAssistantError(
                f"电脑当前状态为“{state}”，不是“已开机”，已拒绝关机指令"
            )
        await self.coordinator.async_send_ctrl(CMD_POWER_OFF)


class SettingSwitch(CddzEntity, SwitchEntity):
    """A one-bit setting inside function.data_b (7.5)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: CddzCoordinator,
        field: str,
        name: str,
        icon: str,
        enabled_default: bool = True,
    ) -> None:
        super().__init__(coordinator, field)
        self._field = field
        self._attr_name = name
        self._attr_icon = icon
        self._attr_entity_registry_enabled_default = enabled_default

    @property
    def is_on(self) -> bool:
        return bool(self.setting.get(self._field, 0))

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_setting(self._field, 1)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_setting(self._field, 0)
