import logging
from typing import Dict, Optional, Set, Tuple

from PIL import Image
from PIL.Image import Image as ImageType

from ..common.image_handler import ImageHandler
from ..const import *

_LOGGER = logging.getLogger(__name__)


class ImageHandlerViomi(ImageHandler):
    MAP_OUTSIDE = 0x00
    MAP_WALL = 0xff
    MAP_SCAN = 0x01
    MAP_ROOM_MIN = 10
    MAP_ROOM_MAX = 59
    MAP_SELECTED_ROOM_MIN = 60
    MAP_SELECTED_ROOM_MAX = 109

    @staticmethod
    def parse(buf, width, height, colors, image_config, draw_cleaned_area) \
            -> Tuple[ImageType, Dict[int, Tuple[int, int, int, int]], Set[int], Optional[ImageType]]:
        rooms = {}
        cleaned_areas = set()
        scale = image_config[CONF_SCALE]
        trim_left = int(image_config[CONF_TRIM][CONF_LEFT] * width / 100)
        trim_right = int(image_config[CONF_TRIM][CONF_RIGHT] * width / 100)
        trim_top = int(image_config[CONF_TRIM][CONF_TOP] * height / 100)
        trim_bottom = int(image_config[CONF_TRIM][CONF_BOTTOM] * height / 100)
        trimmed_height = height - trim_top - trim_bottom
        trimmed_width = width - trim_left - trim_right
        if trimmed_width == 0 or trimmed_height == 0:
            return ImageHandler.create_empty_map_image(colors), rooms, cleaned_areas, None
        image = Image.new('RGBA', (trimmed_width, trimmed_height))
        pixels = image.load()
        cleaned_areas_layer = None
        cleaned_areas_pixels = None
        if draw_cleaned_area:
            cleaned_areas_layer = Image.new('RGBA', (trimmed_width, trimmed_height))
            cleaned_areas_pixels = cleaned_areas_layer.load()
        buf.skip('trim_bottom', trim_bottom * width)
        unknown_pixels = set()
        for img_y in range(trimmed_height):
            buf.skip('trim_left', trim_left)
            for img_x in range(trimmed_width):
                pixel_type = buf.get_uint8('pixel')
                x = img_x
                y = trimmed_height - 1 - img_y
                if pixel_type == ImageHandlerViomi.MAP_OUTSIDE:
                    pixels[x, y] = ImageHandler.__get_color__(COLOR_MAP_OUTSIDE, colors)
                elif pixel_type == ImageHandlerViomi.MAP_WALL:
                    pixels[x, y] = ImageHandler.__get_color__(COLOR_MAP_WALL_V2, colors)
                elif pixel_type == ImageHandlerViomi.MAP_SCAN:
                    pixels[x, y] = ImageHandler.__get_color__(COLOR_SCAN, colors)
                elif ImageHandlerViomi.MAP_ROOM_MIN <= pixel_type <= ImageHandlerViomi.MAP_SELECTED_ROOM_MAX:
                    room_x = img_x + trim_left
                    room_y = img_y + trim_bottom
                    if pixel_type < ImageHandlerViomi.MAP_SELECTED_ROOM_MIN:
                        room_number = pixel_type
                    else:
                        room_number = pixel_type - ImageHandlerViomi.MAP_SELECTED_ROOM_MIN + ImageHandlerViomi.MAP_ROOM_MIN
                        cleaned_areas.add(room_number)
                        if draw_cleaned_area:
                            cleaned_areas_pixels[x, y] = ImageHandler.__get_color__(COLOR_CLEANED_AREA, colors)
                    if room_number not in rooms:
                        rooms[room_number] = (room_x, room_y, room_x, room_y)
                    else:
                        rooms[room_number] = (min(rooms[room_number][0], room_x),
                                              min(rooms[room_number][1], room_y),
                                              max(rooms[room_number][2], room_x),
                                              max(rooms[room_number][3], room_y))
                    default = ImageHandler.ROOM_COLORS[room_number % len(ImageHandler.ROOM_COLORS)]
                    pixels[x, y] = ImageHandler.__get_color__(f"{COLOR_ROOM_PREFIX}{room_number}", colors, default)
                else:
                    pixels[x, y] = ImageHandler.__get_color__(COLOR_UNKNOWN, colors)
                    unknown_pixels.add(pixel_type)
            buf.skip('trim_right', trim_right)
        buf.skip('trim_top', trim_top * width)
        if image_config["scale"] != 1 and trimmed_width != 0 and trimmed_height != 0:
            image = image.resize((int(trimmed_width * scale), int(trimmed_height * scale)), resample=Image.NEAREST)
            if draw_cleaned_area:
                cleaned_areas_layer = cleaned_areas_layer.resize(
                    (int(trimmed_width * scale), int(trimmed_height * scale)), resample=Image.NEAREST)
        if len(unknown_pixels) > 0:
            _LOGGER.warning('unknown pixel_types: %s', unknown_pixels)
        return image, rooms, cleaned_areas, cleaned_areas_layer
