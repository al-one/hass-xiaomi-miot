"""Verify named conditions, failed readings, and the Home Assistant entity lifecycle."""

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.restore_state import RestoreEntity, RestoredExtraData

from custom_components.xiaomi_miot.binary_sensor import BinarySensorEntity
from custom_components.xiaomi_miot.sensor import SensorEntity
from custom_components.xiaomi_miot.core.converters import BaseConv, MiotConditionConv
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.utils import DeviceException


MODEL = 'dmaker.derh.22ht'
FAULT_PROPERTY_ADDRESS = {'siid': 2, 'piid': 2}
FAULT_PROPERTY_MAPPING = {'dehumidifier.fault': FAULT_PROPERTY_ADDRESS}
TRANSLATIONS_DIRECTORY = Path('custom_components/xiaomi_miot/translations')
EXPECTED_CONDITIONS = {
    1: ('tank_full', None),
    2: ('temperature_humidity_sensor_fault', EntityCategory.DIAGNOSTIC),
    3: ('coil_temperature_sensor_fault', EntityCategory.DIAGNOSTIC),
    4: ('internal_communication_fault', EntityCategory.DIAGNOSTIC),
    5: ('filter_cleaning_due', None),
    6: ('defrosting', None),
    7: ('fan_fault', EntityCategory.DIAGNOSTIC),
    8: ('compressor_overload_protection', EntityCategory.DIAGNOSTIC),
    9: ('low_refrigerant_protection', EntityCategory.DIAGNOSTIC),
    10: ('operating_temperature_out_of_range', None),
}


def get_condition_converters(device):
    return [converter for converter in device.converters if isinstance(converter, MiotConditionConv)]


@pytest.fixture
def dehumidifier(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f'{MODEL}.json'), model=MODEL)
    entities = []
    device.entry.adders['binary_sensor'] = lambda new_entities, **kwargs: entities.extend(new_entities)
    device.add_entities('binary_sensor')
    return device, entities


def report_condition_code(device, reported_code):
    payload = device.decode([{**FAULT_PROPERTY_ADDRESS, 'code': 0, 'value': reported_code}])
    device.dispatch(payload)
    return payload


async def test_device_readings_update_home_assistant_states(hass, dehumidifier):
    device, entities = dehumidifier
    component = EntityComponent(logging.getLogger(__name__), 'binary_sensor', hass)
    component.register_shutdown()
    await component.async_add_entities(entities)
    tank_full = entities[0]

    assert hass.states.get(tank_full.entity_id).state == STATE_UNKNOWN
    report_condition_code(device, 1)
    assert hass.states.get(tank_full.entity_id).state == STATE_ON
    device.dispatch(device.decode([{**FAULT_PROPERTY_ADDRESS, 'code': -704042011}]))
    assert hass.states.get(tank_full.entity_id).state == STATE_UNAVAILABLE
    report_condition_code(device, 0)
    assert hass.states.get(tank_full.entity_id).state == STATE_OFF


@pytest.mark.parametrize('code', range(11))
def test_each_status_code_activates_the_correct_named_entity(dehumidifier, code):
    device, entities = dehumidifier
    report_condition_code(device, code)
    assert len(entities) == 10
    expected_key = EXPECTED_CONDITIONS[code][0] if code else None
    for entity in entities:
        assert entity.available
        assert entity.is_on is (entity.attr == f'binary_sensor.dehumidifier_{expected_key}')


def test_humidity_updates_preserve_the_last_reported_condition(dehumidifier):
    device, entities = dehumidifier
    for code, expected_key in ((0, None), (1, 'tank_full'), (6, 'defrosting'), (0, None)):
        report_condition_code(device, code)
        device.dispatch(device.decode([{'siid': 3, 'piid': 1, 'value': 55}]))
        active_entities = [entity.attr for entity in entities if entity.is_on]
        assert active_entities == ([f'binary_sensor.dehumidifier_{expected_key}'] if expected_key else [])


def test_condition_entities_cannot_send_device_commands(dehumidifier):
    device, entities = dehumidifier
    assert device.encode({entities[0].attr: True}) == {}


@pytest.mark.parametrize('value', [None, True, False, '1', 1.0, -1, 11, 255, {}, []])
def test_unknown_value_never_clears_a_condition(dehumidifier, value):
    device, entities = dehumidifier
    report_condition_code(device, 1)
    report_condition_code(device, value)
    assert all(e.is_on is None and e.available for e in entities)


def test_failed_status_reads_and_offline_recovery_require_a_fresh_reading(dehumidifier):
    device, entities = dehumidifier
    assert all(e.is_on is None for e in entities)
    report_condition_code(device, 0)
    assert all(e.get_state() == {} and e.extra_restore_state_data is None for e in entities)
    device.dispatch(device.decode([{**FAULT_PROPERTY_ADDRESS, 'code': -704042011}]))
    assert all(not e.available and e.is_on is None for e in entities)
    device.dispatch({'sensor.relative_humidity': 55})
    assert all(not e.available for e in entities)
    report_condition_code(device, 1)
    device.available = False
    device.dispatch_info()
    assert all(not e.available and e.is_on is None for e in entities)
    device.available = True
    device.dispatch({'sensor.relative_humidity': 56})
    assert all(not e.available for e in entities)
    report_condition_code(device, 0)
    assert all(e.available and e.is_on is False for e in entities)


