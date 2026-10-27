"""Reported conditions share one MIoT enum read, without inventing fault bits."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.helpers.entity import EntityCategory

from custom_components.xiaomi_miot.binary_sensor import BinarySensorEntity
from custom_components.xiaomi_miot.sensor import SensorEntity
from custom_components.xiaomi_miot.core.converters import MiotConditionConv
from custom_components.xiaomi_miot.core.dehumidifier_conditions import DMAKER_22HT_CONDITIONS
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.utils import DeviceException


MODEL = 'dmaker.derh.22ht'
SOURCE = {'siid': 2, 'piid': 2}
MAPPING = {'dehumidifier.fault': SOURCE}


def conditions(device):
    return [c for c in device.converters if isinstance(c, MiotConditionConv)]


@pytest.fixture
def appliance(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f'{MODEL}.json'), model=MODEL)
    entities = [BinarySensorEntity(device, conv) for conv in conditions(device)]
    return device, entities


def report(device, value):
    payload = device.decode([{**SOURCE, 'code': 0, 'value': value}])
    device.dispatch(payload)
    return payload


@pytest.mark.parametrize('code', range(11))
def test_each_reported_enum_value(appliance, code):
    device, entities = appliance
    report(device, code)
    assert len(entities) == 10
    for entity in entities:
        assert entity.available
        assert entity.is_on is (entity.conv.value == code)


def test_transitions_partial_update_and_read_only(appliance):
    device, entities = appliance
    for code in (0, 1, 6, 0):
        report(device, code)
        device.dispatch(device.decode([{'siid': 3, 'piid': 1, 'value': 55}]))
        assert [e.conv.value for e in entities if e.is_on] == ([] if code == 0 else [code])
    assert device.encode({entities[0].attr: True}) == {}


@pytest.mark.parametrize('value', [None, True, False, '1', 1.0, -1, 11, 255, {}, []])
def test_unknown_value_never_clears_a_condition(appliance, value):
    device, entities = appliance
    report(device, 1)
    report(device, value)
    assert all(e.is_on is None and e.available for e in entities)


def test_error_offline_and_restart_are_not_healthy_states(appliance):
    device, entities = appliance
    assert all(e.is_on is None for e in entities)
    report(device, 0)
    assert all(e.get_state() == {} and e.extra_restore_state_data is None for e in entities)
    device.dispatch(device.decode([{**SOURCE, 'code': -704042011}]))
    assert all(not e.available and e.is_on is None for e in entities)
    device.dispatch({'sensor.relative_humidity': 55})
    assert all(not e.available for e in entities)
    report(device, 1)
    device.available = False
    device.dispatch_info()
    assert all(not e.available and e.is_on is None for e in entities)
    device.available = True
    device.dispatch({'sensor.relative_humidity': 56})
    assert all(not e.available for e in entities)
    report(device, 0)
    assert all(e.available and e.is_on is False for e in entities)


async def test_restored_condition_state_is_never_used(appliance):
    _, entities = appliance
    for entity in entities:
        assert await entity.async_get_last_extra_data() is None
        assert entity.is_on is None


@pytest.mark.parametrize('transport', ['local', 'cloud'])
@pytest.mark.parametrize('response', ['success', 'empty', 'absent', 'error', 'exception'])
async def test_requested_source_validity_and_single_transport_call(appliance, transport, response):
    device, entities = appliance
    report(device, 0)
    replies = {
        'success': [{**SOURCE, 'code': 0, 'value': 1}],
        'empty': [],
        'absent': [{'siid': 3, 'piid': 1, 'value': 55, 'code': 0}],
        'error': [{**SOURCE, 'code': -704042011}],
    }
    get = AsyncMock(return_value=replies.get(response))
    if response == 'exception':
        if transport == 'local':
            get.side_effect = DeviceException('failed')
        else:
            from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException
            get.side_effect = MiCloudException('failed')
    client = SimpleNamespace(async_get_properties_for_mapping=get)
    if transport == 'local':
        device.local = client
    else:
        device.cloud = client
    device.offline_notify = AsyncMock()
    await device.update_miot_status(
        mapping=MAPPING, use_local=transport == 'local', use_cloud=transport == 'cloud',
        auto_cloud=False, max_properties=1,
    )
    get.assert_awaited_once()
    assert all(e.available is (response == 'success') for e in entities)
    assert entities[0].is_on is (True if response == 'success' else None)
    # A successful unrelated poll does not revive the failed condition source.
    get.side_effect = None
    get.return_value = [{'siid': 3, 'piid': 1, 'value': 56, 'code': 0}]
    await device.update_miot_status(
        mapping={'environment.relative_humidity': {'siid': 3, 'piid': 1}},
        use_local=transport == 'local', use_cloud=transport == 'cloud',
        auto_cloud=False, max_properties=1,
    )
    assert all(e.available is (response == 'success') for e in entities)


@pytest.mark.parametrize('transport', ['local', 'cloud'])
async def test_overlapping_poll_failure_does_not_invalidate_successful_condition(appliance, transport):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException

    device, entities = appliance
    report(device, 0)
    started, release = asyncio.Event(), asyncio.Event()

    async def get_properties(*args, mapping=None, **kwargs):
        if (mapping if mapping is not None else args[1]) == MAPPING:
            started.set()
            await release.wait()
            return [{**SOURCE, 'code': 0, 'value': 1}]
        raise DeviceException('humidity failed') if transport == 'local' else MiCloudException('humidity failed')

    setattr(device, transport, SimpleNamespace(async_get_properties_for_mapping=get_properties))
    device.offline_notify = AsyncMock()
    options = dict(use_local=transport == 'local', use_cloud=transport == 'cloud',
                   auto_cloud=False, max_properties=1)
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(device.update_miot_status(mapping=MAPPING, **options))
        try:
            await asyncio.wait_for(started.wait(), 5)
            await device.update_miot_status(
                mapping={'environment.relative_humidity': {'siid': 3, 'piid': 1}}, **options,
            )
        finally:
            release.set()
    assert all(e.available for e in entities)
    assert entities[0].is_on is True
    assert all(e.is_on is False for e in entities[1:])


@pytest.mark.parametrize('locale,tank_name', [
    ('en', 'Tank full'), ('zh-Hans', '水箱已满'), ('zh-Hant', '水箱已滿'),
])
def test_display_names_use_home_assistant_translations(appliance, locale, tank_name):
    _, entities = appliance
    data = json.loads(Path(f'custom_components/xiaomi_miot/translations/{locale}.json').read_text())
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
    assert entities[0].name == tank_name


def test_metadata_identity_and_raw_sensor_compatibility(make_device, load_miot_spec):
    spec = load_miot_spec(f'{MODEL}.json')
    device = make_device(spec, model=MODEL, customizes={'sensor_properties': 'fault'})
    entities = [BinarySensorEntity(device, conv) for conv in conditions(device)]
    raw = SensorEntity(device, device.find_converter('sensor.dehumidifier.fault'))
    assert len({e.unique_id for e in entities} | {raw.unique_id}) == 11
    assert len({e.entity_id for e in entities}) == 10
    for entity, (_, key, diagnostic) in zip(entities, DMAKER_22HT_CONDITIONS):
        assert entity.unique_id == f'{device.unique_id}-dehumidifier_{key}'
        assert entity.entity_id.endswith(f'_dehumidifier_{key}')
        assert entity._attr_translation_key == f'dehumidifier_{key}'
        assert entity.device_info == raw.device_info
        assert entity.entity_category == (EntityCategory.DIAGNOSTIC if diagnostic else None)
        assert entity.device_class == (None if key == 'defrosting' else BinarySensorDeviceClass.PROBLEM)
        assert entity.entity_registry_enabled_default
    assert raw.unique_id.endswith('-dehumidifier-2.fault-2')
    report(device, 1)
    assert raw.native_value == 'water full'


@pytest.mark.parametrize('customizes', [
    {'converters': []},
    {'exclude_miot_services': 'dehumidifier'},
    {'exclude_miot_properties': 'fault'},
    {'exclude_miot_properties': 'prop.2.2'},
    {'miot_mapping': {'environment.relative_humidity': {'siid': 3, 'piid': 1}}},
])
def test_explicit_user_exclusions(make_device, load_miot_spec, customizes):
    device = make_device(load_miot_spec(f'{MODEL}.json'), model=MODEL, customizes=customizes)
    assert conditions(device) == []


@pytest.mark.parametrize('mutation', ['model', 'urn', 'source_name', 'format', 'access', 'enum'])
def test_unreviewed_profiles_are_not_expanded(hass, make_device, mutation):
    data = json.loads(Path(f'tests/fixtures/{MODEL}.json').read_text())
    source = data['services'][1]['properties'][1]
    model = MODEL
    if mutation == 'model':
        model = 'dmaker.derh.50l'
    elif mutation == 'urn':
        data['type'] += 'new'
    elif mutation == 'source_name':
        source['type'] = source['type'].replace(':fault:', ':failure:')
    elif mutation == 'enum':
        source['value-list'][0]['value'] = 11
    else:
        source[mutation] = 'bool' if mutation == 'format' else ['notify']
    assert conditions(make_device(MiotSpec(hass, data), model=model)) == []


async def test_mapping_and_polling_are_unchanged(appliance, make_device, load_miot_spec):
    device, _ = appliance
    without = make_device(load_miot_spec(f'{MODEL}.json'), model=MODEL, customizes={'converters': []})
    assert device.miot_mapping() == without.miot_mapping()
    assert list(device.miot_mapping().values()).count(SOURCE) == 1
    assert device.custom_config_integer('interval_seconds') == 120
    # Coordinator creation, without setup, cannot make network requests.
    enabled = await device.init_miot_coordinators(120)
    disabled = await without.init_miot_coordinators(120)
    assert [(c.name, c.update_interval) for c in enabled] == [(c.name, c.update_interval) for c in disabled]


def test_translations_and_official_vendor_label_evidence(appliance):
    _, entities = appliance
    for locale in ('en', 'zh-Hans', 'zh-Hant'):
        data = json.loads(Path(f'custom_components/xiaomi_miot/translations/{locale}.json').read_text())
        assert all(e._attr_translation_key in data['entity']['binary_sensor'] for e in entities)
    data = json.loads(Path(f'tests/fixtures/{MODEL}.languages.json').read_text())['data']
    assert 'humidity' in data['en']['service:002:property:002:valuelist:002'].lower()
    assert '铜管' in data['zh_cn']['service:002:property:002:valuelist:003']
