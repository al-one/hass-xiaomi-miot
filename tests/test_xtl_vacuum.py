import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.vacuum import VacuumEntityFeature

from custom_components.xiaomi_miot.core.miot_spec import MiotResult
from custom_components.xiaomi_miot import vacuum as vacuum_platform
from custom_components.xiaomi_miot.vacuum import MiotXtlVacuumEntity

MODEL = "xtl.vacuum.xm2216"
MAP_URL = "https://fds.example/xtl-vacuum-xm2216/0"

# Synthetic cloud map file: fields[3] is room metadata (as a JSON string),
# fields[9] the outline polygons keyed by room_id. Names come padded from the app.
CLOUD_MAP = {
    "mapId": 1,
    "fields": [
        "", "", "", json.dumps([
            {"id": 1, "name": "Kitchen  ", "type": "4", "centerX": 330, "centerY": 420, "room_id": 7},
            {"id": 2, "name": "", "type": "", "centerX": 400, "centerY": 390, "room_id": 3},
        ]), "", "", "", "", [],
        [
            {"id": 7, "data": [303, 397, 303, 444, 360, 444, 360, 397]},
            {"id": 3, "data": [380, 380, 380, 400, 420, 400, 420, 380]},
        ],
    ],
    "cleanValues": 0,
}


class FakeCloud:
    user_id = "1234"

    def __init__(self):
        self.calls = []

    async def async_request_api(self, api, data=None, **kwargs):
        self.calls.append((api, data))
        return {"code": 0, "result": {"url": MAP_URL}}


@pytest.fixture
def entity(make_device, load_miot_spec):
    spec = load_miot_spec(f"{MODEL}.json")
    device = make_device(spec, model=MODEL)
    device.cloud = FakeCloud()
    ent = MiotXtlVacuumEntity({"device": device, "name": "Vacuum"}, spec.get_service("vacuum"))
    ent._available = True
    ent.calls = []

    async def call_action(act, params=None, **kwargs):
        ent.calls.append((act.name, params))
        if act.name == "get_map_data":
            return MiotResult({"code": 0, "out": [{"piid": 38, "value": "1234/test-device/0"}]})
        return MiotResult({"code": 0})

    ent.async_call_action = call_action
    task_idle(ent)
    return ent


def task_idle(ent, task=1, ret=1):
    ent.device.props[ent._prop_task.full_name] = task
    ent.device.props[ent._prop_return.full_name] = ret


@pytest.fixture(autouse=True)
def no_sleep():
    with patch.object(vacuum_platform.asyncio, "sleep", AsyncMock()):
        yield


@pytest.fixture
def cloud_map():
    response = MagicMock()
    response.read = AsyncMock(return_value=json.dumps(CLOUD_MAP).encode())
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch.object(vacuum_platform, "async_get_clientsession", return_value=session):
        yield session


def test_xtl_features(entity):
    features = entity.supported_features
    assert isinstance(features, VacuumEntityFeature)
    assert VacuumEntityFeature.CLEAN_SPOT in features
    clean_area = getattr(VacuumEntityFeature, "CLEAN_AREA", None)
    if clean_area and vacuum_platform.Segment:
        assert clean_area in features


async def test_xtl_rooms_from_cloud_map(entity, cloud_map):
    rooms = await entity.async_refresh_rooms()

    assert entity.device.cloud.calls[0] == (
        "v2/home/get_interim_file_url_pro", {"obj_name": "1234/test-device/0"},
    )
    cloud_map.get.assert_called_once_with(MAP_URL, timeout=30)
    # named rooms keep their (stripped) name, unnamed ones get id + size
    assert {rid: r["name"] for rid, r in rooms.items()} == {7: "Kitchen", 3: "Room 3 (2.0 m²)"}
    assert entity._state_attrs["rooms"] == {7: "Kitchen", 3: "Room 3 (2.0 m²)"}


@pytest.mark.skipif(vacuum_platform.Segment is None, reason="vacuum segments need HA 2026.3+")
async def test_xtl_segments(entity, cloud_map):
    segments = await entity.async_get_segments()

    assert [(s.id, s.name) for s in segments] == [("7", "Kitchen"), ("3", "Room 3 (2.0 m²)")]


async def test_xtl_clean_segments(entity):
    await entity.async_clean_segments(["7", "3"])

    assert entity.calls == [("start_clean", [3, "[7,3]"])]


async def test_xtl_open_task_is_stopped_first(entity):
    task_idle(entity, task=9)  # Area Pause

    await entity.async_send_command("app_segment_clean", [{"segments": [5], "repeat": 2}])

    assert entity.calls == [
        ("stop_clean", None), ("set_clean_count", [2]), ("start_clean", [3, "[5]"]),
    ]


async def test_xtl_returning_counts_as_open_task(entity):
    task_idle(entity, task=1, ret=2)

    await entity.async_send_command("app_segment_clean", [6])

    assert entity.calls == [("stop_clean", None), ("start_clean", [3, "[6]"])]


async def test_xtl_zoned_clean(entity):
    await entity.async_send_command("app_zoned_clean", [[354.4, 422, 305, 402, 1]])

    # corners normalised, rounded and expanded to x1,y1,x2,y1,x2,y2,x1,y2
    assert entity.calls == [
        ("set_clean_count", [1]),
        ("start_clean", [4, "[305,402,354,402,354,422,305,422]"]),
    ]


async def test_xtl_spot_and_stop(entity):
    await entity.async_clean_spot()
    await entity.async_stop()

    # stop-sweeping leaves the task open, stop-clean ends it
    assert entity.calls == [("start_clean", [6, ""]), ("stop_clean", None)]


async def test_xtl_other_commands_still_go_to_miio(entity):
    with patch.object(MiotXtlVacuumEntity, "async_miio_command", AsyncMock(return_value="ok")) as miio:
        assert await entity.async_send_command("get_status", []) == "ok"

    miio.assert_awaited_once_with("get_status", [])
