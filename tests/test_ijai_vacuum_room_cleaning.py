"""Room cleaning support for older ijai MIoT vacuums."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.vacuum import VacuumEntityFeature

from custom_components.xiaomi_miot.core.miot_spec import MiotResult
from custom_components.xiaomi_miot.vacuum import (
    Segment,
    MiotVacuumEntity,
    _parse_map_room_list,
    _room_clean_config,
)

MODEL = "ijai.vacuum.v3"


def _entity(device, spec):
    return MiotVacuumEntity(
        {"device": device, "name": "Vacuum"}, spec.get_service("vacuum")
    )


def test_ijai_room_cleaning_is_exposed(make_device, load_miot_spec):
    spec = load_miot_spec(f"{MODEL}.json")
    entity = _entity(make_device(spec, model=MODEL), spec)

    if Segment is None:
        pytest.skip("Home Assistant does not support vacuum segments")
    assert VacuumEntityFeature.CLEAN_AREA in entity.supported_features
    assert entity.supports_room_cleaning


def test_parse_map_room_list():
    if Segment is None:
        pytest.skip("Home Assistant does not support vacuum segments")
    segments = _parse_map_room_list(
        '[{"name":"Kitchen","id":10},{"name":"Office","id":11}]'
    )
    assert segments == [
        Segment(id="10", name="Kitchen"),
        Segment(id="11", name="Office"),
    ]


def test_parse_map_room_list_rejects_invalid_values():
    assert _parse_map_room_list("") == []
    assert _parse_map_room_list("not-json") == []
    assert _parse_map_room_list({"id": 10}) == []


def test_room_clean_config():
    assert _room_clean_config(["10", "11"], 0) == (
        '{"rooms":[10,11],"clean_mode":0,"is_ai_cleaning":false}'
    )


@pytest.mark.skipif(Segment is None, reason="Home Assistant does not support vacuum segments")
async def test_clean_segments_uses_set_room_clean(make_device, load_miot_spec):
    spec = load_miot_spec(f"{MODEL}.json")
    entity = _entity(make_device(spec, model=MODEL), spec)
    entity.async_set_miot_property = AsyncMock()
    entity.async_call_action = AsyncMock(
        return_value=MiotResult({"code": 0})
    )

    await entity.async_clean_segments(["10", "11"])

    entity.async_set_miot_property.assert_awaited_once_with(2, 8, 7)

    entity.async_call_action.assert_awaited_once_with(
        entity._act_set_room_clean,
        [
            {"piid": 24, "value": "10,11"},
            {"piid": 25, "value": 0},
            {"piid": 26, "value": 1},
        ],
        force_params=True,
    )


@pytest.mark.skipif(Segment is None, reason="Home Assistant does not support vacuum segments")
async def test_get_segments_reads_map_room_list(make_device, load_miot_spec):
    spec = load_miot_spec(f"{MODEL}.json")
    entity = _entity(make_device(spec, model=MODEL), spec)
    entity._prop_cur_map_id = SimpleNamespace(
        full_name="map.cur_map_id", from_device=lambda device: 123456
    )
    entity.async_call_action = AsyncMock(
        return_value=MiotResult({
            "code": 0,
            "out": [{"piid": 17, "value": '[{"name":"Kitchen","id":10}]'}],
        })
    )
    entity._state_attrs = {}

    segments = await entity.async_get_segments()

    entity.async_call_action.assert_awaited_once_with(
        entity._act_get_map_room_list, [123456]
    )
    assert segments == [Segment(id="10", name="Kitchen")]
    assert entity._state_attrs["room_mapping"] == [["10", "10", "Kitchen"]]
