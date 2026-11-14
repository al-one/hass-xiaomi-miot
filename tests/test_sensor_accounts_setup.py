"""Regression tests for sensor account setup issues #2979 and #2722.

An account with messages disabled must still register its slot for scene
history, same-user entries in one region must not register duplicate sensors,
and the same account in different regions must get independent sensors.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.helpers import entity_registry as er

from custom_components.xiaomi_miot import DOMAIN, init_integration_data
from custom_components.xiaomi_miot import sensor as sensor_module


def _fake_cloud(user_id, server="cn", **kwargs):
    return SimpleNamespace(
        user_id=user_id,
        default_server=server,
        account_key=f"{user_id}-{server}",
        **kwargs,
    )


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
    cloud = _fake_cloud(
        "1583113750",
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
        await sensor_module.async_setup_entry(
            hass, SimpleNamespace(), lambda *args, **kwargs: None
        )

    account = hass.data[DOMAIN]["accounts"]["1583113750-cn"]
    assert account["scene_history_123"] is _DummySceneHistorySensor.created[0]


async def test_scene_history_setup_keeps_existing_slot(hass):
    init_integration_data(hass)
    cloud = _fake_cloud(
        "1583113750",
        async_get_homerooms=AsyncMock(return_value=[]),
    )
    entry = _fake_entry(
        cloud, {"disable_message": True, "disable_scene_history": False}
    )
    hass.data[DOMAIN]["accounts"]["1583113750-cn"] = {"keep": True}

    with patch.object(sensor_module.HassEntry, "init", return_value=entry), \
         patch.object(sensor_module, "async_setup_config_entry", AsyncMock()):
        await sensor_module.async_setup_entry(
            hass, SimpleNamespace(), lambda *args, **kwargs: None
        )

    assert hass.data[DOMAIN]["accounts"]["1583113750-cn"] == {"keep": True}


async def test_concurrent_account_setup_adds_one_message_sensor(hass):
    """Duplicate entries for one account and region must share one sensor."""
    init_integration_data(hass)
    user_id = "1583113750"
    cloud = _fake_cloud(user_id)
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
        def __init__(self, hass, cloud):
            self._attr_unique_id = f"xiaomi_miot-mihome-message-{cloud.account_key}"
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
    assert entities[0]._attr_unique_id == (
        f"xiaomi_miot-mihome-message-{user_id}-cn"
    )
    assert hass.data[DOMAIN]["accounts"][f"{user_id}-cn"]["messenger"] is entities[0]


async def test_same_user_in_two_regions_gets_two_message_sensors(hass):
    """The same account in two regions must not share one message sensor."""
    init_integration_data(hass)
    user_id = "1886497405"
    registrations = []

    class _DummyMessageSensor:
        def __init__(self, hass, cloud):
            self._attr_unique_id = f"xiaomi_miot-mihome-message-{cloud.account_key}"
            self.entity_id = sensor_module._message_entity_id(cloud)
            self.coordinator = SimpleNamespace(
                async_config_entry_first_refresh=AsyncMock()
            )

    def make_adder():
        def add_entities(entities, update_before_add=False):
            registrations.extend(entities)

        return add_entities

    with patch.object(
        sensor_module.HassEntry, "init", side_effect=lambda hass, entry: entry
    ), patch.object(
        sensor_module, "MihomeMessageSensor", _DummyMessageSensor
    ), patch.object(
        sensor_module, "async_setup_config_entry", AsyncMock()
    ):
        for server in ("cn", "sg"):
            cloud = _fake_cloud(user_id, server)
            await sensor_module.async_setup_entry(
                hass,
                _fake_entry(cloud, {"disable_scene_history": True}),
                make_adder(),
            )

    assert len(registrations) == 2
    assert {e._attr_unique_id for e in registrations} == {
        f"xiaomi_miot-mihome-message-{user_id}-cn",
        f"xiaomi_miot-mihome-message-{user_id}-sg",
    }
    assert {e.entity_id for e in registrations} == {
        f"sensor.mi_{user_id}_message",
        f"sensor.mi_{user_id}_sg_message",
    }
    assert set(hass.data[DOMAIN]["accounts"]) == {
        f"{user_id}-cn",
        f"{user_id}-sg",
    }


async def test_non_cn_legacy_message_entity_is_renamed(hass):
    """A non-default region gets a region suffix in its entity ID."""
    init_integration_data(hass)
    user_id = "1886497405"
    ent_reg = er.async_get(hass)
    legacy = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"xiaomi_miot-mihome-message-{user_id}",
        suggested_object_id=f"mi_{user_id}_message",
    )
    assert legacy.entity_id == f"sensor.mi_{user_id}_message"

    class _DummyMessageSensor:
        def __init__(self, hass, cloud):
            self._attr_unique_id = f"xiaomi_miot-mihome-message-{cloud.account_key}"
            self.coordinator = SimpleNamespace(
                async_config_entry_first_refresh=AsyncMock()
            )

    cloud = _fake_cloud(user_id, "sg")
    with patch.object(
        sensor_module.HassEntry, "init", side_effect=lambda hass, entry: entry
    ), patch.object(
        sensor_module, "MihomeMessageSensor", _DummyMessageSensor
    ), patch.object(
        sensor_module, "async_setup_config_entry", AsyncMock()
    ):
        await sensor_module.async_setup_entry(
            hass,
            _fake_entry(cloud, {"disable_scene_history": True}),
            lambda *args, **kwargs: None,
        )

    assert ent_reg.async_get(f"sensor.mi_{user_id}_message") is None
    assert ent_reg.async_get_entity_id(
        "sensor", DOMAIN, f"xiaomi_miot-mihome-message-{user_id}-sg"
    ) == f"sensor.mi_{user_id}_sg_message"


async def test_cn_legacy_message_entity_keeps_entity_id(hass):
    """The default region only migrates the unique ID, not the entity ID."""
    init_integration_data(hass)
    user_id = "1886497405"
    ent_reg = er.async_get(hass)
    legacy = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"xiaomi_miot-mihome-message-{user_id}",
        suggested_object_id=f"mi_{user_id}_message",
    )

    class _DummyMessageSensor:
        def __init__(self, hass, cloud):
            self._attr_unique_id = f"xiaomi_miot-mihome-message-{cloud.account_key}"
            self.coordinator = SimpleNamespace(
                async_config_entry_first_refresh=AsyncMock()
            )

    cloud = _fake_cloud(user_id, "cn")
    with patch.object(
        sensor_module.HassEntry, "init", side_effect=lambda hass, entry: entry
    ), patch.object(
        sensor_module, "MihomeMessageSensor", _DummyMessageSensor
    ), patch.object(
        sensor_module, "async_setup_config_entry", AsyncMock()
    ):
        await sensor_module.async_setup_entry(
            hass,
            _fake_entry(cloud, {"disable_scene_history": True}),
            lambda *args, **kwargs: None,
        )

    assert ent_reg.async_get_entity_id(
        "sensor", DOMAIN, f"xiaomi_miot-mihome-message-{user_id}-cn"
    ) == legacy.entity_id
