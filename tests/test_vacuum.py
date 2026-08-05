from homeassistant.components.vacuum import Segment

from custom_components.xiaomi_miot.vacuum import (
    _parse_room_information,
    _room_clean_config,
    _room_sweep_payload,
)


def test_parse_room_information():
    result = _parse_room_information(
        '{"rooms":[{"id":3,"name":"Living Room"},{"id":16,"name":"Office"}],"map_uid":10}'
    )

    assert result == [
        Segment(id='3', name='Living Room'),
        Segment(id='16', name='Office'),
    ]


def test_parse_room_information_rejects_invalid_values():
    assert _parse_room_information('') == []
    assert _parse_room_information('{"rooms":null}') == []
    assert _parse_room_information('not-json') == []


def test_room_sweep_payload():
    assert _room_sweep_payload(['3', '16']) == '3,16'


def test_room_clean_config():
    assert _room_clean_config(['3', '16']) == (
        '{"rooms":[3,16],"clean_mode":1,"is_ai_cleaning":false}'
    )
