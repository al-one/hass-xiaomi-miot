"""coord_type resolves per-report coordinate system for xiaoxun watch (#3058)."""
import logging
from types import SimpleNamespace

from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.device_tracker import MiotTrackerEntity

COORD_TYPE = DEVICE_CUSTOMIZES['xiaoxun.watch.sw773']['coord_type']
# synthetic grid point inside China, not a real location
LAT = 30.0
LNG = 120.0


def make_tracker(hass, maptype):
    ent = object.__new__(MiotTrackerEntity)
    ent.hass = hass
    ent.device = SimpleNamespace(name_model='xiaoxun.watch.sw773')
    ent.logger = logging.getLogger('test')
    ent._state_attrs = {} if maptype is None else {'locationinfo.maptype': maptype}
    ent._attr_latitude = LAT
    ent._attr_longitude = LNG
    ent.custom_config = lambda *args, **kwargs: COORD_TYPE
    return ent


def test_render_coord_type(hass):
    assert make_tracker(hass, 0).render_coord_type(COORD_TYPE) == 'bd09'
    assert make_tracker(hass, '0').render_coord_type(COORD_TYPE) == 'bd09'
    assert make_tracker(hass, 1).render_coord_type(COORD_TYPE) == 'gcj02'
    assert make_tracker(hass, None).render_coord_type(COORD_TYPE) == 'gcj02'


async def test_invalid_template_is_ignored(hass):
    ent = make_tracker(hass, 0)
    assert ent.render_coord_type("{{ data['missing.key']|int }}") == ''


async def test_transform_coord_follows_maptype(hass):
    ent = make_tracker(hass, 0)
    await ent.transform_coord()
    assert (round(ent._attr_latitude, 5), round(ent._attr_longitude, 5)) != (LAT, LNG)
    bd09_lat = ent._attr_latitude

    ent = make_tracker(hass, 1)
    await ent.transform_coord()
    assert round(ent._attr_latitude, 5) != round(bd09_lat, 5)

    ent = make_tracker(hass, 0)
    ent.custom_config = lambda *args, **kwargs: 'bd09'
    await ent.transform_coord()
    assert round(ent._attr_latitude, 6) == round(bd09_lat, 6)
