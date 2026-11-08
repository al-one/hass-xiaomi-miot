"""Base entity for the CDDZ PC03W boot card integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import CddzCoordinator


class CddzEntity(CoordinatorEntity[CddzCoordinator]):
    """Base class for all PC03W entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CddzCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device.unique_id}_{key}"

    @property
    def device_info(self) -> dict:
        return self.coordinator.device.hass_device_info

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def pc_state(self) -> int | None:
        """Return function.state (7.3)."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("pc_state")

    @property
    def is_pc_on(self) -> bool:
        return self.pc_state in (0, 1)

    @property
    def is_pc_off(self) -> bool:
        return self.pc_state in (2, 3)

    @property
    def setting(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("settings", {})

    @property
    def key_setting(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("keys", {})

    @property
    def duration(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("durations", {})

    @property
    def pc_number(self) -> int:
        return int((self.coordinator.data or {}).get("pc_number") or 0)

    @property
    def boot_stat_raw(self) -> int | None:
        """Return the raw MIoT 9.1 value (used by the vendor's boot statistics)."""
        value = (self.coordinator.data or {}).get("uptime")
        return None if value is None else int(value)

    @property
    def open_time_set(self) -> int | None:
        value = (self.coordinator.data or {}).get("open_time_set")
        return None if value is None else int(value)

    @property
    def config(self) -> int:
        return int((self.coordinator.data or {}).get("config") or 0)