async def test_restart_does_not_restore_an_old_tank_not_full_reading(dehumidifier, monkeypatch):
    _, entities = dehumidifier
    tank_full = entities[0]
    saved_reading = RestoredExtraData({tank_full.attr: False})
    restore_saved_reading = AsyncMock(return_value=saved_reading)
    monkeypatch.setattr(RestoreEntity, 'async_get_last_extra_data', restore_saved_reading)

    await tank_full.async_added_to_hass()

    assert tank_full.is_on is None
    assert tank_full.extra_restore_state_data is None
    restore_saved_reading.assert_not_awaited()


async def test_other_binary_sensors_still_restore_their_state(dehumidifier, monkeypatch):
    device, _ = dehumidifier
    sensor = BinarySensorEntity(device, BaseConv('door_open', 'binary_sensor'))
    saved_reading = RestoredExtraData({sensor.attr: True})
    restore_saved_reading = AsyncMock(return_value=saved_reading)
    monkeypatch.setattr(RestoreEntity, 'async_get_last_extra_data', restore_saved_reading)

    await sensor.async_added_to_hass()

    assert sensor.is_on is True
    restore_saved_reading.assert_awaited_once()


@pytest.mark.parametrize('transport', ['local', 'cloud'])
@pytest.mark.parametrize('response_kind', ['success', 'empty', 'absent', 'error', 'exception'])
async def test_requested_status_read_controls_availability_with_one_request(dehumidifier, transport, response_kind):
    device, entities = dehumidifier
    report_condition_code(device, 0)
    property_responses = {
        'success': [{**FAULT_PROPERTY_ADDRESS, 'code': 0, 'value': 1}],
        'empty': [],
        'absent': [{'siid': 3, 'piid': 1, 'value': 55, 'code': 0}],
        'error': [{**FAULT_PROPERTY_ADDRESS, 'code': -704042011}],
    }
    read_properties = AsyncMock(return_value=property_responses.get(response_kind))
    if response_kind == 'exception':
        if transport == 'local':
            read_properties.side_effect = DeviceException('failed')
        else:
            from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException
            read_properties.side_effect = MiCloudException('failed')
    client = SimpleNamespace(async_get_properties_for_mapping=read_properties)
    if transport == 'local':
        device.local = client
    else:
        device.cloud = client
    device.offline_notify = AsyncMock()
    await device.update_miot_status(
        mapping=FAULT_PROPERTY_MAPPING, use_local=transport == 'local', use_cloud=transport == 'cloud',
        auto_cloud=False, max_properties=1,
    )
    read_properties.assert_awaited_once()
    assert all(e.available is (response_kind == 'success') for e in entities)
    assert entities[0].is_on is (True if response_kind == 'success' else None)
    # Reading humidity successfully does not make a failed status reading available.
    read_properties.side_effect = None
    read_properties.return_value = [{'siid': 3, 'piid': 1, 'value': 56, 'code': 0}]
    await device.update_miot_status(
        mapping={'environment.relative_humidity': {'siid': 3, 'piid': 1}},
        use_local=transport == 'local', use_cloud=transport == 'cloud',
        auto_cloud=False, max_properties=1,
    )
    assert all(e.available is (response_kind == 'success') for e in entities)


@pytest.mark.parametrize('transport', ['local', 'cloud'])
async def test_overlapping_poll_failure_does_not_invalidate_successful_condition(dehumidifier, transport):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException

    device, entities = dehumidifier
    report_condition_code(device, 0)
    condition_read_started, allow_condition_read_to_finish = asyncio.Event(), asyncio.Event()

    async def read_properties(*args, mapping=None, **kwargs):
        if (mapping if mapping is not None else args[1]) == FAULT_PROPERTY_MAPPING:
            condition_read_started.set()
            await allow_condition_read_to_finish.wait()
            return [{**FAULT_PROPERTY_ADDRESS, 'code': 0, 'value': 1}]
        raise DeviceException('humidity failed') if transport == 'local' else MiCloudException('humidity failed')

    setattr(device, transport, SimpleNamespace(async_get_properties_for_mapping=read_properties))
    device.offline_notify = AsyncMock()
    connection_options = {
        'use_local': transport == 'local', 'use_cloud': transport == 'cloud',
        'auto_cloud': False, 'max_properties': 1,
    }
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(device.update_miot_status(mapping=FAULT_PROPERTY_MAPPING, **connection_options))
        try:
            await asyncio.wait_for(condition_read_started.wait(), 5)
            await device.update_miot_status(
                mapping={'environment.relative_humidity': {'siid': 3, 'piid': 1}}, **connection_options,
            )
        finally:
            allow_condition_read_to_finish.set()
    assert all(e.available for e in entities)
    assert entities[0].is_on is True
    assert all(e.is_on is False for e in entities[1:])


