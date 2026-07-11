# Multi-Entity Converter Design for `cnhdm.airrtc.wkq01`

**Date:** 2026-07-11
**Status:** Approved for implementation planning

## Problem

The `cnhdm.airrtc.wkq01` exposes air conditioning, floor heating, and fresh-air functions through one MIoT `thermostat` service. Several properties have overlapping semantic roles, such as multiple power, target-temperature, and fan-level properties.

The current global climate converter groups properties by semantic name. PR #2878 ([fix(climate): Handle duplicate properties in on_init()](https://github.com/al-one/hass-xiaomi-miot/pull/2878)) proposed adding duplicate-property guards to `ClimateEntity.on_init()` so the first matching property wins for each role. Review concluded that the first-wins approach is unsafe: it depends on converter ordering, silently suppresses device functions, and still cannot expose the floor-heating and fresh-air features as independent entities. Model-level property exclusion was also considered and rejected for the same reason.

The integration must preserve every independently controllable function while preventing unrelated properties from being combined into one Home Assistant entity.

## Goals

- Represent the device as three independently controllable entities:
  - air-conditioner Climate
  - floor-heating Climate
  - fresh-air Fan
- Preserve the shared environment temperature as a Sensor and the physical-controls lock as a Switch.
- Select ambiguous properties declaratively by exact MIoT identifiers.
- Preserve the existing air-conditioner entity identity.
- Give each additional parent converter and entity a stable, distinct identity.
- Keep existing converter behavior unchanged for models without the new configuration.

## Non-Goals

- Changing global duplicate-property selection in Climate entities.
- Extracting reusable global converter constants for this one model.
- Splitting the MIoT service definition itself.
- Changing entity identity for existing models by default.

## Device Property Mapping

| Function | MIoT selector | Meaning |
| --- | --- | --- |
| Air conditioning | `prop.2.3` | power |
| Air conditioning | `prop.2.1` | mode |
| Air conditioning | `prop.2.5` | target temperature |
| Air conditioning | `prop.2.2` | fan level |
| Fresh air | `prop.2.9` | power |
| Fresh air | `prop.2.7` | fan level |
| Floor heating | `prop.2.10` | power |
| Floor heating | `prop.2.8` | target temperature |
| Shared environment | `prop.3.1` | current temperature (`temperature`) |
| Device controls | `prop.5.1` | physical-controls lock (`physical_controls_locked`) |

Exact selectors are used inside the three parent converter definitions because the properties belong to different logical functions despite sharing one service. The standalone Sensor and Switch use semantic property names because those names are unambiguous.

## Converter Selection Semantics

Add an optional model customization key named `converters` to `Device.init_converters()`.

```python
custom_converters = self.custom_config('converters')
base_converters = (
    GLOBAL_CONVERTERS
    if custom_converters is None
    else custom_converters
)
appends = self.custom_config_list('append_converters') or []

for cfg in [*base_converters, *appends]:
    ...
```

The behavior is:

| Model configuration | Converter definitions processed |
| --- | --- |
| `converters` absent | `GLOBAL_CONVERTERS`, then `append_converters` |
| `converters: []` | no base converters, then `append_converters` |
| non-empty `converters` | model `converters`, then `append_converters` |

This is an explicit replacement mechanism. It does not merge model entries with `GLOBAL_CONVERTERS`. Existing models remain unchanged because an absent key retains the current global behavior.

### Info Entity Diagnostics

`InfoConv.decode()` currently copies device customizations into the Info entity's `customizes` state attribute. The new model-level `converters` definitions contain Python converter classes and internal configuration structures that are not suitable for Home Assistant state serialization or recorder persistence. Remove the key from the copied diagnostics before constructing the payload:

```python
customizes = {**device.customizes}
customizes.pop('append_converters', None)
customizes.pop('converters', None)
customizes.pop('extend_miot_specs', None)
```

The Info entity continues to expose the effective converter full names through its existing top-level diagnostics field:

```python
'converters': [c.full_name for c in device.converters]
```

This preserves useful runtime diagnostics without exposing class objects or duplicating the declarative configuration.

## Entity Identity

Parent converter deduplication already uses `conv.full_name`. The air-conditioner keeps its property-derived attribute, while the floor-heating and fresh-air converters set explicit `kwargs.attr` values. Their parent converter full names are therefore stable and distinct:

