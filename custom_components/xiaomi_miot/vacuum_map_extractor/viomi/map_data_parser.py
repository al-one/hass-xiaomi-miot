import logging
from struct import unpack_from
from typing import Dict, List, Optional, Set, Tuple

from ..common.map_data import Area, ImageData, MapData, Path, Point, Room, \
    Wall, Zone
from ..common.map_data_parser import MapDataParser
from ..const import *
from ..viomi.image_handler import ImageHandlerViomi

_LOGGER = logging.getLogger(__name__)


class ParsingBuffer:
    def __init__(self, name: str, data: bytes, start_offs: int, length: int):
        self._name = name
        self._data = data
        self._offs = start_offs
        self._length = length
        self._image_beginning = None

    def set_name(self, name: str):
        self._name = name
        _LOGGER.debug('SECTION %s: offset 0x%x', self._name, self._offs)

    def mark_as_image_beginning(self):
        self._image_beginning = self._offs

    def get_at_image(self, offset):
        return self._data[self._image_beginning + offset - 1]

    def skip(self, field, n):
        if self._length < n:
            raise ValueError(f"error parsing {self._name}.{field} at offset {self._offs:#x}: buffer underrun")
        self._offs += n
        self._length -= n

    def get_uint8(self, field):
        if self._length < 1:
            raise ValueError(f"error parsing {self._name}.{field} at offset {self._offs:#x}: buffer underrun")
        self._offs += 1
        self._length -= 1
        return self._data[self._offs - 1]

    def get_uint16(self, field):
        if self._length < 2:
            raise ValueError(f"error parsing {self._name}.{field} at offset {self._offs:#x}: buffer underrun")
        self._offs += 2
        self._length -= 2
        return unpack_from('<H', self._data, self._offs - 2)[0]

    def get_uint32(self, field):
        if self._length < 4:
            raise ValueError(f"error parsing {self._name}.{field} at offset {self._offs:#x}: buffer underrun")
        self._offs += 4
        self._length -= 4
        return unpack_from('<L', self._data, self._offs - 4)[0]

    def get_float32(self, field):
        if self._length < 4:
            raise ValueError(f"error parsing {self._name}.{field} at offset {self._offs:#x}: buffer underrun")
        self._offs += 4
        self._length -= 4
        return unpack_from('<f', self._data, self._offs - 4)[0]

    def get_string_len8(self, field):
        n = self.get_uint8(field + '.len')
        if self._length < n:
            raise ValueError(f"error parsing {self._name}.{field} at offset {self._offs:#x}: buffer underrun")
        self._offs += n
        self._length -= n
        return self._data[self._offs - n:self._offs].decode('UTF-8')

    def peek_uint32(self, field):
        if self._length < 4:
            raise ValueError(f"error parsing {self._name}.{field} at offset {self._offs:#x}: buffer underrun")
        return unpack_from('<L', self._data, self._offs)[0]

    def check_empty(self):
        if self._length == 0:
            _LOGGER.debug('all of the data has been processed')
        else:
            _LOGGER.warning('%d bytes remained in the buffer', self._length)


