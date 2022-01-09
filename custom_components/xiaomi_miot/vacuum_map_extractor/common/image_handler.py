import logging
from typing import Callable

from PIL import Image, ImageDraw, ImageFont
from PIL.Image import Image as ImageType

from ..common.map_data import ImageData
from ..const import *

_LOGGER = logging.getLogger(__name__)


class ImageHandler:
    COLORS = {
        COLOR_MAP_INSIDE: (32, 115, 185),
        COLOR_MAP_OUTSIDE: (19, 87, 148),
        COLOR_MAP_WALL: (100, 196, 254),
        COLOR_MAP_WALL_V2: (93, 109, 126),
        COLOR_GREY_WALL: (93, 109, 126),
        COLOR_CLEANED_AREA: (127, 127, 127, 127),
        COLOR_PATH: (147, 194, 238),
        COLOR_GOTO_PATH: (0, 255, 0),
        COLOR_PREDICTED_PATH: (255, 255, 0),
        COLOR_ZONES: (0xAD, 0xD8, 0xFF, 0x8F),
        COLOR_ZONES_OUTLINE: (0xAD, 0xD8, 0xFF),
        COLOR_VIRTUAL_WALLS: (255, 0, 0),
        COLOR_NEW_DISCOVERED_AREA: (64, 64, 64),
        COLOR_NO_GO_ZONES: (255, 33, 55, 127),
        COLOR_NO_GO_ZONES_OUTLINE: (255, 0, 0),
        COLOR_NO_MOPPING_ZONES: (163, 130, 211, 127),
        COLOR_NO_MOPPING_ZONES_OUTLINE: (163, 130, 211),
        COLOR_CHARGER: (0x66, 0xfe, 0xda, 0x7f),
        COLOR_ROBO: (75, 235, 149),
        COLOR_ROOM_NAMES: (0, 0, 0),
        COLOR_OBSTACLE: (0, 0, 0, 128),
        COLOR_IGNORED_OBSTACLE: (0, 0, 0, 128),
        COLOR_OBSTACLE_WITH_PHOTO: (0, 0, 0, 128),
        COLOR_IGNORED_OBSTACLE_WITH_PHOTO: (0, 0, 0, 128),
        COLOR_UNKNOWN: (0, 0, 0),
        COLOR_SCAN: (0xDF, 0xDF, 0xDF),
        COLOR_ROOM_1: (240, 178, 122),
        COLOR_ROOM_2: (133, 193, 233),
        COLOR_ROOM_3: (217, 136, 128),
        COLOR_ROOM_4: (52, 152, 219),
        COLOR_ROOM_5: (205, 97, 85),
        COLOR_ROOM_6: (243, 156, 18),
        COLOR_ROOM_7: (88, 214, 141),
        COLOR_ROOM_8: (245, 176, 65),
        COLOR_ROOM_9: (252, 212, 81),
        COLOR_ROOM_10: (72, 201, 176),
        COLOR_ROOM_11: (84, 153, 199),
        COLOR_ROOM_12: (133, 193, 233),
        COLOR_ROOM_13: (245, 176, 65),
        COLOR_ROOM_14: (82, 190, 128),
        COLOR_ROOM_15: (72, 201, 176),
        COLOR_ROOM_16: (165, 105, 189)
    }
    ROOM_COLORS = [COLOR_ROOM_1, COLOR_ROOM_2, COLOR_ROOM_3, COLOR_ROOM_4, COLOR_ROOM_5, COLOR_ROOM_6, COLOR_ROOM_7,
                   COLOR_ROOM_8, COLOR_ROOM_9, COLOR_ROOM_10, COLOR_ROOM_11, COLOR_ROOM_12, COLOR_ROOM_13,
                   COLOR_ROOM_14, COLOR_ROOM_15, COLOR_ROOM_16]

    @staticmethod
    def create_empty_map_image(colors, text="NO MAP") -> ImageType:
        color = ImageHandler.__get_color__(COLOR_MAP_OUTSIDE, colors)
        image = Image.new('RGBA', (300, 200), color=color)
        if sum(color[0:3]) > 382:
            text_color = (0, 0, 0)
        else:
            text_color = (255, 255, 255)
        draw = ImageDraw.Draw(image, "RGBA")
        w, h = draw.textsize(text)
        draw.text(((image.size[0] - w) / 2, (image.size[1] - h) / 2), text, fill=text_color)
        return image

    @staticmethod
    def draw_path(image: ImageData, path, colors, scale):
        ImageHandler.__draw_path__(image, path, ImageHandler.__get_color__(COLOR_PATH, colors), scale)

    @staticmethod
    def draw_goto_path(image: ImageData, path, colors, scale):
        ImageHandler.__draw_path__(image, path, ImageHandler.__get_color__(COLOR_GOTO_PATH, colors), scale)

    @staticmethod
    def draw_predicted_path(image: ImageData, path, colors, scale):
        ImageHandler.__draw_path__(image, path, ImageHandler.__get_color__(COLOR_PREDICTED_PATH, colors), scale)

    @staticmethod
    def draw_no_go_areas(image: ImageData, areas, colors):
        ImageHandler.__draw_areas__(image, areas,
                                    ImageHandler.__get_color__(COLOR_NO_GO_ZONES, colors),
                                    ImageHandler.__get_color__(COLOR_NO_GO_ZONES_OUTLINE, colors))

    @staticmethod
    def draw_no_mopping_areas(image: ImageData, areas, colors):
        ImageHandler.__draw_areas__(image, areas,
                                    ImageHandler.__get_color__(COLOR_NO_MOPPING_ZONES, colors),
                                    ImageHandler.__get_color__(COLOR_NO_MOPPING_ZONES_OUTLINE, colors))

    @staticmethod
    def draw_walls(image: ImageData, walls, colors):
        draw = ImageDraw.Draw(image.data, 'RGBA')
        for wall in walls:
            draw.line(wall.to_img(image.dimensions).as_list(),
                      ImageHandler.__get_color__(COLOR_VIRTUAL_WALLS, colors), width=2)

    @staticmethod
    def draw_zones(image: ImageData, zones, colors):
        areas = list(map(lambda z: z.as_area(), zones))
        ImageHandler.__draw_areas__(image, areas,
                                    ImageHandler.__get_color__(COLOR_ZONES, colors),
                                    ImageHandler.__get_color__(COLOR_ZONES_OUTLINE, colors))

    @staticmethod
    def draw_charger(image: ImageData, charger, sizes, colors):
        color = ImageHandler.__get_color__(COLOR_CHARGER, colors)
        radius = sizes[CONF_SIZE_CHARGER_RADIUS]
        ImageHandler.__draw_circle__(image, charger, radius, color, color)

    @staticmethod
    def draw_obstacles(image: ImageData, obstacles, sizes, colors):
        color = ImageHandler.__get_color__(COLOR_OBSTACLE, colors)
        radius = sizes[CONF_SIZE_OBSTACLE_RADIUS]
        ImageHandler.draw_all_obstacles(image, obstacles, radius, color)

    @staticmethod
    def draw_ignored_obstacles(image: ImageData, obstacles, sizes, colors):
        color = ImageHandler.__get_color__(COLOR_IGNORED_OBSTACLE, colors)
        radius = sizes[CONF_SIZE_IGNORED_OBSTACLE_RADIUS]
        ImageHandler.draw_all_obstacles(image, obstacles, radius, color)

    @staticmethod
    def draw_obstacles_with_photo(image: ImageData, obstacles, sizes, colors):
        color = ImageHandler.__get_color__(COLOR_OBSTACLE_WITH_PHOTO, colors)
        radius = sizes[CONF_SIZE_OBSTACLE_WITH_PHOTO_RADIUS]
        ImageHandler.draw_all_obstacles(image, obstacles, radius, color)

    @staticmethod
    def draw_ignored_obstacles_with_photo(image: ImageData, obstacles, sizes, colors):
        color = ImageHandler.__get_color__(COLOR_IGNORED_OBSTACLE_WITH_PHOTO, colors)
        radius = sizes[CONF_SIZE_IGNORED_OBSTACLE_WITH_PHOTO_RADIUS]
        ImageHandler.draw_all_obstacles(image, obstacles, radius, color)

    @staticmethod
    def draw_all_obstacles(image: ImageData, obstacles, radius, color):
        for obstacle in obstacles:
            ImageHandler.__draw_circle__(image, obstacle, radius, color, color)

    @staticmethod
    def draw_vacuum_position(image: ImageData, vacuum_position, sizes, colors):
        color = ImageHandler.__get_color__(COLOR_ROBO, colors)
        radius = sizes[CONF_SIZE_VACUUM_RADIUS]
        ImageHandler.__draw_circle__(image, vacuum_position, radius, color, color)

    @staticmethod
    def draw_room_names(image: ImageData, rooms, colors):
        color = ImageHandler.__get_color__(COLOR_ROOM_NAMES, colors)
        for room in rooms.values():
            p = room.point()
            if p is not None:
                point = p.to_img(image.dimensions)
                ImageHandler.__draw_text__(image, room.name, point.x, point.y, color)

    @staticmethod
    def rotate(image: ImageData):
        if image.dimensions.rotation == 90:
            image.data = image.data.transpose(Image.ROTATE_90)
        if image.dimensions.rotation == 180:
            image.data = image.data.transpose(Image.ROTATE_180)
        if image.dimensions.rotation == 270:
            image.data = image.data.transpose(Image.ROTATE_270)

    @staticmethod
    def draw_texts(image: ImageData, texts):
        for text_config in texts:
            x = text_config[CONF_X] * image.data.size[0] / 100
            y = text_config[CONF_Y] * image.data.size[1] / 100
            ImageHandler.__draw_text__(image, text_config[CONF_TEXT], x, y, text_config[CONF_COLOR],
                                       text_config[CONF_FONT], text_config[CONF_FONT_SIZE])

    @staticmethod
    def draw_layer(image: ImageData, layer_name):
        ImageHandler.__draw_layer__(image, image.additional_layers[layer_name])

    @staticmethod
    def __draw_circle__(image: ImageData, center, r, outline, fill):
        def draw_func(draw: ImageDraw):
            point = center.to_img(image.dimensions)
            coords = [point.x - r, point.y - r, point.x + r, point.y + r]
            draw.ellipse(coords, outline=outline, fill=fill)

        ImageHandler.__draw_on_new_layer__(image, draw_func)

    @staticmethod
    def __draw_areas__(image: ImageData, areas, fill, outline):
        if len(areas) == 0:
            return
        for area in areas:
            def draw_func(draw: ImageDraw):
                draw.polygon(area.to_img(image.dimensions).as_list(), fill, outline)

            ImageHandler.__draw_on_new_layer__(image, draw_func)

    @staticmethod
    def __draw_path__(image: ImageData, path, color, scale):
        if len(path.path) < 2:
            return

        def draw_func(draw: ImageDraw):
            s = path.path[0].to_img(image.dimensions)
            for point in path.path[1:]:
                e = point.to_img(image.dimensions)
                draw.line([s.x * scale, s.y * scale, e.x * scale, e.y * scale], width=int(scale), fill=color)
                s = e

        ImageHandler.__draw_on_new_layer__(image, draw_func, scale)

    @staticmethod
    def __draw_text__(image: ImageData, text, x, y, color, font_file=None, font_size=None):
        def draw_func(draw: ImageDraw):
            font = ImageFont.load_default()
            try:
                if font_file is not None and font_size > 0:
                    font = ImageFont.truetype(font_file, font_size)
            except OSError:
                _LOGGER.warning("Unable to find font file: %s", font_file)
            except ImportError:
                _LOGGER.warning("Unable to open font: %s", font_file)
            finally:
                w, h = draw.textsize(text, font)
                draw.text((x - w / 2, y - h / 2), text, font=font, fill=color)

        ImageHandler.__draw_on_new_layer__(image, draw_func)

    @staticmethod
    def __get_color__(name, colors, default_name=None):
        if name in colors:
            return colors[name]
        if default_name is None:
            return ImageHandler.COLORS[name]
        return ImageHandler.COLORS[default_name]

    @staticmethod
    def __draw_on_new_layer__(image: ImageData, draw_function: Callable, scale=1):
        if scale == 1:
            size = image.data.size
        else:
            size = [int(image.data.size[0] * scale), int(image.data.size[1] * scale)]
        layer = Image.new("RGBA", size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(layer, "RGBA")
        draw_function(draw)
        if scale != 1:
            layer = layer.resize(image.data.size, resample=Image.BOX)
        ImageHandler.__draw_layer__(image, layer)

    @staticmethod
    def __draw_layer__(image: ImageData, layer: ImageType):
        image.data = Image.alpha_composite(image.data, layer)