```text
climate.floor_heating
fan.fresh_air
```

Entity creation has a separate collision point: `convert_unique_id()` currently returns the service IID for every `MiotServiceConv`, so both Climate converters from SIID 2 would otherwise receive the same entity key and Home Assistant unique ID.

Add two opt-in unique-ID options before the existing fallback:

```python
def convert_unique_id(conv):
    if uid := conv.option.get('unique_id'):
        return uid
    if conv.option.get('use_unique_attr'):
        return conv.attr

    # Existing fallback behavior remains unchanged.
    service = getattr(conv, 'service', None)
    if isinstance(conv, MiotServiceConv) and isinstance(service, MiotService):
        return service.iid
    ...
```

The precedence is:

```text
option.unique_id > option.use_unique_attr > existing fallback
```

- `kwargs.attr` controls the converter attribute and therefore its `full_name`; it does not change entity identity by itself.
- `option.unique_id` supplies an explicit stable entity identifier and has the highest priority.
- `option.use_unique_attr: true` uses `conv.attr` as the entity identifier and suggested entity ID suffix, avoiding repetition when an explicit stable attribute is already configured.
- Without either option, existing `MiotServiceConv` behavior continues to use the service IID.

The air-conditioner Climate intentionally uses the existing fallback so its identity remains unchanged. Floor heating and fresh air set stable logical attributes and opt into using those attributes as their entity IDs.

## Model Configuration

Add the following customization for `cnhdm.airrtc.wkq01`:

```python
'cnhdm.airrtc.wkq01': {
    'converters': [
        {
            'class': MiotClimateConv,
            'services': ['thermostat'],
            'kwargs': {
                'main_props': ['prop.2.1'],
                'option': {
                    'name': 'Air Conditioner',
                },
            },
            'converters': [
                {'props': ['prop.2.3']},
                {'props': ['prop.2.1'], 'desc': True},
                {'props': ['prop.2.5']},
                {'props': ['prop.2.2'], 'desc': True},
                {'props': ['prop.3.1']},
            ],
        },
        {
            'class': MiotClimateConv,
            'services': ['thermostat'],
            'kwargs': {
                'attr': 'floor_heating',
                'main_props': ['prop.2.8'],
                'option': {
                    'name': 'Floor Heating',
                    'use_unique_attr': True,
                    'hvac_mode': 'heat',
                },
            },
            'converters': [
                {'props': ['prop.2.10']},
                {'props': ['prop.2.8']},
                {'props': ['prop.3.1']},
            ],
        },
        {
            'class': MiotFanConv,
            'services': ['thermostat'],
            'kwargs': {
                'attr': 'fresh_air',
                'main_props': ['prop.2.9'],
                'option': {
                    'name': 'Fresh Air',
                    'use_unique_attr': True,
                },
            },
            'converters': [
                {'props': ['prop.2.9']},
                {'props': ['prop.2.7'], 'desc': True},
            ],
        },
    ],
    'sensor_properties': 'temperature',
    'switch_properties': 'physical_controls_locked',
}
```

`option.name` supplies a fixed English display name for the entity. When set:

- `_attr_name` is replaced with the supplied name.
- `_attr_translation_key` is cleared so Home Assistant does not translate `thermostat` over the configured name.
- The configured name is not localized; further languages must use translation keys in code if needed.

When `option.use_unique_attr: true` is also set, the suggested entity ID is generated from `conv.attr` rather than the underlying service or property identifier. The existing air-conditioner Climate uses the fixed `Air Conditioner` display name but does not enable `use_unique_attr`, so it keeps the entity ID derived from the `thermostat` service.

## Fixed HVAC Mode for Power-Only Climate Entities

`option.hvac_mode` defines the fixed running mode of a Climate entity that has a power converter but no real mode converter. The configured value is resolved through the existing `_hvac_modes` mapping so its corresponding `HVACAction` remains consistent.

For `option.hvac_mode: 'heat'`, the complete behavior is:

| Power state | HVAC mode | HVAC action |
| --- | --- | --- |
| off | `HVACMode.OFF` | `HVACAction.OFF` |
| on | `HVACMode.HEAT` | `HVACAction.HEATING` |