@pytest.mark.parametrize('locale', sorted(path.stem for path in TRANSLATIONS_DIRECTORY.glob('*.json')))
def test_display_names_use_home_assistant_translations(dehumidifier, locale):
    _, entities = dehumidifier
    data = json.loads((TRANSLATIONS_DIRECTORY / f'{locale}.json').read_text())
    names = data['entity']['binary_sensor']
    platform = SimpleNamespace(
        domain='binary_sensor', platform_name='xiaomi_miot', component_translations={},
        platform_translations={
            f'component.xiaomi_miot.entity.binary_sensor.{key}.name': value['name']
            for key, value in names.items() if 'name' in value
        },
    )
    for entity in entities:
        entity.platform = platform
        assert entity.name == names[entity.translation_key]['name']
    expected_tank_names = {'en': 'Tank full', 'zh-Hans': '水箱已满', 'zh-Hant': '水箱已滿'}
    if locale in expected_tank_names:
        assert entities[0].name == expected_tank_names[locale]


def test_metadata_identity_and_raw_sensor_compatibility(make_device, load_miot_spec):
    spec = load_miot_spec(f'{MODEL}.json')
    device = make_device(spec, model=MODEL, customizes={'sensor_properties': 'fault'})
    entities = [BinarySensorEntity(device, conv) for conv in get_condition_converters(device)]
    raw_fault_sensor = SensorEntity(device, device.find_converter('sensor.dehumidifier.fault'))
    assert len({e.unique_id for e in entities} | {raw_fault_sensor.unique_id}) == 11
    assert len({e.entity_id for e in entities}) == 10
    entities_by_key = {entity.conv.attr: entity for entity in entities}
    for key, entity_category in EXPECTED_CONDITIONS.values():
        entity = entities_by_key[f'dehumidifier_{key}']
        assert entity.unique_id == f'{device.unique_id}-dehumidifier_{key}'
        assert entity.entity_id.endswith(f'_dehumidifier_{key}')
        assert entity._attr_translation_key == f'dehumidifier_{key}'
        assert entity.device_info == raw_fault_sensor.device_info
        assert entity.entity_category == entity_category
        assert entity.device_class == (None if key == 'defrosting' else BinarySensorDeviceClass.PROBLEM)
        assert entity.entity_registry_enabled_default
    assert raw_fault_sensor.unique_id.endswith('-dehumidifier-2.fault-2')
    report_condition_code(device, 1)
    assert raw_fault_sensor.native_value == 'water full'


@pytest.mark.parametrize('customizes', [
    {'converters': []},
    {'exclude_miot_services': 'dehumidifier'},
    {'exclude_miot_properties': 'fault'},
    {'exclude_miot_properties': 'prop.2.2'},
    {'miot_mapping': {'environment.relative_humidity': {'siid': 3, 'piid': 1}}},
])
def test_explicit_user_exclusions(make_device, load_miot_spec, customizes):
    device = make_device(load_miot_spec(f'{MODEL}.json'), model=MODEL, customizes=customizes)
    assert get_condition_converters(device) == []


@pytest.mark.parametrize('mutation', [
    'model', 'urn', 'source_name', 'format', 'access', 'unknown_code', 'boolean_code', 'missing_code',
])
def test_other_models_and_incompatible_properties_have_no_condition_sensors(hass, make_device, mutation):
    data = json.loads(Path(f'tests/fixtures/{MODEL}.json').read_text())
    fault_property_schema = data['services'][1]['properties'][1]
    model = MODEL
    if mutation == 'model':
        model = 'dmaker.derh.50l'
    elif mutation == 'urn':
        data['type'] += 'new'
    elif mutation == 'source_name':
        fault_property_schema['type'] = fault_property_schema['type'].replace(':fault:', ':failure:')
    elif mutation == 'unknown_code':
        fault_property_schema['value-list'][0]['value'] = 11
    elif mutation == 'boolean_code':
        fault_property_schema['value-list'][0]['value'] = False
    elif mutation == 'missing_code':
        fault_property_schema['value-list'].pop()
    else:
        fault_property_schema[mutation] = 'bool' if mutation == 'format' else ['notify']
    assert get_condition_converters(make_device(MiotSpec(hass, data), model=model)) == []


async def test_mapping_and_polling_are_unchanged(dehumidifier, make_device, load_miot_spec):
    device, _ = dehumidifier
    device_without_condition_sensors = make_device(
        load_miot_spec(f'{MODEL}.json'), model=MODEL, customizes={'converters': []},
    )
    assert device.miot_mapping() == device_without_condition_sensors.miot_mapping()
    assert list(device.miot_mapping().values()).count(FAULT_PROPERTY_ADDRESS) == 1
    assert device.custom_config_integer('interval_seconds') == 120
    # Compare the real polling schedules; creating coordinators does not perform a read.
    condition_coordinators = await device.init_miot_coordinators(120)
    baseline_coordinators = await device_without_condition_sensors.init_miot_coordinators(120)
    assert [(coordinator.name, coordinator.update_interval) for coordinator in condition_coordinators] == [
        (coordinator.name, coordinator.update_interval) for coordinator in baseline_coordinators
    ]
