"""Select entities for the CDDZ PC03W boot card integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    INDICATOR_LIGHT_OPTIONS,
    KEY_FEATURE_OPTIONS,
    POWER_ON_STATE_OPTIONS,
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
            IndicatorLightSelect(coordinator),
            PowerOnStateSelect(coordinator),
            KeyModeSelect(
                coordinator,
                "single_click_mode",
                "单击功能",
                "single",
                enabled_default=False,
            ),
            KeyModeSelect(
                coordinator,
                "double_click_mode",
                "双击功能",
                "double",
                enabled_default=False,
            ),
            KeyModeSelect(
                coordinator,
                "long_press_mode",
                "长按功能",
                "long",
                enabled_default=False,
            ),
        ]
    )


class SettingSelect(CddzEntity, SelectEntity):
    """Base class for a byte-sized setting inside function.data_b (7.5)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: CddzCoordinator,
        field: str,
        name: str,
        icon: str,
        options: dict[int, str],
    ) -> None:
        super().__init__(coordinator, field)
        self._field = field
        self._attr_name = name
        self._attr_icon = icon
        self._options = options
        self._attr_options = list(options.values())

    def _value(self) -> int:
        return int(self.setting.get(self._field, 0))

    @property
    def current_option(self) -> str | None:
        return self._options.get(self._value())

    async def async_select_option(self, option: str) -> None:
        for value, label in self._options.items():
            if label == option:
                await self.coordinator.async_set_setting(self._field, value)
                return
        raise ValueError(f"未知选项: {option}")


class IndicatorLightSelect(SettingSelect):
    """Indicator light mode (follow / always on / always off)."""

    def __init__(self, coordinator: CddzCoordinator) -> None:
        super().__init__(
            coordinator,
            "indicator_light",
            "指示灯模式",
            "mdi:lightbulb-outline",
            INDICATOR_LIGHT_OPTIONS,
        )


class PowerOnStateSelect(SettingSelect):
    """Behavior after mains power returns (off / on / remember)."""

    def __init__(self, coordinator: CddzCoordinator) -> None:
        super().__init__(
            coordinator,
            "power_on_state",
            "上电状态",
            "mdi:power-plug-outline",
            POWER_ON_STATE_OPTIONS,
        )


class KeyModeSelect(CddzEntity, SelectEntity):
    """A key-mode field inside function.data_a (7.4)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: CddzCoordinator,
        field: str,
        name: str,
        key: str,
        enabled_default: bool = True,
    ) -> None:
        super().__init__(coordinator, f"key_{key}")
        self._field = field
        self._attr_name = name
        self._attr_icon = "mdi:remote"
        self._attr_options = list(KEY_FEATURE_OPTIONS.values())
        self._attr_entity_registry_enabled_default = enabled_default

    @property
    def current_option(self) -> str | None:
        return KEY_FEATURE_OPTIONS.get(int(self.key_setting.get(self._field, 0)))

    async def async_select_option(self, option: str) -> None:
        for value, label in KEY_FEATURE_OPTIONS.items():
            if label == option:
                await self.coordinator.async_set_key_mode(self._field, value)
                return
        raise ValueError(f"未知选项: {option}")