The supported HVAC modes are exactly `OFF` and `HEAT`. Selecting Heat or calling turn-on writes only the entity's assigned power property. Setting the target temperature writes only its assigned target-temperature property.

The option is conditional:

- It applies only when a power converter exists and no real mode converter is present.
- A real mode converter always takes precedence; when one exists, `option.hvac_mode` is ignored for supported modes, state, action, and writes.
- A power-only Climate entity without the option retains the existing `OFF/AUTO` behavior.

State updates follow a power-driven invariant:

- When a payload contains the assigned power property, its value deterministically sets `is_on`, HVAC mode, and HVAC action, regardless of their previous values.
- Repeated power values are idempotent and reassert the same complete state.
- When a payload does not contain the power property, it must not change `is_on`, HVAC mode, or HVAC action. Target- and current-temperature properties still update independently.
- A payload containing both power and temperature updates both state groups in the same call.

The design does not add `RestoreEntity` behavior to `ClimateEntity`; after setup or reload, the first device power update establishes the fixed HVAC state.

## Entity Behavior

### Air-Conditioner Climate

- Power: `prop.2.3`
- Mode: `prop.2.1`
- Target temperature: `prop.2.5`
- Fan level: `prop.2.2`
- Current temperature: `prop.3.1`
- Entity identity: existing service-IID fallback

Its supported HVAC modes continue to derive from the mode property's value list.

### Floor-Heating Climate

- Power: `prop.2.10`
- Target temperature: `prop.2.8`
- Current temperature: `prop.3.1`
- Converter attribute: `floor_heating`
- Entity identity: `floor_heating`, derived from the explicit converter attribute
- Suggested entity ID suffix: `floor_heating`
- Fixed display name: `Floor Heating`

This converter has no real mode property, so `option.hvac_mode: 'heat'` applies the fixed power-only Climate behavior defined above.

Turning the floor-heating Climate on or selecting Heat writes only `prop.2.10`. Setting its target temperature writes only `prop.2.8`.

### Fresh-Air Fan

- Power: `prop.2.9`
- Fan level: `prop.2.7`
- Converter attribute: `fresh_air`
- Entity identity: `fresh_air`, derived from the explicit converter attribute
- Suggested entity ID suffix: `fresh_air`
- Fixed display name: `Fresh Air`

The fan-level property is a three-value enumeration:

| Raw value | Description |
| --- | --- |
| `1` | Low |
| `2` | Medium |
| `3` | High |

The existing Fan ordered-list conversion maps these descriptions to Home Assistant percentages and converts percentages back to raw MIoT values. The entity reports three speeds and supports `FanEntityFeature.SET_SPEED`.

Write behavior depends on current power state:

- Adjusting percentage while on writes only `prop.2.7`.
- Setting a positive percentage while off writes `prop.2.9 = True` and the corresponding `prop.2.7` value together.
- Setting percentage to zero writes only `prop.2.9 = False`.
- Calling turn-on without a percentage writes only `prop.2.9 = True`.
- Calling turn-off writes only `prop.2.9 = False`.

No fresh-air operation may write the air-conditioner power or fan-level properties `prop.2.3` or `prop.2.2`.

### Standalone Entities

- `sensor_properties: 'temperature'` creates the shared current-temperature Sensor through the existing semantic lookup path.
- `switch_properties: 'physical_controls_locked'` creates the lock Switch through the existing semantic lookup path.

The shared temperature may also feed both Climate entities. This duplication is intentional: the Climate entities need current temperature, while the standalone Sensor preserves the original device feature.

## Compatibility

- Models without `converters` continue to process `GLOBAL_CONVERTERS` followed by `append_converters`.
- Existing `append_converters` customizations retain their current meaning.
- Existing converter and entity unique IDs remain unchanged unless a converter explicitly sets `unique_id` or enables `use_unique_attr`.
- The existing air-conditioner entity for this model retains the service-IID-based identity, including any user-customized Entity Registry entity ID across upgrade and reload.
- The change does not introduce global property-order precedence or suppress duplicate properties for other devices.
- Because this model opts out of global converters, future MIoT spec additions require an explicit review of the model customization and its checked-in fixture before new entities are exposed.

## Test Strategy

### Test Infrastructure

Add the repository's first focused pytest infrastructure as part of this change:

