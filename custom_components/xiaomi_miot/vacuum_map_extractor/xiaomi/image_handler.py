import logging
from typing import Tuple

from PIL import Image
from PIL.Image import Image as ImageType

from ..common.image_handler import ImageHandler
from ..const import *

_LOGGER = logging.getLogger(__name__)


class ImageHandlerXiaomi(ImageHandler):
    MAP_OUTSIDE = 0x00
    MAP_WALL = 0x01
    MAP_INSIDE = 0xFF
    MAP_SCAN = 0x07

    @staticmethod
    def parse(raw_data: bytes, width, height, colors, image_config) -> Tuple[ImageType, dict]:
        rooms = {}
        scale = image_config[CONF_SCALE]
        trim_left = int(image_config[CONF_TRIM][CONF_LEFT] * width / 100)
        trim_right = int(image_config[CONF_TRIM][CONF_RIGHT] * width / 100)
        trim_top = int(image_config[CONF_TRIM][CONF_TOP] * height / 100)
        trim_bottom = int(image_config[CONF_TRIM][CONF_BOTTOM] * height / 100)
        trimmed_height = height - trim_top - trim_bottom
        trimmed_width = width - trim_left - trim_right
        image = Image.new('RGBA', (trimmed_width, trimmed_height))
        if width == 0 or height == 0:
            return ImageHandler.create_empty_map_image(colors), {}
        pixels = image.load()
        for img_y in range(trimmed_height):
            for img_x in range(trimmed_width):
                pixel_type = raw_data[img_x + trim_left + width * (img_y + trim_bottom)]
                x = img_x
                y = trimmed_height - img_y - 1
                if pixel_type == ImageHandlerXiaomi.MAP_OUTSIDE:
                    pixels[x, y] = ImageHandler.__get_color__(COLOR_MAP_OUTSIDE, colors)
                elif pixel_type == ImageHandlerXiaomi.MAP_WALL:
                    pixels[x, y] = ImageHandler.__get_color__(COLOR_MAP_WALL, colors)
                elif pixel_type == ImageHandlerXiaomi.MAP_INSIDE:
                    pixels[x, y] = ImageHandler.__get_color__(COLOR_MAP_INSIDE, colors)
                elif pixel_type == ImageHandlerXiaomi.MAP_SCAN:
                    pixels[x, y] = ImageHandler.__get_color__(COLOR_SCAN, colors)
                else:
                    obstacle = pixel_type & 0x07
                    if obstacle == 0:
                        pixels[x, y] = ImageHandler.__get_color__(COLOR_GREY_WALL, colors)
                    elif obstacle == 1:
                        pixels[x, y] = ImageHandler.__get_color__(COLOR_MAP_WALL_V2, colors)
                    elif obstacle == 7:
                        room_number = (pixel_type & 0xFF) >> 3
                        room_x = img_x + trim_left
                        room_y = img_y + trim_bottom
                        if room_number not in rooms:
                            rooms[room_number] = (room_x, room_y, room_x, room_y)
                        else:
                            rooms[room_number] = (min(rooms[room_number][0], room_x),
                                                  min(rooms[room_number][1], room_y),
                                                  max(rooms[room_number][2], room_x),
                                                  max(rooms[room_number][3], room_y))
                        default = ImageHandler.ROOM_COLORS[room_number >> 1]
                        pixels[x, y] = ImageHandler.__get_color__(f"{COLOR_ROOM_PREFIX}{room_number}", colors, default)
                    else:
                        pixels[x, y] = ImageHandler.__get_color__(COLOR_UNKNOWN, colors)
        if image_config["scale"] != 1 and width != 0 and height != 0:
            image = image.resize((int(trimmed_width * scale), int(trimmed_height * scale)), resample=Image.NEAREST)
        return image, rooms

    @staticmethod
    def get_room_at_pixel(raw_data: bytes, width, x, y):
        room_number = None
        pixel_type = raw_data[x + width * y]
        if pixel_type not in [ImageHandlerXiaomi.MAP_INSIDE, ImageHandlerXiaomi.MAP_SCAN]:
            if pixel_type & 0x07 == 7:
                room_number = (pixel_type & 0xFF) >> 3
        return room_number
