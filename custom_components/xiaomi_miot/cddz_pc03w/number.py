"""Number entities for the CDDZ PC03W boot card integration."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
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
    async_add_entities(
        [
            PcNumberEntity(coordinator),
            HibernateIntervalNumber(coordinator),
            DurationNumber(coordinator, "on_duration", "开机按键时长"),
            DurationNumber(coordinator, "off_duration", "关机按键时长"),
            DurationNumber(coordinator, "restart_duration", "重启按键时长"),
            DurationNumber(coordinator, "force_off_duration", "强制关机按键时长"),
        ]
    )


class PcNumberEntity(CddzEntity, NumberEntity):
    """PC number stored in function.number (7.2)."""

    _attr_name = "电脑编号"
    _attr_icon = "mdi:counter"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 255
    _attr_native_step = 1
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: CddzCoordinator) -> None:
        super().__init__(coordinator, "pc_number")

    @property
    def native_value(self) -> int:
        return self.pc_number

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_pc_number(int(value))


class HibernateIntervalNumber(CddzEntity, NumberEntity):
    """Sleep-detection interval in seconds (7.5 bits 15..8, 0.5 s units)."""

    _attr_name = "休眠检测间隔"
    _attr_icon = "mdi:timer-sand"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_native_min_value = 0
    _attr_native_max_value = 60
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: CddzCoordinator) -> None:
        super().__init__(coordinator, "hibernate_interval")

    @property
    def native_value(self) -> float:
        return int(self.setting.get("hibernate_interval", 0)) / 2

    async def async_set_native_value(self, value: float) -> None:
        raw = max(0, min(255, round(value * 2)))
        await self.coordinator.async_set_setting("hibernate_interval", raw)


class DurationNumber(CddzEntity, NumberEntity):
    """A press duration in seconds (7.6, 0.5 s units)."""

    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_native_min_value = 0
    _attr_native_max_value = 60
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:timer-outline"

    def __init__(
        self,
        coordinator: CddzCoordinator,
        field: str,
        name: str,
    ) -> None:
        super().__init__(coordinator, f"duration_{field}")
        self._field = field
        self._attr_name = name

    @property
    def native_value(self) -> float:
        return int(self.duration.get(self._field, 0)) / 2

    async def async_set_native_value(self, value: float) -> None:
        raw = max(1, min(120, round(value * 2)))
        await self.coordinator.async_set_duration(self._field, raw)
