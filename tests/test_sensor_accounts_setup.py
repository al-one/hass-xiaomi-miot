"""Regression tests for sensor account setup issues #2979 and #2722.

An account with messages disabled must still register its slot for scene
history, and same-user entries must not race to register duplicate sensors.
"""
import asyncio
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


async def test_concurrent_account_setup_adds_one_message_sensor(hass):
    """Two region entries for one user must share one message entity."""
    init_integration_data(hass)
    user_id = "1583113750"
    cloud = SimpleNamespace(user_id=user_id)
    second_setup_started = asyncio.Event()
    refresh_started = asyncio.Event()
    finish_refresh = asyncio.Event()
    cloud_calls = 0

    async def get_cloud():
        nonlocal cloud_calls
        cloud_calls += 1
        if cloud_calls == 2:
            second_setup_started.set()
        return cloud

    def make_entry():
        entry = SimpleNamespace(
            get_cloud=get_cloud,
            get_config=lambda k=None, d=None: d if k is None else {
                "disable_scene_history": True
            }.get(k, d),
        )
        entry.new_adder = lambda *a, **k: entry
        return entry

    registrations = []

    class _DummyMessageSensor:
        def __init__(self, *args, **kwargs):
            self._attr_unique_id = f"xiaomi_miot-mihome-message-{user_id}"
            self.coordinator = SimpleNamespace(
                async_config_entry_first_refresh=self._first_refresh
            )

        async def _first_refresh(self):
            refresh_started.set()
            await finish_refresh.wait()

    def make_adder(region):
        def add_entities(entities, update_before_add=False):
            registrations.append((region, entities))

        return add_entities

    with patch.object(
        sensor_module.HassEntry, "init", side_effect=lambda hass, entry: entry
    ), patch.object(
        sensor_module, "MihomeMessageSensor", _DummyMessageSensor
    ), patch.object(
        sensor_module, "async_setup_config_entry", AsyncMock()
    ):
        first = asyncio.create_task(
            sensor_module.async_setup_entry(
                hass, make_entry(), make_adder("region_a")
            )
        )
        await asyncio.wait_for(refresh_started.wait(), timeout=1)
        second = asyncio.create_task(
            sensor_module.async_setup_entry(
                hass, make_entry(), make_adder("region_b")
            )
        )
        await asyncio.wait_for(second_setup_started.wait(), timeout=1)
        await asyncio.sleep(0)
        finish_refresh.set()
        await asyncio.gather(first, second)

    assert len(registrations) == 1
    region, entities = registrations[0]
    assert region in {"region_a", "region_b"}
    assert len(entities) == 1
    assert entities[0]._attr_unique_id == f"xiaomi_miot-mihome-message-{user_id}"
    assert hass.data[DOMAIN]["accounts"][user_id]["messenger"] is entities[0]
