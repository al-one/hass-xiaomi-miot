from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.vacuum import VacuumActivity

from custom_components.xiaomi_miot import MiotEntity
from custom_components.xiaomi_miot.core.miio2miot import Miio2MiotHelper
from custom_components.xiaomi_miot.vacuum import MiotViomiVacuumEntity

MODEL = "viomi.vacuum.v10"

# Responses to the viomi.vacuum.v8 miio commands, captured from a real
# viomi.vacuum.v10 (fw 3.5.8_0035) while docked and charging
GET_PROP = ["3.5.8_0035", 5, 0, 2103, 77, 3, 1, 0, 0.78, 3, 13, 1, 1, 1, 0]
GET_CONSUMABLES = [16, 16, 16, 2]


def miio_device(run_state=5):
    values = list(GET_PROP)
    values[1] = run_state
    responses = {"get_prop": values, "get_consumables": GET_CONSUMABLES}
    device = AsyncMock()
    device.async_send.side_effect = lambda method, params=None: responses[method]
    return device


def test_viomi_vacuum_v10_extends_v8_mapping(hass, load_miot_spec):
    spec = load_miot_spec(f"{MODEL}.json")
    helper = Miio2MiotHelper.from_model(hass, MODEL, spec)

    assert helper is not None
    assert helper.specs["prop.2.1"] == {"prop": "run_state"}
    assert helper.specs["prop.2.2"]["setter"] == "set_suction"
    assert {
        "action.2.1", "action.2.2", "action.2.3", "action.2.4", "action.2.5", "action.3.1",
    } <= set(helper.specs)
    assert [c["method"] for c in helper.config["miio_commands"]] == ["get_prop", "get_consumables"]


@pytest.mark.parametrize("run_state", range(9))
async def test_viomi_vacuum_v10_status_matches_run_state(hass, load_miot_spec, run_state):
    spec = load_miot_spec(f"{MODEL}.json")
    helper = Miio2MiotHelper.from_model(hass, MODEL, spec)
    mapping = {
        "status": {"siid": 2, "piid": 1},
        "mode": {"siid": 2, "piid": 2},
        "battery_level": {"siid": 3, "piid": 1},
    }

    results = await helper.async_get_miot_props(miio_device(run_state), mapping)

    assert [r["value"] for r in results] == [run_state, 3, 77]


async def test_viomi_vacuum_v10_consumables(hass, load_miot_spec):
    spec = load_miot_spec(f"{MODEL}.json")
    helper = Miio2MiotHelper.from_model(hass, MODEL, spec)

    props = await helper.async_get_miio_props(miio_device())

    assert props["main_brush_life"] == 96
    assert props["side_brush_life"] == 91
    assert props["hypa_life"] == 91
    assert props["mop_life"] == 99


async def test_viomi_vacuum_v10_clean_area_and_time(hass, make_device, load_miot_spec):
    spec = load_miot_spec(f"{MODEL}.json")
    device = make_device(spec, model=MODEL)
    device.local = miio_device()
    device.miio2miot = Miio2MiotHelper.from_model(hass, MODEL, spec)
    await device.miio2miot.async_get_miio_props(device.local)

    await device.update_miio_props()

    assert device.props["miio.s_area"] == 0.78
    assert device.props["miio.s_time"] == 0


@pytest.mark.parametrize(("status", "activity"), [
    (0, VacuumActivity.IDLE),
    (1, VacuumActivity.IDLE),
    (2, VacuumActivity.PAUSED),
    (3, VacuumActivity.CLEANING),
    (4, VacuumActivity.RETURNING),
    (5, VacuumActivity.DOCKED),
    (6, VacuumActivity.CLEANING),
    (7, VacuumActivity.CLEANING),
])
async def test_viomi_vacuum_v10_activity(make_device, load_miot_spec, status, activity):
    spec = load_miot_spec(f"{MODEL}.json")
    device = make_device(spec, model=MODEL)
    entity = MiotViomiVacuumEntity({"device": device, "name": "Vacuum"}, spec.get_service("vacuum"))
    entity._available = True
    device.props["vacuum.status"] = status

    with patch.object(MiotEntity, "async_update", AsyncMock()):
        await entity.async_update()

    assert entity.activity == activity