```text
requirements_test.txt
tests/
├── conftest.py
├── fixtures/
│   └── cnhdm.airrtc.wkq01.json
├── test_converter_options.py
└── test_cnhdm_airrtc_wkq01.py
```

- `requirements_test.txt` provides pytest and the Home Assistant custom-component test support needed by the fixtures.
- `tests/conftest.py` contains only shared Home Assistant and integration fixtures required by these tests.
- `tests/fixtures/cnhdm.airrtc.wkq01.json` is a fixed local MIoT spec fixture for deterministic model tests; tests do not fetch the live specification.
- `tests/test_converter_options.py` covers framework-level converter replacement, identity, naming, and Info diagnostics behavior.
- `tests/test_cnhdm_airrtc_wkq01.py` covers the model-specific entity grouping, runtime behavior, and entity-registry migration lifecycle.

Add a pytest job to `.github/workflows/validate.yml`. It runs against the current stable Home Assistant environment only. The existing stable, dev, and 2023.7 Home Assistant configuration-validation matrix remains unchanged; the new unit-test job does not expand that compatibility matrix.

Keep the infrastructure minimal and scoped to the approved converter design. It does not introduce coverage tooling, a multi-version pytest matrix, or tests for unrelated integration behavior.

### Converter Selection

- Verify a model without `converters` receives global and appended converters.
- Verify `converters: []` skips global definitions but still processes appended definitions.
- Verify non-empty `converters` replaces global definitions and still processes appended definitions.
- Verify the Info entity omits model-level `converters` from its `customizes` state attribute.
- Verify the Info entity's top-level `converters` field still lists the full names of the effective runtime converters.

### Unique IDs

- Verify `option.unique_id` overrides `option.use_unique_attr` and the service-IID fallback.
- Verify `option.use_unique_attr: true` returns `conv.attr` when no explicit unique ID exists and generates the suggested entity ID from the same attribute.
- Verify a `MiotServiceConv` without either option still uses the service IID.
- Verify explicit `kwargs.attr` values produce stable, distinct converter full names.
- Verify the two Climate entities and Fan entity for this model have distinct entity keys and Home Assistant unique IDs.

### Entity Registry Migration

Keep pure identity unit tests separate from one registry-backed lifecycle test. The lifecycle test must add entities through Home Assistant's Entity Platform so Entity Registry matching is exercised; mocking only `async_add_entities` is insufficient.

Seed the registry with the existing air-conditioner Climate identity:

```text
platform: xiaomi_miot
unique ID: <device unique ID>-2
entity ID: climate.living_room_ac
```

The custom entity ID represents a user-renamed existing entity. After loading the new model configuration, verify:

- The air-conditioner Climate reuses the existing registry entry and retains `climate.living_room_ac`.
- Its unique ID remains `<device unique ID>-2`.
- Floor heating is registered with unique ID `<device unique ID>-floor_heating` and suggested entity ID suffix `floor_heating`.
- Fresh air is registered with unique ID `<device unique ID>-fresh_air` and suggested entity ID suffix `fresh_air`.
- The registry contains exactly two Climate entities and one Fan entity for these controls.
- No duplicate thermostat or air-conditioner Climate is created.
- Updating the air-conditioner display name to `Air Conditioner` does not alter its registry entity ID.

Unload and reload the config entry, then verify:

- All three unique IDs and entity IDs remain unchanged.
- The entity counts do not increase.
- The new entities do not acquire collision suffixes such as `_2` or `_3`.
- The user-renamed `climate.living_room_ac` still refers to the original registry entry.

### Fixed HVAC Mode

- Verify the floor-heating Climate advertises exactly `OFF` and `HEAT`.
- Verify the transition sequence `HEAT → OFF → HEAT` maps power deterministically to `HEAT/HEATING`, `OFF/OFF`, and `HEAT/HEATING`.
- Verify repeated `True` and repeated `False` power updates are idempotent and reassert the complete matching mode/action state.
- Verify a target-temperature-only payload updates the target while preserving the current `is_on`, HVAC mode, and HVAC action in both powered and unpowered states.
- Verify a combined power and target-temperature payload updates both state groups in the same call.
- Verify selecting Heat and calling turn-on write only `prop.2.10`.
- Verify setting the floor-heating target temperature writes only `prop.2.8`.
- Verify `option.hvac_mode` is ignored when a real mode converter exists.
- Verify a power-only Climate entity without the option retains its existing `OFF/AUTO` behavior.
- Do not introduce or test new `RestoreEntity` behavior; after setup or reload, verify the first power update establishes the correct fixed mode and action.

