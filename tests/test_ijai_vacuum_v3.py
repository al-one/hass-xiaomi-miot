"""Coverage for the ijai.vacuum.v3 customization and its cleaning-record template."""

import json

from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.templates import CUSTOM_TEMPLATES, template


def cleaning_record(start, seconds, area, status):
    """Build a `clean-end-ii` (siid 7, eiid 4) cloud record like the Xiaomi cloud returns."""
    arguments = [
        {'piid': 27, 'value': start},
        {'piid': 28, 'value': seconds},
        {'piid': 29, 'value': area},
        {'piid': 31, 'value': 0},
        {'piid': 32, 'value': 0},
        {'piid': 37, 'value': status},
    ]
    return {
        'did': '1',
        'key': '7.4',
        'type': 'event',
        'time': start + seconds,
        'value': json.dumps(arguments),
    }


def test_customization_exposes_cleaning_record_attributes():
    customize = DEVICE_CUSTOMIZES['ijai.vacuum.v3']

    assert customize['miio_cloud_records'] == 'event.7.4:1'
    assert customize['miio_event_7.4_template'] in CUSTOM_TEMPLATES
    assert customize['sensor_attributes'].split(',') == [
        'event.7.4:start',
        'event.7.4:duration',
        'event.7.4:area',
        'event.7.4:result',
    ]
    for prop in ('cleaning_time', 'cleaning_area', 'fault', 'cloth_state'):
        assert prop in customize['sensor_properties'].split(',')
    assert 'mop_route' in customize['select_properties'].split(',')


def test_customization_keeps_the_generic_ijai_entities():
    generic = DEVICE_CUSTOMIZES['ijai.vacuum.*']
    customize = DEVICE_CUSTOMIZES['ijai.vacuum.v3']

    for key in ('sensor_properties', 'switch_properties', 'select_properties'):
        assert set(generic[key].split(',')) <= set(customize[key].split(','))


async def test_clean_record_template(hass):
    result = template('ijai_vacuum_v3_clean_record', hass).async_render({
        'result': [cleaning_record(1789819165, 600, 9, 1)],
    })

    assert result['start'].startswith('2026-09-19')
    assert result['duration'] == 10
    assert result['area'] == 9
    assert result['result'] == 'finished'


async def test_clean_record_template_status_names(hass):
    for status, name in enumerate(['unknown', 'finished', 'stopped_by_app', 'stopped_by_button', 'error']):
        result = template('ijai_vacuum_v3_clean_record', hass).async_render({
            'result': [cleaning_record(1789819165, 60, 1, status)],
        })
        assert result['result'] == name

    result = template('ijai_vacuum_v3_clean_record', hass).async_render({
        'result': [cleaning_record(1789819165, 60, 1, 99)],
    })
    assert result['result'] == 'unknown'


async def test_clean_record_template_without_records(hass):
    result = template('ijai_vacuum_v3_clean_record', hass).async_render({'result': []})

    assert result['start'] is None
    assert result['duration'] == 0
    assert result['area'] == 0
    assert result['result'] == 'unknown'
