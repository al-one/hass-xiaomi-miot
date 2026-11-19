"""Sensors for the CDDZ PC03W boot card integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONFIG_BITS,
    DOMAIN,
    STATE_LABELS,
    extract_bits,
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
            PcStateSensor(coordinator),
            PcUptimeSensor(coordinator),
            OpenTimeSetSensor(coordinator),
            FeatureConfigSensor(coordinator),
        ]
    )


class PcStateSensor(CddzEntity, SensorEntity):
    """Current PC state as reported by the boot card."""

    _attr_name = "电脑状态"
    _attr_icon = "mdi:desktop-tower"

    def __init__(self, coordinator: CddzCoordinator) -> None:
        super().__init__(coordinator, "pc_state")

    @property
    def native_value(self) -> str | None:
        state = self.pc_state
        if state is None:
            return None
        return STATE_LABELS.get(state, f"未知 ({state})")

    @property
    def extra_state_attributes(self) -> dict[str, int | bool | None]:
        return {
            "state_code": self.pc_state,
            "is_on": self.is_pc_on,
        }


class PcUptimeSensor(CddzEntity, SensorEntity):
    """Raw MIoT 9.1 value, used by the vendor app for its boot statistics chart.

    This is *not* a cumulative uptime.  The official plugin reads history for 9.1
    and divides each reported delta by 60 to draw minutes per hour/day.
    """

    _attr_name = "开机统计原始值"
    _attr_icon = "mdi:chart-line"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "s"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CddzCoordinator) -> None:
        super().__init__(coordinator, "uptime")

    @property
    def native_value(self) -> int | None:
        return self.boot_stat_raw

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {
            "note": "设备上报的 9.1 原始值；官方插件用它做开机统计图表，不是累计开机时长。实际开机时长可用 sensor.192_168_2_2_uptime。"
        }


class OpenTimeSetSensor(CddzEntity, SensorEntity):
    """On-time reminder setting (MIoT 6.3, minutes)."""

    _attr_name = "开机提醒设置"
    _attr_icon = "mdi:clock-alert-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "min"

    def __init__(self, coordinator: CddzCoordinator) -> None:
        super().__init__(coordinator, "open_time_set")

    @property
    def native_value(self) -> int | None:
        value = self.open_time_set
        if value is None or value == 0xFFFFFFFF:
            return None
        return value

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        return {"raw": self.open_time_set}


class FeatureConfigSensor(CddzEntity, SensorEntity):
    """Decoded feature flags from function.config (7.1)."""

    _attr_name = "设备功能配置"
    _attr_icon = "mdi:information-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CddzCoordinator) -> None:
        super().__init__(coordinator, "config")

    @property
    def native_value(self) -> str:
        return f"0x{self.config:08X}"

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        return {
            name: extract_bits(self.config, msb, length)
            for name, (msb, length) in CONFIG_BITS.items()
        }