### Fresh-Air Fan

- Verify raw values `1`, `2`, and `3` decode through Low, Medium, and High to their ordered-list percentages.
- Verify representative percentages encode back to raw values `1`, `2`, and `3`, preserving the ordered-list round trip without duplicating Home Assistant's percentage rounding algorithm in the assertions.
- Verify the entity reports `speed_count == 3` and supports `FanEntityFeature.SET_SPEED`.
- Verify changing percentage while on writes only `prop.2.7`.
- Verify setting a positive percentage while off writes `prop.2.9 = True` together with the corresponding `prop.2.7` value.
- Verify setting percentage to zero and calling turn-off write only `prop.2.9 = False`.
- Verify calling turn-on without a percentage writes only `prop.2.9 = True`.
- Verify no fresh-air operation writes `prop.2.2` or `prop.2.3`.

### Model Mapping

Use the fixed local MIoT spec fixture and verify that the complete approved entity set is exactly:

| Domain | Entity |
| --- | --- |
| `button` | Info |
| `climate` | Air Conditioner |
| `climate` | Floor Heating |
| `fan` | Fresh Air |
| `sensor` | Temperature |
| `switch` | Physical Controls Locked |

Also verify:

- Exactly two Climate parent converters and one Fan parent converter are created.
- Each parent's `attrs` contains only its declared properties.
- Child property converters retain `domain=None` and are not created as independent entities.
- The Info converter remains present even though model `converters` replaces `GLOBAL_CONVERTERS`.
- Semantic `temperature` creates exactly one Sensor and `physical_controls_locked` creates exactly one Switch.
- No residual global thermostat converter creates an extra Climate or Fan entity.
- Properties of the `function` service, including weekly-program data, are not exposed as an accidental side effect.
- The air-conditioner entity retains its previous unique ID and service-derived entity ID.
- `option.name` sets the fixed display name and clears the service translation key.
- Floor heating and fresh air use `floor_heating` and `fresh_air` as their suggested entity ID suffixes.
- Writes from each entity target only its assigned power, mode, temperature, and fan-level properties.

Do not compare the complete old and new converter lists: the old Climate grouping is the defect being replaced. The six-entity set above is the authoritative expected result for the checked-in fixture.

## Implementation Scope

Expected implementation files:

- `custom_components/xiaomi_miot/core/device.py`
  - select model `converters` or `GLOBAL_CONVERTERS`, then append `append_converters`
- `custom_components/xiaomi_miot/core/converters.py`
  - omit model-level `converters` definitions from the Info entity's `customizes` state attribute while preserving effective converter names
- `custom_components/xiaomi_miot/core/hass_entity.py`
  - apply unique-ID option precedence
  - use `conv.attr` as the suggested entity ID suffix when `use_unique_attr` is enabled
  - apply `option.name` as a fixed display name and clear the service translation key
- `custom_components/xiaomi_miot/climate.py`
  - apply `option.hvac_mode` only to power-only Climate entities
  - derive supported modes, powered state, and HVAC Action from the existing `_hvac_modes` mapping
  - deterministically update mode/action when power is present and preserve them for unrelated partial payloads
  - preserve real mode converter precedence and the default `OFF/AUTO` behavior
- `custom_components/xiaomi_miot/core/device_customizes.py`
  - add the model-specific converter definitions and semantic Sensor/Switch properties
- `.github/workflows/validate.yml`
  - add a pytest job using the current stable Home Assistant test environment
- `requirements_test.txt`
  - declare the minimal pytest and Home Assistant custom-component test dependencies
- `tests/conftest.py`
  - provide shared Home Assistant and integration fixtures
- `tests/fixtures/cnhdm.airrtc.wkq01.json`
  - provide a deterministic local MIoT specification for model tests
- `tests/test_converter_options.py`
  - test converter replacement, identity options, naming, and Info diagnostics
- `tests/test_cnhdm_airrtc_wkq01.py`
  - test model-specific converter grouping and entity behavior

No global converter extraction or unrelated Climate refactoring is part of this change.
