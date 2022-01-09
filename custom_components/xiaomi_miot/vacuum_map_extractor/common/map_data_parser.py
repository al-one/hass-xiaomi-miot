import logging

from ..common.image_handler import ImageHandler
from ..common.map_data import ImageData, MapData
from ..const import *

_LOGGER = logging.getLogger(__name__)


class MapDataParser:

    @staticmethod
    def create_empty(colors, text) -> MapData:
        map_data = MapData()
        empty_map = ImageHandler.create_empty_map_image(colors, text)
        map_data.image = ImageData.create_empty(empty_map)
        return map_data

    @staticmethod
    def parse(raw: bytes, colors, drawables, texts, sizes, image_config) -> MapData:
        pass

    @staticmethod
    def draw_elements(colors, drawables, sizes, map_data: MapData, image_config):
        scale = float(image_config[CONF_SCALE])
        for drawable in drawables:
            if DRAWABLE_CHARGER == drawable and map_data.charger is not None:
                ImageHandler.draw_charger(map_data.image, map_data.charger, sizes, colors)
            if DRAWABLE_VACUUM_POSITION == drawable and map_data.vacuum_position is not None:
                ImageHandler.draw_vacuum_position(map_data.image, map_data.vacuum_position, sizes, colors)
            if DRAWABLE_OBSTACLES == drawable and map_data.obstacles is not None:
                ImageHandler.draw_obstacles(map_data.image, map_data.obstacles, sizes, colors)
            if DRAWABLE_IGNORED_OBSTACLES == drawable and map_data.ignored_obstacles is not None:
                ImageHandler.draw_ignored_obstacles(map_data.image, map_data.ignored_obstacles, sizes, colors)
            if DRAWABLE_OBSTACLES_WITH_PHOTO == drawable and map_data.obstacles_with_photo is not None:
                ImageHandler.draw_obstacles_with_photo(map_data.image, map_data.obstacles_with_photo, sizes, colors)
            if DRAWABLE_IGNORED_OBSTACLES_WITH_PHOTO == drawable and map_data.ignored_obstacles_with_photo is not None:
                ImageHandler.draw_ignored_obstacles_with_photo(map_data.image, map_data.ignored_obstacles_with_photo,
                                                               sizes, colors)
            if DRAWABLE_PATH == drawable and map_data.path is not None:
                ImageHandler.draw_path(map_data.image, map_data.path, colors, scale)
            if DRAWABLE_GOTO_PATH == drawable and map_data.goto_path is not None:
                ImageHandler.draw_goto_path(map_data.image, map_data.goto_path, colors, scale)
            if DRAWABLE_PREDICTED_PATH == drawable and map_data.predicted_path is not None:
                ImageHandler.draw_predicted_path(map_data.image, map_data.predicted_path, colors, scale)
            if DRAWABLE_NO_GO_AREAS == drawable and map_data.no_go_areas is not None:
                ImageHandler.draw_no_go_areas(map_data.image, map_data.no_go_areas, colors)
            if DRAWABLE_NO_MOPPING_AREAS == drawable and map_data.no_mopping_areas is not None:
                ImageHandler.draw_no_mopping_areas(map_data.image, map_data.no_mopping_areas, colors)
            if DRAWABLE_VIRTUAL_WALLS == drawable and map_data.walls is not None:
                ImageHandler.draw_walls(map_data.image, map_data.walls, colors)
            if DRAWABLE_ZONES == drawable and map_data.zones is not None:
                ImageHandler.draw_zones(map_data.image, map_data.zones, colors)
            if DRAWABLE_CLEANED_AREA == drawable and DRAWABLE_CLEANED_AREA in map_data.image.additional_layers:
                ImageHandler.draw_layer(map_data.image, drawable)
            if DRAWABLE_ROOM_NAMES == drawable and map_data.rooms is not None:
                ImageHandler.draw_room_names(map_data.image, map_data.rooms, colors)
