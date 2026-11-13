"""Coordinator for the CDDZ PC03W boot card integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    DURATION_BITS,
    KEY_BITS,
    POLL_PROPERTIES,
    PROP_DURATION_BITS,
    PROP_KEY_BITS,
    PROP_PC_NUMBER,
    PROP_SETTING_BITS,
    SETTING_BITS,
    extract_bits,
    set_bits,
)

_LOGGER = logging.getLogger(__name__)


class CddzCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the raw MIoT properties used by the vendor plugin."""

    def __init__(self, hass: HomeAssistant, device: Any) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.device = device

    async def _async_update_data(self) -> dict[str, Any]:
        if self.device is None:
            raise UpdateFailed("未找到对应的 Xiaomi Miot 设备")

        try:
            raw = await self.device.async_get_properties(
                POLL_PROPERTIES,
                update_entity=False,
                throw=True,
            )
        except Exception as exc:
            raise UpdateFailed(f"读取设备属性失败: {exc}") from exc

        if not isinstance(raw, dict) or raw.get("error"):
            raise UpdateFailed(f"读取设备属性失败: {raw}")

        data: dict[str, Any] = {
            "switch": raw.get("switch.on"),
            "config": raw.get("function.config"),
            "pc_number": raw.get("function.number"),
            "pc_state": raw.get("function.state"),
            "key_bits": raw.get("function.data_a"),
            "setting_bits": raw.get("function.data_b"),
            "duration_bits": raw.get("function.data_c"),
            "uptime": raw.get("time", raw.get("time.time")),
            "open_time_set": raw.get("setting.open_time_set"),
        }

        # Keep the last known value if a property was not returned.
        for key, value in data.items():
            if value is None and self.data:
                data[key] = self.data.get(key)

        if data["pc_state"] is None:
            raise UpdateFailed("设备未返回电脑状态 (7.3)")

        data["setting_bits"] = int(data.get("setting_bits") or 0)
        data["key_bits"] = int(data.get("key_bits") or 0)
        data["duration_bits"] = int(data.get("duration_bits") or 0)
        data["settings"] = {
            field: extract_bits(data["setting_bits"], msb, length)
            for field, (msb, length) in SETTING_BITS.items()
        }
        data["keys"] = {
            field: extract_bits(data["key_bits"], msb, length)
            for field, (msb, length) in KEY_BITS.items()
        }
        data["durations"] = {
            field: extract_bits(data["duration_bits"], msb, length)
            for field, (msb, length) in DURATION_BITS.items()
        }
        data["pc_on"] = data["pc_state"] in (0, 1)
        data["pc_off"] = data["pc_state"] in (2, 3)
        return data

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def async_send_ctrl(self, value: int) -> None:
        """Send a setting.ctrl command (siid 6, aiid 1)."""
        result = await self.device.async_call_action(6, 1, [int(value)])
        if not result or not getattr(result, "is_success", False):
            error = getattr(result, "error", None) or result
            raise HomeAssistantError(f"发送控制指令失败: {error}")
        _LOGGER.info("Sent PC03W ctrl command 0x%08X", value)
        self._schedule_cddz_refresh(3)

    async def async_set_setting(self, field: str, value: int) -> None:
        """Update one bit field inside function.data_b (7.5)."""
        msb, length = SETTING_BITS[field]
        new_bits = set_bits(int(self.data["setting_bits"]), msb, length, value)
        await self._write_property(PROP_SETTING_BITS, new_bits, "setting_bits")
        self.data["settings"][field] = int(value)
        self.async_set_updated_data(self.data)

    async def async_set_duration(self, field: str, raw_value: int) -> None:
        """Update one press-duration field inside function.data_c (7.6)."""
        msb, length = DURATION_BITS[field]
        new_bits = set_bits(int(self.data["duration_bits"]), msb, length, raw_value)
        await self._write_property(PROP_DURATION_BITS, new_bits, "duration_bits")
        self.data["durations"][field] = int(raw_value)
        self.async_set_updated_data(self.data)

    async def async_set_key_mode(self, field: str, value: int) -> None:
        """Update one key-mode field inside function.data_a (7.4)."""
        msb, length = KEY_BITS[field]
        new_bits = set_bits(int(self.data["key_bits"]), msb, length, value)
        await self._write_property(PROP_KEY_BITS, new_bits, "key_bits")
        self.data["keys"][field] = int(value)
        self.async_set_updated_data(self.data)

    async def async_set_pc_number(self, value: int) -> None:
        """Set the PC number (7.2)."""
        await self._write_property(PROP_PC_NUMBER, int(value), "pc_number")

    async def _write_property(self, prop: dict[str, int], value: int, data_key: str) -> None:
        result = await self.device.async_set_miot_property(
            prop["siid"], prop["piid"], int(value)
        )
        if not result or not getattr(result, "is_success", False):
            error = getattr(result, "error", None) or result
            raise HomeAssistantError(f"写入设备属性失败: {error}")
        self.data[data_key] = int(value)
        self._schedule_cddz_refresh(2)

    def _schedule_cddz_refresh(self, delay: int) -> None:
        async def _later() -> None:
            await asyncio.sleep(delay)
            await self.async_request_refresh()

        self.hass.async_create_task(_later())
