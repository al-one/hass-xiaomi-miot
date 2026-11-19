"""Extra entities for cddz.plug.pc03w, injected into Xiaomi Miot platforms."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..core.hass_entry import HassEntry
from .const import DOMAIN, MODEL
from .coordinator import CddzCoordinator

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f"{DOMAIN}_data"


def _entities_for_domain(domain: str, coordinator: CddzCoordinator) -> list[Any]:
    if domain == "sensor":
        from .sensor import (
            FeatureConfigSensor,
            OpenTimeSetSensor,
            PcStateSensor,
            PcUptimeSensor,
        )

        return [
            PcStateSensor(coordinator),
            PcUptimeSensor(coordinator),
            OpenTimeSetSensor(coordinator),
            FeatureConfigSensor(coordinator),
        ]

    if domain == "binary_sensor":
        from .binary_sensor import PcPoweredBinarySensor

        return [PcPoweredBinarySensor(coordinator)]

    if domain == "switch":
        from .switch import PcPowerSwitch, SettingSwitch

        return [
            PcPowerSwitch(coordinator),
            SettingSwitch(coordinator, "child_lock", "机箱按钮童锁", "mdi:lock-outline"),
            SettingSwitch(coordinator, "xa_voice", "小爱语音控制", "mdi:microphone"),
            SettingSwitch(coordinator, "hibernate", "休眠关机", "mdi:sleep"),
            SettingSwitch(
                coordinator,
                "parameter_lock",
                "参数锁定",
                "mdi:lock",
                enabled_default=False,
            ),
            SettingSwitch(
                coordinator,
                "power_reset",
                "电源键复位",
                "mdi:restart",
                enabled_default=False,
            ),
        ]

    if domain == "button":
        from .button import CddzCommandButton
        from .const import CMD_FORCE_OFF, CMD_FORCE_RESTART, CMD_RESTART

        return [
            CddzCommandButton(coordinator, "restart", "重启", "mdi:restart", CMD_RESTART),
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

    if domain == "select":
        from .select import (
            IndicatorLightSelect,
            KeyModeSelect,
            PowerOnStateSelect,
        )

        return [
            IndicatorLightSelect(coordinator),
            PowerOnStateSelect(coordinator),
            KeyModeSelect(
                coordinator, "single_click_mode", "单击功能", "single", False
            ),
            KeyModeSelect(
                coordinator, "double_click_mode", "双击功能", "double", False
            ),
            KeyModeSelect(
                coordinator, "long_press_mode", "长按功能", "long", False
            ),
        ]

    if domain == "number":
        from .number import (
            DurationNumber,
            HibernateIntervalNumber,
            PcNumberEntity,
        )

        return [
            PcNumberEntity(coordinator),
            HibernateIntervalNumber(coordinator),
            DurationNumber(coordinator, "on_duration", "开机按键时长"),
            DurationNumber(coordinator, "off_duration", "关机按键时长"),
            DurationNumber(coordinator, "restart_duration", "重启按键时长"),
            DurationNumber(coordinator, "force_off_duration", "强制关机按键时长"),
        ]

    return []


async def async_setup_cddz_platform(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    domain: str,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add PC03W entities to the current Xiaomi Miot platform."""
    data = hass.data.setdefault(DATA_KEY, {})
    coordinators: dict[str, CddzCoordinator] = data.setdefault("coordinators", {})
    added: set[tuple[str, str]] = data.setdefault("added", set())
    lock: asyncio.Lock = data.setdefault("lock", asyncio.Lock())

    for device in HassEntry.init(hass, config_entry).devices.values():
        try:
            model = device.info.model or device.info.get("model") or ""
            urn = device.info.urn or ""
        except Exception as exc:  # noqa: BLE001 - vendor info may be incomplete
            _LOGGER.debug("Skipping device while checking PC03W model: %s", exc)
            continue
        if model != MODEL and "cddz-pc03w" not in urn:
            continue

        async with lock:
            coordinator = coordinators.get(device.unique_id)
            if coordinator is None:
                coordinator = CddzCoordinator(hass, device)
                await coordinator.async_refresh()
                coordinators[device.unique_id] = coordinator

                def _cleanup(unique_id: str = device.unique_id) -> None:
                    coordinators.pop(unique_id, None)
                    for key in [k for k in added if k[0] == unique_id]:
                        added.discard(key)

                config_entry.async_on_unload(coordinator.async_shutdown)
                config_entry.async_on_unload(_cleanup)
                _LOGGER.info("PC03W coordinator created for %s", device.did)

            key = (device.unique_id, domain)
            if key in added:
                continue

            entities = _entities_for_domain(domain, coordinator)
            if not entities:
                continue
            added.add(key)
            async_add_entities(entities, update_before_add=False)
            _LOGGER.info("Added %s PC03W %s entities", len(entities), domain)