class MapDataParserViomi(MapDataParser):
    FEATURE_ROBOT_STATUS = 0x00000001
    FEATURE_IMAGE = 0x00000002
    FEATURE_HISTORY = 0x00000004
    FEATURE_CHARGE_STATION = 0x00000008
    FEATURE_RESTRICTED_AREAS = 0x00000010
    FEATURE_CLEANING_AREAS = 0x00000020
    FEATURE_NAVIGATE = 0x00000040
    FEATURE_REALTIME = 0x00000080
    FEATURE_ROOMS = 0x00001000

    POSITION_UNKNOWN = 1100

    @staticmethod
    def parse(raw: bytes, colors, drawables, texts, sizes, image_config) -> MapData:
        map_data = MapData(0, 1)
        buf = ParsingBuffer('header', raw, 0, len(raw))
        feature_flags = buf.get_uint32('feature_flags')
        map_id = buf.peek_uint32('map_id')
        _LOGGER.debug('feature_flags: 0x%x, map_id: %d', feature_flags, map_id)

        if feature_flags & MapDataParserViomi.FEATURE_ROBOT_STATUS != 0:
            MapDataParserViomi.parse_section(buf, 'robot_status', map_id)
            buf.skip('unknown1', 0x28)

        if feature_flags & MapDataParserViomi.FEATURE_IMAGE != 0:
            MapDataParserViomi.parse_section(buf, 'image', map_id)
            map_data.image, map_data.rooms, map_data.cleaned_rooms = \
                MapDataParserViomi.parse_image(buf, colors, image_config, DRAWABLE_CLEANED_AREA in drawables)

        if feature_flags & MapDataParserViomi.FEATURE_HISTORY != 0:
            MapDataParserViomi.parse_section(buf, 'history', map_id)
            map_data.path = MapDataParserViomi.parse_history(buf)

        if feature_flags & MapDataParserViomi.FEATURE_CHARGE_STATION != 0:
            MapDataParserViomi.parse_section(buf, 'charge_station', map_id)
            map_data.charger = MapDataParserViomi.parse_position(buf, 'pos')
            foo = buf.get_float32('foo')
            _LOGGER.debug('pos: %s, foo: %f', map_data.charger, foo)

        if feature_flags & MapDataParserViomi.FEATURE_RESTRICTED_AREAS != 0:
            MapDataParserViomi.parse_section(buf, 'restricted_areas', map_id)
            map_data.walls, map_data.no_go_areas = MapDataParserViomi.parse_restricted_areas(buf)

        if feature_flags & MapDataParserViomi.FEATURE_CLEANING_AREAS != 0:
            MapDataParserViomi.parse_section(buf, 'cleaning_areas', map_id)
            map_data.zones = MapDataParserViomi.parse_cleaning_areas(buf)

        if feature_flags & MapDataParserViomi.FEATURE_NAVIGATE != 0:
            MapDataParserViomi.parse_section(buf, 'navigate', map_id)
            buf.skip('unknown1', 4)
            map_data.goto = MapDataParserViomi.parse_position(buf, 'pos')
            foo = buf.get_float32('foo')
            _LOGGER.debug('pos: %s, foo: %f', map_data.goto, foo)

        if feature_flags & MapDataParserViomi.FEATURE_REALTIME != 0:
            MapDataParserViomi.parse_section(buf, 'realtime', map_id)
            buf.skip('unknown1', 5)
            map_data.vacuum_position = MapDataParserViomi.parse_position(buf, 'pos')
            foo = buf.get_float32('foo')
            _LOGGER.debug('pos: %s, foo: %f', map_data.vacuum_position, foo)

        if feature_flags & 0x00000800 != 0:
            MapDataParserViomi.parse_section(buf, 'unknown1', map_id)
            MapDataParserViomi.parse_unknown_section(buf)

        if feature_flags & MapDataParserViomi.FEATURE_ROOMS != 0:
            MapDataParserViomi.parse_section(buf, 'rooms', map_id)
            MapDataParserViomi.parse_rooms(buf, map_data.rooms)

        if feature_flags & 0x00002000 != 0:
            MapDataParserViomi.parse_section(buf, 'unknown2', map_id)
            MapDataParserViomi.parse_unknown_section(buf)

        if feature_flags & 0x00004000 != 0:
            MapDataParserViomi.parse_section(buf, 'room_outlines', map_id)
            MapDataParserViomi.parse_room_outlines(buf)

        buf.check_empty()

        _LOGGER.debug('rooms: %s', [str(room) for number, room in map_data.rooms.items()])
        if not map_data.image.is_empty:
            MapDataParserViomi.draw_elements(colors, drawables, sizes, map_data, image_config)
            if len(map_data.rooms) > 0 and map_data.vacuum_position is not None:
                map_data.vacuum_room = MapDataParserViomi.get_current_vacuum_room(buf, map_data.vacuum_position)
                if map_data.vacuum_room is not None:
                    map_data.vacuum_room_name = map_data.rooms[map_data.vacuum_room].name
                _LOGGER.debug('current vacuum room: %s', map_data.vacuum_room)
            ImageHandlerViomi.rotate(map_data.image)
            ImageHandlerViomi.draw_texts(map_data.image, texts)
        return map_data

    @staticmethod
    def map_to_image(x):
        return x * 20 + 400

    @staticmethod
    def get_current_vacuum_room(buf: ParsingBuffer, vacuum_position: Point) -> Optional[int]:
        x = int(MapDataParserViomi.map_to_image(vacuum_position.x))
        y = int(MapDataParserViomi.map_to_image(vacuum_position.y))
        pixel_type = buf.get_at_image(y * 800 + x)
        if ImageHandlerViomi.MAP_ROOM_MIN <= pixel_type <= ImageHandlerViomi.MAP_ROOM_MAX:
            return pixel_type
        elif ImageHandlerViomi.MAP_SELECTED_ROOM_MIN <= pixel_type <= ImageHandlerViomi.MAP_SELECTED_ROOM_MAX:
            return pixel_type - ImageHandlerViomi.MAP_SELECTED_ROOM_MIN + ImageHandlerViomi.MAP_ROOM_MIN
        return None

    @staticmethod
    def parse_image(buf: ParsingBuffer, colors: Dict, image_config: Dict, draw_cleaned_area: bool) \
            -> Tuple[ImageData, Dict[int, Room], Set[int]]:
        buf.skip('unknown1', 0x08)
        image_top = 0
        image_left = 0
        image_height = buf.get_uint32('image_height')
        image_width = buf.get_uint32('image_width')
        buf.skip('unknown2', 20)
        image_size = image_height * image_width
        _LOGGER.debug('width: %d, height: %d', image_width, image_height)
        if image_width \
                - image_width * (image_config[CONF_TRIM][CONF_LEFT] + image_config[CONF_TRIM][CONF_RIGHT]) / 100 \
                < MINIMAL_IMAGE_WIDTH:
            image_config[CONF_TRIM][CONF_LEFT] = 0
            image_config[CONF_TRIM][CONF_RIGHT] = 0
        if image_height \
                - image_height * (image_config[CONF_TRIM][CONF_TOP] + image_config[CONF_TRIM][CONF_BOTTOM]) / 100 \
                < MINIMAL_IMAGE_HEIGHT:
            image_config[CONF_TRIM][CONF_TOP] = 0
            image_config[CONF_TRIM][CONF_BOTTOM] = 0
        buf.mark_as_image_beginning()
        image, rooms_raw, cleaned_areas, cleaned_areas_layer = ImageHandlerViomi.parse(buf, image_width, image_height,
                                                                                       colors, image_config,
                                                                                       draw_cleaned_area)
        _LOGGER.debug('img: number of rooms: %d, numbers: %s', len(rooms_raw), rooms_raw.keys())
        rooms = {}
        for number, room in rooms_raw.items():
            rooms[number] = Room(number, (room[0] + image_left - 400) / 20,
                                 (room[1] + image_top - 400) / 20,
                                 (room[2] + image_left - 400) / 20,
                                 (room[3] + image_top - 400) / 20)
        return ImageData(image_size, image_top, image_left, image_height, image_width, image_config,
                         image, MapDataParserViomi.map_to_image,
                         {DRAWABLE_CLEANED_AREA: cleaned_areas_layer}), rooms, cleaned_areas

    @staticmethod
    def parse_history(buf: ParsingBuffer) -> Path:
        path_points = []
        buf.skip('unknown1', 4)
        history_count = buf.get_uint32('history_count')
        for _ in range(history_count):
            mode = buf.get_uint8('mode')  # 0: taxi, 1: working
            path_points.append(MapDataParserViomi.parse_position(buf, 'path'))
        return Path(len(path_points), 1, 0, path_points)

    @staticmethod
    def parse_restricted_areas(buf: ParsingBuffer) -> Tuple[List[Wall], List[Area]]:
        walls = []
        areas = []
        buf.skip('unknown1', 4)
        area_count = buf.get_uint32('area_count')
        for _ in range(area_count):
            buf.skip('restricted.unknown1', 12)
            p1 = MapDataParserViomi.parse_position(buf, 'p1')
            p2 = MapDataParserViomi.parse_position(buf, 'p2')
            p3 = MapDataParserViomi.parse_position(buf, 'p3')
            p4 = MapDataParserViomi.parse_position(buf, 'p4')
            buf.skip('restricted.unknown2', 48)
            _LOGGER.debug('restricted: %s %s %s %s', p1, p2, p3, p4)
            if p1 == p2 and p3 == p4:
                walls.append(Wall(p1.x, p1.y, p3.x, p3.y))
            else:
                areas.append(Area(p1.x, p1.y, p2.x, p2.y, p3.x, p3.y, p4.x, p4.y))
        return walls, areas

    @staticmethod
    def parse_cleaning_areas(buf: ParsingBuffer) -> List[Zone]:
        buf.skip('unknown1', 4)
        area_count = buf.get_uint32('area_count')
        zones = []
        for _ in range(area_count):
            buf.skip('area.unknown1', 12)
            p1 = MapDataParserViomi.parse_position(buf, 'p1')
            p2 = MapDataParserViomi.parse_position(buf, 'p2')
            p3 = MapDataParserViomi.parse_position(buf, 'p3')
            p4 = MapDataParserViomi.parse_position(buf, 'p4')
            buf.skip('area.unknown2', 48)
            zones.append(Zone(p1.x, p1.y, p3.x, p3.y))
        return zones

    @staticmethod
    def parse_rooms(buf: ParsingBuffer, map_data_rooms: Dict[int, Room]):
        map_name = buf.get_string_len8('map_name')
        map_arg = buf.get_uint32('map_arg')
        _LOGGER.debug('map#%d: %s', map_arg, map_name)
        while map_arg > 1:
            map_name = buf.get_string_len8('map_name')
            map_arg = buf.get_uint32('map_arg')
            _LOGGER.debug('map#%d: %s', map_arg, map_name)
        room_count = buf.get_uint32('room_count')
        for _ in range(room_count):
            room_id = buf.get_uint8('room.id')
            room_name = buf.get_string_len8('room.name')
            if map_data_rooms is not None and room_id in map_data_rooms:
                map_data_rooms[room_id].name = room_name
            buf.skip('room.unknown1', 1)
            room_text_pos = MapDataParserViomi.parse_position(buf, 'room.text_pos')
            _LOGGER.debug('room#%d: %s %s', room_id, room_name, room_text_pos)
        buf.skip('unknown1', 6)

    @staticmethod
    def parse_room_outlines(buf: ParsingBuffer):
        buf.skip('unknown1', 51)
        room_count = buf.get_uint32('room_count')
        for _ in range(room_count):
            room_id = buf.get_uint32('room.id')
            segment_count = buf.get_uint32('room.segment_count')
            for _ in range(segment_count):
                buf.skip('unknown2', 5)
            _LOGGER.debug('room#%d: segment_count: %d', room_id, segment_count)

    @staticmethod
    def parse_section(buf: ParsingBuffer, name: str, map_id: int):
        buf.set_name(name)
        magic = buf.get_uint32('magic')
        if magic != map_id:
            raise ValueError(
                f"error parsing section {name} at offset {buf._offs - 4:#x}: magic check failed {magic:#x}")

    @staticmethod
    def parse_position(buf: ParsingBuffer, name: str) -> Optional[Point]:
        x = buf.get_float32(name + '.x')
        y = buf.get_float32(name + '.y')
        if x == MapDataParserViomi.POSITION_UNKNOWN or y == MapDataParserViomi.POSITION_UNKNOWN:
            return None
        return Point(x, y)

    @staticmethod
    def parse_unknown_section(buf: ParsingBuffer) -> bool:
        n = buf._data[buf._offs:].find(buf._data[4:8])
        if n >= 0:
            buf._offs += n
            buf._length -= n
            return True
        else:
            buf._offs += buf._length
            buf._length = 0
            return False
