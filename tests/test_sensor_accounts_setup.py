"""Regression tests for issue #2979: scene history setup KeyError.

A UI-configured account with messages disabled must still register its
account slot before the scene history block indexes it.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from custom_components.xiaomi_miot import DOMAIN, init_integration_data
from custom_components.xiaomi_miot import sensor as sensor_module


def _fake_entry(cloud, cfg):
    entry = SimpleNamespace(
        get_cloud=AsyncMock(return_value=cloud),
        get_config=lambda k=None, d=None: dict(cfg) if k is None else cfg.get(k, d),
    )
    entry.new_adder = lambda *a, **k: entry
    return entry


class _DummySceneHistorySensor:
    created = []

    def __init__(self, *args, **kwargs):
        self.coordinator = SimpleNamespace(
            async_config_entry_first_refresh=AsyncMock()
        )
        _DummySceneHistorySensor.created.append(self)


async def test_scene_history_setup_with_disabled_message(hass):
    init_integration_data(hass)
    cloud = SimpleNamespace(
        user_id="1583113750",
        async_get_homerooms=AsyncMock(return_value=[{"id": 123, "uid": "u"}]),
    )
    entry = _fake_entry(
        cloud, {"disable_message": True, "disable_scene_history": False}
    )
    _DummySceneHistorySensor.created = []

    with patch.object(sensor_module.HassEntry, "init", return_value=entry), \
         patch.object(
             sensor_module, "MihomeSceneHistorySensor", _DummySceneHistorySensor
         ), \
         patch.object(sensor_module, "async_setup_config_entry", AsyncMock()):
        await sensor_module.async_setup_entry(hass, SimpleNamespace(), AsyncMock())

    account = hass.data[DOMAIN]["accounts"]["1583113750"]
    assert account["scene_history_123"] is _DummySceneHistorySensor.created[0]

async def test_scene_history_setup_keeps_existing_slot(hass):
    init_integration_data(hass)
    cloud = SimpleNamespace(
        user_id="1583113750",
        async_get_homerooms=AsyncMock(return_value=[]),
    )
    entry = _fake_entry(
        cloud, {"disable_message": True, "disable_scene_history": False}
    )
    hass.data[DOMAIN]["accounts"]["1583113750"] = {"keep": True}

    with patch.object(sensor_module.HassEntry, "init", return_value=entry), \
         patch.object(sensor_module, "async_setup_config_entry", AsyncMock()):
        await sensor_module.async_setup_entry(hass, SimpleNamespace(), AsyncMock())

    assert hass.data[DOMAIN]["accounts"]["1583113750"] == {"keep": True}
