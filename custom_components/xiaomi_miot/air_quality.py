"""Support for Xiaomi air qualities."""
import logging

from homeassistant.const import *  # noqa: F401
from homeassistant.components.air_quality import (
    DOMAIN as ENTITY_DOMAIN,
    AirQualityEntity,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotToggleEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    model = str(config.get(CONF_MODEL) or '')
    entities = []
    miot = config.get('miot_type')
    if miot:
        spec = await MiotSpec.async_from_type(hass, miot)
        for srv in spec.get_services('air_monitor', 'environment'):
            if not srv.get_property('pm2_5_density', 'co2_density'):
                continue
            cfg = {
                **config,
                'name': f"{config.get('name')} {srv.description}"
            }
            entities.append(MiotAirQualityEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotAirQualityEntity(MiotToggleEntity, AirQualityEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(miot_service, config=config)
        self._environment = miot_service.spec.get_service('environment') or self._miot_service
        self._state_attrs.update({'entity_class': self.__class__.__name__})

    def get_property_value(self, *args):
        prop = self._environment.get_property(*args)
        if prop:
            return prop.from_dict(self._state_attrs)
        return None

    @property
    def particulate_matter_2_5(self):
        return self.get_property_value('pm2_5_density')

    @property
    def particulate_matter_10(self):
        return self.get_property_value('pm10_density')

    @property
    def particulate_matter_0_1(self):
        """Return the particulate matter 0.1 level."""
        return None

    @property
    def air_quality_index(self):
        return self.get_property_value('air_quality_index', 'aqi')

    @property
    def ozone(self):
        """Return the O3 (ozone) level."""
        return None

    @property
    def carbon_monoxide(self):
        """Return the CO (carbon monoxide) level."""
        return None

    @property
    def carbon_dioxide(self):
        return self.get_property_value('co2_density')

    @property
    def attribution(self):
        """Return the attribution."""
        return None

    @property
    def sulphur_dioxide(self):
        """Return the SO2 (sulphur dioxide) level."""
        return None

    @property
    def nitrogen_oxide(self):
        """Return the N2O (nitrogen oxide) level."""
        return None

    @property
    def nitrogen_monoxide(self):
        """Return the NO (nitrogen monoxide) level."""
        return None

    @property
    def nitrogen_dioxide(self):
        """Return the NO2 (nitrogen dioxide) level."""
        return None

    @property
    def state(self):
        """Return the current state."""
        return self.particulate_matter_2_5

    @property
    def unit_of_measurement(self):
        return CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
