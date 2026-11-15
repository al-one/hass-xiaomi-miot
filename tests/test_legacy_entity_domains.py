"""Suggested legacy IDs must use their HA platform without renaming registry entries."""
from datetime import timedelta
from importlib import import_module
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_DEVICE
from homeassistant.helpers import area_registry as ar, entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_miot import DOMAIN, MiotEntity
from custom_components.xiaomi_miot.alarm_control_panel import MiotAlarmEntity
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.switch import SwitchSubEntity
from custom_components.xiaomi_miot.vacuum import MiotVacuumEntity


PLATFORMS = [
    ('alarm_control_panel', 'MiotAlarmEntity'),
    ('remote', 'MiotRemoteEntity'),
    ('vacuum', 'MiotVacuumEntity'),
    ('water_heater', 'MiotWaterHeaterEntity'),
]


@pytest.fixture
def legacy_spec(hass):
    """Only the service identity is needed by the legacy constructors."""
    return MiotSpec(hass, {
        'type': 'urn:miot-spec-v2:device:vacuum:0000A006:test-model:1',
        'description': 'Test Device',
        'services': [
            {'iid': 2, 'type': 'urn:miot-spec-v2:service:vacuum:00007810:test-model:1',
             'description': 'Robot Cleaner', 'properties': []},
            {'iid': 3, 'type': 'urn:miot-spec-v2:service:arming:00007820:test-model:1',
             'description': 'Arming', 'properties': []},
        ],
    })


@pytest.mark.parametrize(('domain', 'class_name'), PLATFORMS)
def test_legacy_platform_declares_its_domain(domain, class_name):
    module = import_module(f'custom_components.xiaomi_miot.{domain}')
    assert getattr(module, class_name)._entity_domain == domain


@pytest.mark.parametrize(('entity_cls', 'domain', 'service'), [
    (MiotVacuumEntity, 'vacuum', 'vacuum'),
    (MiotAlarmEntity, 'alarm_control_panel', 'arming'),
])
@pytest.mark.parametrize('existing', [False, True], ids=['new', 'existing-renamed'])
async def test_platform_registration_and_reload_preserve_identity(
    hass, make_device, legacy_spec, entity_cls, domain, service, existing, caplog,
):
    device = make_device(legacy_spec)
    unique_id = f'{device.unique_id}-{legacy_spec.get_service(service).iid}'
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    seeded = None
    if existing:
        seeded = registry.async_get_or_create(
            domain, DOMAIN, unique_id, config_entry=entry,
            suggested_object_id='original_device',
        )
        area = ar.async_get(hass).async_create('Test Room')
        seeded = registry.async_update_entity(
            seeded.entity_id, new_entity_id=f'{domain}.custom_device',
            name='Custom Device', icon='mdi:star', area_id=area.id,
        )

    first = None
    for _ in range(2):
        entity = entity_cls({CONF_DEVICE: device}, legacy_spec.get_service(service))
        assert entity.entity_id.startswith(f'{domain}.')
        assert entity.unique_id == unique_id
        # Avoid subscriptions/device I/O, not HA's entity registration machinery.
        entity._attr_device_info = None
        platform = EntityPlatform(
            hass=hass, logger=device.log, domain=domain, platform_name=DOMAIN,
            platform=None, scan_interval=timedelta(hours=1), entity_namespace=None,
        )
        platform.config_entry = entry
        with patch.object(entity, 'async_added_to_hass', AsyncMock()):
            await platform.async_add_entities([entity])
        current = registry.async_get(entity.entity_id)
        assert current.platform == DOMAIN
        assert current.unique_id == unique_id
        assert current.config_entry_id == entry.entry_id
        if first is None:
            first = current
        assert (current.id, current.entity_id) == (first.id, first.entity_id)
        if seeded:
            assert (current.id, current.entity_id) == (seeded.id, seeded.entity_id)
            assert (current.name, current.icon, current.area_id) == (
                seeded.name, seeded.icon, seeded.area_id,
            )
        assert len([r for r in registry.entities.values()
                    if r.platform == DOMAIN and r.unique_id == unique_id]) == 1
        await platform.async_reset()
        await hass.async_block_till_done()
        assert not platform.entities
        # HA may retain a restored/unavailable placeholder for a registered ID.
        assert registry.async_get(current.entity_id).id == first.id

    assert 'sets an entity ID with wrong domain' not in caplog.text


def test_no_service_fallback_uses_platform_without_changing_unique_id(make_device, legacy_spec):
    class LegacyVacuum(MiotEntity):
        _entity_domain = 'vacuum'

    device = make_device(legacy_spec)
    entity = LegacyVacuum(config={CONF_DEVICE: device})
    assert entity.entity_id.startswith('vacuum.')
    assert entity.unique_id == device.unique_id


def test_subentity_keeps_its_own_platform_and_identity(make_device, legacy_spec):
    device = make_device(legacy_spec)
    parent = MiotVacuumEntity({CONF_DEVICE: device}, legacy_spec.get_service('vacuum'))
    child = SwitchSubEntity(parent, 'power')
    assert child.entity_id.startswith('switch.')
    assert child.unique_id == f'{parent.unique_id}-power'
    explicit = SwitchSubEntity(parent, 'power', {'entity_id': 'switch.custom_control'})
    assert explicit.entity_id == 'switch.custom_control'
    assert explicit.unique_id == child.unique_id
