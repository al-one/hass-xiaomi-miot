# Multi-Climate Converters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `cnhdm.airrtc.wkq01` as independent air-conditioner Climate, floor-heating Climate, and fresh-air Fan entities without losing its shared temperature Sensor, controls-lock Switch, or existing air-conditioner identity.

**Architecture:** Add an opt-in model-level `converters` replacement path while retaining the Info converter and appended converters. Add narrowly scoped parent-converter identity, naming, and fixed power-only HVAC options, then declare the model's three controls with exact MIoT property selectors. Exercise the design through a fixed local MIoT fixture, entity-level payload tests, and one Entity Registry lifecycle test.

**Tech Stack:** Python 3, Home Assistant custom integration APIs, pytest, `pytest-homeassistant-custom-component`, Xiaomi MIoT converter classes.

## Global Constraints

- Models without `converters` must continue to process `GLOBAL_CONVERTERS` followed by `append_converters`.
- `converters: []` must process no global converters and still process `append_converters`.
- A non-empty model `converters` list must completely replace `GLOBAL_CONVERTERS` and still process `append_converters`.
- The always-added Info converter must remain present under every converter-selection mode.
- Converter identity precedence must be `option.unique_id > option.use_unique_attr > existing fallback`.
- `option.name` is a fixed, non-localized display name and must clear `_attr_translation_key`.
- `option.hvac_mode` applies only to a Climate with power and without a real mode converter; a real mode converter always wins.
- A power-only Climate without `option.hvac_mode` must retain its current `OFF/AUTO` behavior.
- Fixed-mode Climate power-present payloads deterministically update `is_on`, HVAC mode, and HVAC action; power-absent payloads preserve all three.
- The authoritative checked-in entity set is exactly Info, Thermostat, Floor Heating, Fresh Air, Temperature, and Physical Controls Locked.
- Do not add global duplicate-property precedence, global converter extraction, `RestoreEntity` behavior, coverage tooling, or a multi-version pytest matrix.
- Preserve the existing stable/dev/2023.7 Home Assistant configuration-validation matrix unchanged.

## File and Interface Map

- Create `requirements_test.txt`: current stable Home Assistant custom-component pytest support.
- Create `tests/conftest.py`: initialize integration data and build deterministic `Device` instances from local MIoT specs.
- Create `tests/fixtures/cnhdm.airrtc.wkq01.json`: complete four-service, 24-property local MIoT specification, including all SIID 4 function properties.
- Create `tests/test_converter_options.py`: framework-level converter selection, diagnostics, identity, naming, and generic Climate option tests.
- Create `tests/test_cnhdm_airrtc_wkq01.py`: exact model grouping, entity behavior, MIoT writes, complete entity set, and registry lifecycle.
- Modify `custom_components/xiaomi_miot/core/device.py:399-444`: choose model or global base converter definitions before appending `append_converters`.
- Modify `custom_components/xiaomi_miot/core/converters.py:72-80`: filter declarative converter definitions from Info state diagnostics.
- Modify `custom_components/xiaomi_miot/core/hass_entity.py:112-159,275-288`: apply fixed names, attr-based suggested entity IDs, and unique-ID option precedence.
- Modify `custom_components/xiaomi_miot/climate.py:164-258`: implement fixed power-only HVAC mode without changing real-mode or default behavior.
- Modify `custom_components/xiaomi_miot/core/device_customizes.py`: add the exact three-parent model converter declaration plus semantic Sensor/Switch properties.
- Modify `.github/workflows/validate.yml`: add one current-stable pytest job.

### Shared test interfaces

`tests/conftest.py` produces two callable fixtures: `load_miot_spec(name: str) -> MiotSpec` and `make_device(spec: MiotSpec, *, model: str = "test.device.model", customizes: dict | None = None, unique_id: str = "aa:bb:cc:dd:ee:ff") -> Device`.

The helper installs temporary `DEVICE_CUSTOMIZES[model]`, initializes converters synchronously, and registers cleanup that restores the original customization. Tests that create entities install the required domain class in `XEntity.CLS` by importing its platform module, then instantiate from parent converters or call `Device.add_entities()` with collecting adders.

Runtime write tests patch `device.async_set_properties` and assert the final encoded list of MIoT dictionaries:

```python
{"did": device.did, "siid": 2, "piid": <property>, "value": <value>}
```

---

### Task 1: Establish deterministic pytest infrastructure

**Files:**
- Create: `requirements_test.txt`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/cnhdm.airrtc.wkq01.json`
- Create: `tests/test_converter_options.py`

**Interfaces:**
- Consumes: `init_integration_data()`, `DeviceInfo`, `Device`, `MiotSpec`, `HassEntry`.
- Produces: `load_miot_spec` and `make_device` fixtures used by all later tasks.

- [ ] **Step 1: Add the test dependencies**

Create `requirements_test.txt`:

```text
pytest-homeassistant-custom-component
construct>=2.10.68
python-miio>=0.5.12
micloud>=0.5
```

- [ ] **Step 2: Add a smoke test that requires the shared fixtures**

Create `tests/test_converter_options.py`:

```python
from custom_components.xiaomi_miot.core.device import InfoConverter


def test_make_device_adds_info_converter(make_device, load_miot_spec):
    device = make_device(load_miot_spec("cnhdm.airrtc.wkq01.json"))

    assert device.converters[0] is InfoConverter
    assert device.find_converter("button.info") is InfoConverter
```

- [ ] **Step 3: Run the smoke test and verify RED**

Run:

```bash
pytest -q tests/test_converter_options.py::test_make_device_adds_info_converter
```

Expected: pytest fails during fixture lookup because `load_miot_spec` and `make_device` do not exist.

- [ ] **Step 4: Add the shared fixtures**

Create `tests/conftest.py`:

```python
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.xiaomi_miot import DOMAIN, init_integration_data
from custom_components.xiaomi_miot.core.device import Device, DeviceInfo
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def setup_xiaomi_miot_data(hass):
    init_integration_data(hass)
    hass.data[DOMAIN]["config"] = {}
    hass.data.setdefault("customize", {})


@pytest.fixture
def load_miot_spec(hass):
    def _load(name: str) -> MiotSpec:
        with (FIXTURES / name).open(encoding="utf-8") as file:
            return MiotSpec(hass, json.load(file))

    return _load


@pytest.fixture
def make_device(hass, request):
    originals = {}

    def _make(
        spec: MiotSpec,
        *,
        model: str = "test.device.model",
        customizes: dict | None = None,
        unique_id: str = "aa:bb:cc:dd:ee:ff",
    ) -> Device:
        if model not in originals:
            originals[model] = DEVICE_CUSTOMIZES.get(model)
        DEVICE_CUSTOMIZES[model] = customizes or {}

        entry = SimpleNamespace(
            hass=hass,
            cloud=None,
            id="test-entry",
            adders={},
            get_config=lambda key=None, default=None: default,
        )
        info = DeviceInfo({
            "did": "test-device",
            "mac": unique_id,
            "name": "Test Device",
            "model": model,
            "urn": spec.type,
        })
        device = Device(info, entry)
        device.spec = spec
        device.init_converters()
        return device

    def restore_customizes():
        for model, original in originals.items():
            if original is None:
                DEVICE_CUSTOMIZES.pop(model, None)
            else:
                DEVICE_CUSTOMIZES[model] = original

    request.addfinalizer(restore_customizes)
    return _make
```

- [ ] **Step 5: Add the complete fixed MIoT fixture**

Create `tests/fixtures/cnhdm.airrtc.wkq01.json` with the released model URN and these exact service definitions. Keep every SIID 4 property so tests can prove function/weekly-program data is not accidentally exposed:

```json
{
  "type": "urn:miot-spec-v2:device:thermostat:0000A031:cnhdm-wkq01:1",
  "description": "Thermostat",
  "services": [
    {
      "iid": 2,
      "type": "urn:miot-spec-v2:service:thermostat:0000784A:cnhdm-wkq01:1",
      "description": "Thermostat",
      "properties": [
        {"iid": 3, "type": "urn:miot-spec-v2:property:on:00000006:cnhdm-wkq01:1", "description": "Switch Status", "format": "bool", "access": ["read", "write", "notify"]},
        {"iid": 1, "type": "urn:miot-spec-v2:property:mode:00000008:cnhdm-wkq01:1", "description": "Mode", "format": "uint8", "access": ["read", "write", "notify"], "value-list": [{"value": 0, "description": "Cool"}, {"value": 1, "description": "Heat"}, {"value": 2, "description": "Ventilation"}]},
        {"iid": 5, "type": "urn:miot-spec-v2:property:target-temperature:00000021:cnhdm-wkq01:1", "description": "Target Temperature", "format": "uint32", "access": ["read", "write", "notify"], "unit": "celsius", "value-range": [16, 32, 1]},
        {"iid": 2, "type": "urn:miot-spec-v2:property:fan-level:00000016:cnhdm-wkq01:1", "description": "Fan Level", "format": "uint8", "access": ["read", "write", "notify"], "value-list": [{"value": 0, "description": "Auto"}, {"value": 1, "description": "Low"}, {"value": 2, "description": "Medium"}, {"value": 3, "description": "High"}]},
        {"iid": 7, "type": "urn:miot-spec-v2:property:fan-level:00000016:cnhdm-wkq01:1", "description": "Fan Level", "format": "uint8", "access": ["read", "write", "notify"], "value-list": [{"value": 1, "description": "Low"}, {"value": 2, "description": "Medium"}, {"value": 3, "description": "High"}]},
        {"iid": 8, "type": "urn:miot-spec-v2:property:target-temperature:00000021:cnhdm-wkq01:1", "description": "Target Temperature", "format": "int32", "access": ["read", "write", "notify"], "unit": "celsius", "value-range": [5, 50, 1]},
        {"iid": 9, "type": "urn:miot-spec-v2:property:on:00000006:cnhdm-wkq01:1", "description": "Switch Status", "format": "bool", "access": ["read", "write", "notify"]},
        {"iid": 10, "type": "urn:miot-spec-v2:property:on:00000006:cnhdm-wkq01:1", "description": "Switch Status", "format": "bool", "access": ["read", "write", "notify"]}
      ],
      "actions": [],
      "events": []
    },
    {
      "iid": 3,
      "type": "urn:miot-spec-v2:service:environment:0000780A:cnhdm-wkq01:1",
      "description": "Environment",
      "properties": [
        {"iid": 1, "type": "urn:miot-spec-v2:property:temperature:00000020:cnhdm-wkq01:1", "description": "Temperature", "format": "float", "access": ["read", "notify"], "unit": "celsius", "value-range": [-50, 50, 0.1]}
      ],
      "actions": [],
      "events": []
    },
    {
      "iid": 5,
      "type": "urn:miot-spec-v2:service:physical-controls-locked:00007807:cnhdm-wkq01:1",
      "description": "Physical Control Locked",
      "properties": [
        {"iid": 1, "type": "urn:miot-spec-v2:property:physical-controls-locked:0000001D:cnhdm-wkq01:1", "description": "Physical Control Locked", "format": "bool", "access": ["read", "write", "notify"]}
      ],
      "actions": [],
      "events": []
    },
    {
      "iid": 4,
      "type": "urn:cnhdm-spec:service:function:00007801:cnhdm-wkq01:1",
      "description": "function",
      "properties": [
        {"iid": 2, "type": "urn:cnhdm-spec:property:parameter:00000001:cnhdm-wkq01:1", "description": "", "format": "uint32", "access": ["read", "write", "notify"], "value-range": [0, 4294967295, 1]},
        {"iid": 3, "type": "urn:cnhdm-spec:property:parameter:00000002:cnhdm-wkq01:1", "description": "", "format": "uint32", "access": ["read", "write", "notify"], "value-range": [0, 4294967295, 1]},
        {"iid": 4, "type": "urn:cnhdm-spec:property:time:00000003:cnhdm-wkq01:1", "description": "time", "format": "uint32", "access": ["write"], "value-range": [0, 4294967295, 1]},
        {"iid": 5, "type": "urn:cnhdm-spec:property:time:00000004:cnhdm-wkq01:1", "description": "", "format": "uint32", "access": ["write"], "value-range": [0, 4294967295, 1]},
        {"iid": 6, "type": "urn:cnhdm-spec:property:weekly-program:00000005:cnhdm-wkq01:1", "description": "", "format": "uint32", "access": ["read", "write", "notify"], "value-range": [0, 4294967295, 1]},
        {"iid": 7, "type": "urn:cnhdm-spec:property:weekly-program:00000006:cnhdm-wkq01:1", "description": "", "format": "uint32", "access": ["read", "write", "notify"], "value-range": [0, 4294967295, 1]},
        {"iid": 8, "type": "urn:cnhdm-spec:property:weekly-program:00000007:cnhdm-wkq01:1", "description": "weekly-program", "format": "uint32", "access": ["read", "write", "notify"], "value-range": [0, 4294967295, 1]},
        {"iid": 9, "type": "urn:cnhdm-spec:property:weekly-program:00000008:cnhdm-wkq01:1", "description": "", "format": "uint32", "access": ["read", "write", "notify"], "value-range": [0, 4294967295, 1]},
        {"iid": 10, "type": "urn:cnhdm-spec:property:weekly-program:00000009:cnhdm-wkq01:1", "description": "", "format": "uint32", "access": ["read", "write", "notify"], "value-range": [0, 4294967295, 1]},
        {"iid": 11, "type": "urn:cnhdm-spec:property:weekly-program:0000000A:cnhdm-wkq01:1", "description": "", "format": "uint32", "access": ["read", "write", "notify"], "value-range": [0, 4294967295, 1]},
        {"iid": 12, "type": "urn:cnhdm-spec:property:weekly-program:0000000B:cnhdm-wkq01:1", "description": "", "format": "uint32", "access": ["read", "write", "notify"], "value-range": [0, 4294967295, 1]},
        {"iid": 13, "type": "urn:cnhdm-spec:property:weekly-program:0000000C:cnhdm-wkq01:1", "description": "", "format": "uint32", "access": ["read", "notify", "write"], "value-range": [0, 4294967295, 1]},
        {"iid": 14, "type": "urn:cnhdm-spec:property:weekly-program:0000000D:cnhdm-wkq01:1", "description": "", "format": "uint32", "access": ["notify", "read", "write"], "value-range": [0, 4294967295, 1]},
        {"iid": 15, "type": "urn:cnhdm-spec:property:exchange-mode:0000000E:cnhdm-wkq01:1", "description": "", "format": "bool", "access": ["read", "notify", "write"]}
      ],
      "actions": [],
      "events": [{"iid": 1, "type": "urn:cnhdm-spec:event:time:00005001:cnhdm-wkq01:1", "description": "time", "arguments": []}]
    }
  ]
}
```

- [ ] **Step 6: Run the smoke test and verify GREEN**

Run:

```bash
pytest -q tests/test_converter_options.py::test_make_device_adds_info_converter
```

Expected: `1 passed`.

- [ ] **Step 7: Commit the test foundation**

```bash
git add requirements_test.txt tests/conftest.py tests/fixtures/cnhdm.airrtc.wkq01.json tests/test_converter_options.py
git commit -m "🧪 add focused MIoT converter test foundation"
```

---

### Task 2: Replace global converters per model and protect Info diagnostics

**Files:**
- Modify: `tests/test_converter_options.py`
- Modify: `custom_components/xiaomi_miot/core/device.py:399-444`
- Modify: `custom_components/xiaomi_miot/core/converters.py:72-80`

**Interfaces:**
- Consumes: `Device.custom_config()`, `append_converters`, `GLOBAL_CONVERTERS`, `InfoConv.decode()`.
- Produces: absent/empty/non-empty `converters` selection semantics and recorder-safe Info diagnostics.

- [ ] **Step 1: Add failing converter-selection tests**

Append to `tests/test_converter_options.py`:

```python
from custom_components.xiaomi_miot.core.converters import MiotClimateConv, MiotFanConv


def parent_domains(device):
    return [
        converter.domain
        for converter in device.converters
        if isinstance(converter, (MiotClimateConv, MiotFanConv))
    ]


def test_absent_model_converters_keeps_globals_and_appends(make_device, load_miot_spec):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        customizes={
            "append_converters": [{
                "class": MiotFanConv,
                "services": ["thermostat"],
                "kwargs": {"attr": "appended_fan", "main_props": ["prop.2.9"]},
            }],
        },
    )

    parent_names = [converter.full_name for converter in device.converters]
    appended_index = parent_names.index("fan.appended_fan")
    global_indices = [
        index
        for index, converter in enumerate(device.converters)
        if isinstance(converter, (MiotClimateConv, MiotFanConv))
        and converter.full_name != "fan.appended_fan"
    ]
    assert global_indices
    assert max(global_indices) < appended_index
    assert "climate" in parent_domains(device)
    assert device.find_converter("fan.appended_fan") is not None


def test_empty_model_converters_skips_globals_but_keeps_appends(make_device, load_miot_spec):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        customizes={
            "converters": [],
            "append_converters": [{
                "class": MiotFanConv,
                "services": ["thermostat"],
                "kwargs": {"attr": "appended_fan", "main_props": ["prop.2.9"]},
            }],
        },
    )

    assert parent_domains(device) == ["fan"]
    assert device.find_converter("fan.appended_fan") is not None
    assert device.find_converter("button.info") is InfoConverter


def test_model_converters_replace_globals_and_keep_appends(make_device, load_miot_spec):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        customizes={
            "converters": [{
                "class": MiotClimateConv,
                "services": ["thermostat"],
                "kwargs": {"attr": "replacement", "main_props": ["prop.2.8"]},
            }],
            "append_converters": [{
                "class": MiotFanConv,
                "services": ["thermostat"],
                "kwargs": {"attr": "appended_fan", "main_props": ["prop.2.9"]},
            }],
        },
    )

    assert parent_domains(device) == ["climate", "fan"]
    assert device.find_converter("climate.replacement") is not None
    assert device.find_converter("fan.appended_fan") is not None


def test_info_omits_converter_config_but_lists_effective_names(make_device, load_miot_spec):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        customizes={
            "converters": [],
            "append_converters": [{
                "class": MiotFanConv,
                "services": ["thermostat"],
                "kwargs": {"attr": "appended_fan", "main_props": ["prop.2.9"]},
            }],
        },
    )
    payload = {}

    InfoConverter.decode(device, payload, None)

    assert "converters" not in payload["customizes"]
    assert "append_converters" not in payload["customizes"]
    assert payload["converters"] == [converter.full_name for converter in device.converters]
    assert "fan.appended_fan" in payload["converters"]
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
pytest -q tests/test_converter_options.py -k "model_converters or info_omits"
```

Expected: empty and replacement cases still contain global parent converters; Info diagnostics still contain the `converters` configuration.

- [ ] **Step 3: Implement explicit base-converter selection**

In `Device.init_converters()`, replace the current `appends`/loop preamble with:

```python
        custom_converters = self.custom_config('converters')
        base_converters = (
            GLOBAL_CONVERTERS
            if custom_converters is None
            else custom_converters
        )
        appends = self.custom_config_list('append_converters') or []
        for cfg in [*base_converters, *appends]:
```

Do not move `self.add_converter(InfoConverter)` or `self.dispatch_info()`; they must remain before the model/global selection.

- [ ] **Step 4: Filter model converter definitions from Info state**

In `InfoConv.decode()`, keep the copied dictionary and add the middle removal:

```python
        customizes = {**device.customizes}
        customizes.pop('append_converters', None)
        customizes.pop('converters', None)
        customizes.pop('extend_miot_specs', None)
```

- [ ] **Step 5: Run the converter-selection tests and verify GREEN**

Run:

```bash
pytest -q tests/test_converter_options.py -k "model_converters or info_omits"
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit converter selection**

```bash
git add custom_components/xiaomi_miot/core/device.py custom_components/xiaomi_miot/core/converters.py tests/test_converter_options.py
git commit -m "🧩 support model-level converter replacement"
```

---

### Task 3: Add stable parent identity, fixed names, and attr-based suggested IDs

**Files:**
- Modify: `tests/test_converter_options.py`
- Modify: `custom_components/xiaomi_miot/core/hass_entity.py:112-159,275-288`

**Interfaces:**
- Consumes: `BaseConv.option`, `MiotServiceConv.service`, `MiotServiceConv.attr`.
- Produces: `convert_unique_id(conv)` precedence and opt-in `XEntity` name/entity-ID behavior.

- [ ] **Step 1: Add failing option and entity metadata tests**

Append to `tests/test_converter_options.py`:

```python
from custom_components.xiaomi_miot.climate import ClimateEntity
from custom_components.xiaomi_miot.core.hass_entity import convert_unique_id


def service_converter(spec, **option):
    service = spec.get_service("thermostat")
    return MiotClimateConv(
        service=service,
        attr="floor_heating",
        main_props=["prop.2.8"],
        option=option,
    )


def test_unique_id_option_priority(load_miot_spec):
    spec = load_miot_spec("cnhdm.airrtc.wkq01.json")

    assert convert_unique_id(service_converter(spec)) == 2
    assert convert_unique_id(service_converter(spec, use_unique_attr=True)) == "floor_heating"
    assert convert_unique_id(service_converter(spec, unique_id="explicit-id")) == "explicit-id"
    assert convert_unique_id(service_converter(
        spec,
        unique_id="explicit-id",
        use_unique_attr=True,
    )) == "explicit-id"


def test_explicit_attrs_make_distinct_converter_full_names(load_miot_spec):
    spec = load_miot_spec("cnhdm.airrtc.wkq01.json")

    floor = service_converter(spec, use_unique_attr=True)
    fresh = MiotFanConv(
        service=spec.get_service("thermostat"),
        attr="fresh_air",
        main_props=["prop.2.9"],
        option={"use_unique_attr": True},
    )

    assert floor.full_name == "climate.floor_heating"
    assert fresh.full_name == "fan.fresh_air"


def test_fixed_name_and_attr_based_entity_id(make_device, load_miot_spec):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        customizes={"converters": [{
            "class": MiotClimateConv,
            "services": ["thermostat"],
            "kwargs": {
                "attr": "floor_heating",
                "main_props": ["prop.2.8"],
                "option": {
                    "name": "Floor Heating",
                    "use_unique_attr": True,
                },
            },
        }]},
    )
    entity = ClimateEntity(device, device.find_converter("climate.floor_heating"))

    assert entity.unique_id == f"{device.unique_id}-floor_heating"
    assert entity.entity_id.endswith("_floor_heating")
    assert entity._attr_name == "Floor Heating"
    assert entity._attr_translation_key is None


def test_service_entity_defaults_remain_unchanged(make_device, load_miot_spec):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        customizes={"converters": [{
            "class": MiotClimateConv,
            "services": ["thermostat"],
            "kwargs": {"main_props": ["prop.2.1"]},
        }]},
    )
    converter = next(c for c in device.converters if isinstance(c, MiotClimateConv))
    entity = ClimateEntity(device, converter)

    assert entity.unique_id == f"{device.unique_id}-2"
    assert "thermostat" in entity.entity_id
    assert entity._attr_translation_key == "thermostat"
```

- [ ] **Step 2: Run the option tests and verify RED**

Run:

```bash
pytest -q tests/test_converter_options.py -k "unique_id_option or explicit_attrs or fixed_name or defaults_remain"
```

Expected: `use_unique_attr` still resolves to service IID; the floor entity ID remains service-derived; fixed name and cleared translation key assertions fail.

- [ ] **Step 3: Implement unique-ID option precedence**

At the start of `convert_unique_id()` add:

```python
def convert_unique_id(conv: 'BaseConv'):
    if uid := conv.option.get('unique_id'):
        return uid
    if conv.option.get('use_unique_attr'):
        return conv.attr

    service = getattr(conv, 'service', None)
```

Keep every existing action/property/attr fallback after this addition unchanged.

- [ ] **Step 4: Implement opt-in suggested entity ID and fixed naming**

Change only the `MiotServiceConv` branch of `XEntity.__init__()`:

```python
        if isinstance(conv, MiotServiceConv):
            if conv.option.get('use_unique_attr'):
                self.entity_id = device.spec.generate_entity_id(self, conv.attr, conv.domain)
            else:
                self.entity_id = conv.service.generate_entity_id(self, conv.domain)
            self._attr_name = str(conv.service.friendly_desc)
            self._attr_translation_key = conv.service.name
            self._miot_service = conv.service
            self._miot_property = conv.prop
```

After the converter-type branch and before `self.listen_attrs`, apply the name override:

```python
        if name := conv.option.get('name'):
            self._attr_name = name
            self._attr_translation_key = None
```

- [ ] **Step 5: Run option tests and verify GREEN**

Run:

```bash
pytest -q tests/test_converter_options.py -k "unique_id_option or explicit_attrs or fixed_name or defaults_remain"
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit identity and naming options**

```bash
git add custom_components/xiaomi_miot/core/hass_entity.py tests/test_converter_options.py
git commit -m "🆔 add opt-in converter entity identity options"
```

---

### Task 4: Implement fixed HVAC mode for power-only Climate entities

**Files:**
- Modify: `tests/test_converter_options.py`
- Modify: `custom_components/xiaomi_miot/climate.py:164-258`

**Interfaces:**
- Consumes: `conv.option['hvac_mode']`, `_hvac_modes`, `_conv_power`, `_conv_mode`.
- Produces: `_power_hvac_mode: HVACMode | None`, deterministic fixed-mode state, and unchanged real-mode/default behavior.

- [ ] **Step 1: Add a focused Climate builder and failing fixed-mode tests**

Append to `tests/test_converter_options.py`:

```python
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.climate.const import HVACAction, HVACMode


def make_climate(make_device, spec, converters, option=None):
    device = make_device(
        spec,
        customizes={"converters": [{
            "class": MiotClimateConv,
            "services": ["thermostat"],
            "kwargs": {
                "attr": "test_climate",
                "main_props": ["prop.2.8"],
                "option": option or {},
            },
            "converters": converters,
        }]},
    )
    entity = ClimateEntity(device, device.find_converter("climate.test_climate"))
    device.async_write = AsyncMock()
    return entity


def assert_fixed_heat(entity, is_on):
    assert entity.is_on is is_on
    assert entity.hvac_mode == (HVACMode.HEAT if is_on else HVACMode.OFF)
    assert entity.hvac_action == (HVACAction.HEATING if is_on else HVACAction.OFF)


def test_fixed_power_hvac_mode_is_deterministic(make_device, load_miot_spec):
    entity = make_climate(
        make_device,
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        [{"props": ["prop.2.10"]}, {"props": ["prop.2.8"]}],
        {"hvac_mode": "heat"},
    )

    assert set(entity.hvac_modes) == {HVACMode.OFF, HVACMode.HEAT}
    for value in [True, True, False, False, True]:
        entity.set_state({entity._conv_power.full_name: value})
        assert_fixed_heat(entity, value)
        assert entity._attr_preset_mode is None


def test_fixed_mode_preserves_power_state_on_partial_payload(make_device, load_miot_spec):
    entity = make_climate(
        make_device,
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        [{"props": ["prop.2.10"]}, {"props": ["prop.2.8"]}],
        {"hvac_mode": "heat"},
    )

    entity.set_state({entity._conv_power.full_name: True})
    entity.set_state({entity._conv_target_temp.full_name: 31})
    assert_fixed_heat(entity, True)
    assert entity.target_temperature == 31

    entity.set_state({entity._conv_power.full_name: False})
    entity.set_state({entity._conv_target_temp.full_name: 18})
    assert_fixed_heat(entity, False)
    assert entity.target_temperature == 18

    entity.set_state({
        entity._conv_power.full_name: True,
        entity._conv_target_temp.full_name: 26,
    })
    assert_fixed_heat(entity, True)
    assert entity.target_temperature == 26


def test_real_mode_converter_ignores_fixed_hvac_option(make_device, load_miot_spec):
    entity = make_climate(
        make_device,
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        [{"props": ["prop.2.3"]}, {"props": ["prop.2.1"], "desc": True}],
        {"hvac_mode": "heat"},
    )

    assert set(entity.hvac_modes) == {HVACMode.OFF, HVACMode.AUTO, HVACMode.COOL, HVACMode.HEAT}
    entity.set_state({entity._conv_mode.full_name: "Cool", entity._conv_power.full_name: True})
    assert entity.hvac_mode == HVACMode.COOL
    assert entity.hvac_action == HVACAction.COOLING


@pytest.mark.asyncio
async def test_real_mode_converter_writes_real_mode_property(make_device, load_miot_spec):
    entity = make_climate(
        make_device,
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        [{"props": ["prop.2.3"]}, {"props": ["prop.2.1"], "desc": True}],
        {"hvac_mode": "heat"},
    )
    entity._attr_is_on = True

    await entity.async_set_hvac_mode(HVACMode.COOL)

    entity.device.async_write.assert_awaited_once_with({entity._conv_mode.full_name: "Cool"})


def test_power_only_climate_without_option_keeps_auto(make_device, load_miot_spec):
    entity = make_climate(
        make_device,
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        [{"props": ["prop.2.10"]}],
    )

    assert set(entity.hvac_modes) == {HVACMode.OFF, HVACMode.AUTO}
    entity.set_state({entity._conv_power.full_name: True})
    assert entity.hvac_mode == HVACMode.AUTO
```

- [ ] **Step 2: Run fixed-mode tests and verify RED**

Run:

```bash
pytest -q tests/test_converter_options.py -k "fixed_power or fixed_mode or real_mode or power_only"
```

Expected: the fixed Climate advertises `AUTO` instead of `HEAT` and powers on as `AUTO`; real-mode/default regression tests pass or expose only test-helper corrections.

- [ ] **Step 3: Resolve the fixed mode after converter discovery**

In `ClimateEntity.on_init()`, initialize an instance field immediately after `BaseClimateEntity.on_init(self)`:

```python
        self._power_hvac_mode = None
```

After the converter loop and before assigning `_attr_hvac_modes`, add:

```python
        fixed_mode = self.conv.option.get('hvac_mode')
        if self._conv_power and not self._conv_mode and fixed_mode:
            try:
                self._power_hvac_mode = HVACMode(fixed_mode)
            except ValueError:
                self.log.warning('Unsupported fixed hvac mode: %s', fixed_mode)
            else:
                if self._power_hvac_mode in self._hvac_modes:
                    hvac_modes.discard(HVACMode.AUTO)
                    hvac_modes.add(self._power_hvac_mode)
                else:
                    self._power_hvac_mode = None
```

This validates only the external customization boundary. Do not introduce aliases or fallback modes.

- [ ] **Step 4: Make power-present state deterministic**

Replace the powered-on branch in `ClimateEntity.set_state()` with:

```python
            elif val and self._power_hvac_mode:
                self._attr_hvac_mode = self._power_hvac_mode
                self._attr_hvac_action = self._hvac_modes[self._power_hvac_mode].get('action')
                self._attr_preset_mode = None
            elif val and self._attr_hvac_mode in [None, HVACMode.OFF]:
                self._attr_hvac_mode = HVACMode.AUTO
```

Keep the `val is not None`, powered-off, heater fallback, and temperature handling around this branch unchanged. Because the fixed branch executes only when `val` is truthy, payloads without power still preserve mode/action.

- [ ] **Step 5: Write the fixed mode through its power converter**

In `ClimateEntity.async_set_temperature()`, add this branch immediately after the `OFF` branch and before the existing conditional power-on block:

```python
        if hvac and hvac == self._power_hvac_mode and self._conv_power:
            dat[self._conv_power.full_name] = True
```

This makes selecting the fixed Heat mode reassert power deterministically while still writing no mode property. Calling `async_turn_on()` continues to write the same power converter directly.

- [ ] **Step 6: Run fixed-mode tests and verify GREEN**

Run:

```bash
pytest -q tests/test_converter_options.py -k "fixed_power or fixed_mode or real_mode or power_only"
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit fixed HVAC behavior**

```bash
git add custom_components/xiaomi_miot/climate.py tests/test_converter_options.py
git commit -m "🌡️ support fixed mode power-only climates"
```

---

### Task 5: Declare and verify the complete model converter mapping

**Files:**
- Modify: `custom_components/xiaomi_miot/core/device_customizes.py`
- Create: `tests/test_cnhdm_airrtc_wkq01.py`

**Interfaces:**
- Consumes: exact-property converter resolution in `Device.init_converters()`, identity/naming/HVAC options from Tasks 2-4.
- Produces: the three parent controls plus semantic Sensor/Switch converters for `cnhdm.airrtc.wkq01`.

- [ ] **Step 1: Add the failing model mapping test**

Create `tests/test_cnhdm_airrtc_wkq01.py`:

```python
from custom_components.xiaomi_miot.climate import ClimateEntity
from custom_components.xiaomi_miot.fan import FanEntity
from custom_components.xiaomi_miot.core.converters import MiotClimateConv, MiotFanConv

MODEL = "cnhdm.airrtc.wkq01"


def model_device(make_device, load_miot_spec):
    return make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        model=MODEL,
        customizes=None,
    )


def test_exact_model_converter_mapping(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    climates = [c for c in device.converters if isinstance(c, MiotClimateConv)]
    fans = [c for c in device.converters if isinstance(c, MiotFanConv)]

    assert len(climates) == 2
    assert len(fans) == 1

    air_conditioner = climates[0]
    floor_heating = climates[1]
    fresh_air = fans[0]

    assert floor_heating.full_name == "climate.floor_heating"
    assert fresh_air.full_name == "fan.fresh_air"

    def unique_props(parent):
        return {
            device.find_converter(attr).prop.unique_prop
            for attr in parent.attrs
        }

    assert unique_props(air_conditioner) == {
        "prop.2.1", "prop.2.2", "prop.2.3", "prop.2.5", "prop.3.1",
    }
    assert unique_props(floor_heating) == {"prop.2.8", "prop.2.10", "prop.3.1"}
    assert unique_props(fresh_air) == {"prop.2.7", "prop.2.9"}

    assert all(device.find_converter(attr).domain is None for parent in [*climates, *fans] for attr in parent.attrs)
    assert device.find_converter("button.info") is not None
    assert len([c for c in device.converters if c.domain == "sensor" and c.prop.unique_prop == "prop.3.1"]) == 1
    assert len([c for c in device.converters if c.domain == "switch" and c.prop.unique_prop == "prop.5.1"]) == 1
    assert not any(getattr(c, "prop", None) and c.prop.service.iid == 4 for c in device.converters)


def test_parent_entity_metadata_and_identity(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    climates = [c for c in device.converters if isinstance(c, MiotClimateConv)]
    fans = [c for c in device.converters if isinstance(c, MiotFanConv)]
    air_converter = climates[0]
    floor_converter = climates[1]
    fan_converter = fans[0]

    air = ClimateEntity(device, air_converter)
    floor = ClimateEntity(device, floor_converter)
    fresh = FanEntity(device, fan_converter)

    assert [air.unique_id, floor.unique_id, fresh.unique_id] == [
        f"{device.unique_id}-2",
        f"{device.unique_id}-floor_heating",
        f"{device.unique_id}-fresh_air",
    ]
    assert len({air.unique_id, floor.unique_id, fresh.unique_id}) == 3
    assert air._attr_name == "Thermostat"
    assert floor._attr_name == "Floor Heating"
    assert fresh._attr_name == "Fresh Air"
    assert air._attr_translation_key == "thermostat"
    assert floor._attr_translation_key is None
    assert fresh._attr_translation_key is None
    assert "thermostat" in air.entity_id
    assert floor.entity_id.endswith("_floor_heating")
    assert fresh.entity_id.endswith("_fresh_air")
```

- [ ] **Step 2: Run the model tests and verify RED**

Run:

```bash
pytest -q tests/test_cnhdm_airrtc_wkq01.py
```

Expected: the global thermostat converter produces only one Climate grouping, and `climate.floor_heating`/`fan.fresh_air` are absent.

- [ ] **Step 3: Add the exact model customization**

Add this entry to `DEVICE_CUSTOMIZES` in `custom_components/xiaomi_miot/core/device_customizes.py`:

```python
    'cnhdm.airrtc.wkq01': {
        'converters': [
            {
                'class': MiotClimateConv,
                'services': ['thermostat'],
                'kwargs': {
                    'main_props': ['prop.2.1'],
                },
                'converters': [
                    {'props': ['prop.2.1'], 'desc': True},
                    {'props': ['prop.2.2'], 'desc': True},
                    {'props': ['prop.2.3']},
                    {'props': ['prop.2.5']},
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
                    {'props': ['prop.2.8']},
                    {'props': ['prop.2.10']},
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
                    {'props': ['prop.2.7'], 'desc': True},
                    {'props': ['prop.2.9']},
                ],
            },
        ],
        'sensor_properties': 'temperature',
        'switch_properties': 'physical_controls_locked',
    },
```

Do not extract these dictionaries into global constants.

- [ ] **Step 4: Preserve built-in customization in the fixture helper**

The initial helper intentionally accepts test-local customizations. Update `make_device` so `customizes=None` means “leave the repository's built-in model customization intact,” while an explicit dictionary still overrides it:

```python
        if model not in originals:
            originals[model] = DEVICE_CUSTOMIZES.get(model)
        if customizes is not None:
            DEVICE_CUSTOMIZES[model] = customizes
```

This replaces the earlier unconditional `DEVICE_CUSTOMIZES[model] = customizes or {}` line.

- [ ] **Step 5: Run model tests and verify GREEN**

Run:

```bash
pytest -q tests/test_cnhdm_airrtc_wkq01.py
```

Expected: `2 passed`.

- [ ] **Step 6: Commit the model mapping**

```bash
git add custom_components/xiaomi_miot/core/device_customizes.py tests/conftest.py tests/test_cnhdm_airrtc_wkq01.py
git commit -m "🌀 split cnhdm thermostat controls by function"
```

---

### Task 6: Pin Climate, Fan, complete entity-set, and MIoT write behavior

**Files:**
- Modify: `tests/test_cnhdm_airrtc_wkq01.py`

**Interfaces:**
- Consumes: model parent converters and existing `ClimateEntity`, `FanEntity`, ordered-list conversion, and `Device.encode()` behavior.
- Produces: full regression contract for six entities and control-isolated writes; no production Fan change is expected.

- [ ] **Step 1: Add entity collectors and complete entity-set assertions**

Append to `tests/test_cnhdm_airrtc_wkq01.py`:

```python
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.components.fan import FanEntityFeature
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.util.percentage import ordered_list_item_to_percentage

from custom_components.xiaomi_miot import button, sensor, switch  # noqa: F401


def collect_entities(device):
    collected = {domain: [] for domain in ["button", "climate", "fan", "sensor", "switch"]}
    for domain, entities in collected.items():
        device.entry.adders[domain] = lambda new, update_before_add=False, bucket=entities: bucket.extend(new)
        device.add_entities(domain)
    return collected


def test_complete_entity_set(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    entities = collect_entities(device)

    converter_domains = sorted(
        converter.domain
        for converter in device.converters
        if converter.domain is not None
    )
    assert converter_domains == ["button", "climate", "climate", "fan", "sensor", "switch"]
    assert {domain: len(values) for domain, values in entities.items()} == {
        "button": 1,
        "climate": 2,
        "fan": 1,
        "sensor": 1,
        "switch": 1,
    }
    assert sorted(entity._attr_name for entity in entities["climate"]) == ["Floor Heating", "Thermostat"]
    assert entities["fan"][0]._attr_name == "Fresh Air"
    assert entities["sensor"][0]._miot_property.unique_prop == "prop.3.1"
    assert entities["switch"][0]._miot_property.unique_prop == "prop.5.1"
    assert len(device.entities) == 6
```

- [ ] **Step 2: Add Climate state and write-boundary tests**

Append:

```python
def control_entities(device):
    climates = [
        ClimateEntity(device, converter)
        for converter in device.converters
        if isinstance(converter, MiotClimateConv)
    ]
    fans = [
        FanEntity(device, converter)
        for converter in device.converters
        if isinstance(converter, MiotFanConv)
    ]
    return climates[0], climates[1], fans[0]


def test_air_conditioner_modes_and_ventilation_preset(make_device, load_miot_spec):
    air, _, _ = control_entities(model_device(make_device, load_miot_spec))

    assert set(air.hvac_modes) == {HVACMode.OFF, HVACMode.AUTO, HVACMode.COOL, HVACMode.HEAT}
    assert "Ventilation" in air.preset_modes


def test_floor_heating_power_state_and_partial_updates(make_device, load_miot_spec):
    _, floor, _ = control_entities(model_device(make_device, load_miot_spec))
    assert set(floor.hvac_modes) == {HVACMode.OFF, HVACMode.HEAT}

    for power, mode, action in [
        (True, HVACMode.HEAT, HVACAction.HEATING),
        (True, HVACMode.HEAT, HVACAction.HEATING),
        (False, HVACMode.OFF, HVACAction.OFF),
        (False, HVACMode.OFF, HVACAction.OFF),
        (True, HVACMode.HEAT, HVACAction.HEATING),
    ]:
        floor.set_state({floor._conv_power.full_name: power})
        assert (floor.is_on, floor.hvac_mode, floor.hvac_action) == (power, mode, action)

    floor.set_state({floor._conv_target_temp.full_name: 28})
    assert (floor.is_on, floor.hvac_mode, floor.hvac_action, floor.target_temperature) == (
        True, HVACMode.HEAT, HVACAction.HEATING, 28,
    )
    floor.set_state({floor._conv_power.full_name: False, floor._conv_target_temp.full_name: 21})
    assert (floor.is_on, floor.hvac_mode, floor.hvac_action, floor.target_temperature) == (
        False, HVACMode.OFF, HVACAction.OFF, 21,
    )


@pytest.mark.asyncio
async def test_floor_heating_writes_only_assigned_properties(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    _, floor, _ = control_entities(device)
    device.async_set_properties = AsyncMock(return_value=[{"code": 0}])

    await floor.async_turn_on()
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 10, "value": True},
    ])

    device.async_set_properties.reset_mock()
    floor._attr_is_on = True
    await floor.async_set_hvac_mode(HVACMode.HEAT)
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 10, "value": True},
    ])

    device.async_set_properties.reset_mock()
    await floor.async_set_temperature(**{ATTR_TEMPERATURE: 27})
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 8, "value": 27},
    ])


@pytest.mark.asyncio
async def test_air_conditioner_writes_only_assigned_properties(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    air, _, _ = control_entities(device)
    device.async_set_properties = AsyncMock(return_value=[{"code": 0}])
    payloads = []

    await air.async_turn_on()
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 3, "value": True},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    air._attr_is_on = True
    air._attr_hvac_mode = HVACMode.HEAT
    await air.async_set_hvac_mode(HVACMode.COOL)
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 1, "value": 0},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    await air.async_set_temperature(**{ATTR_TEMPERATURE: 25})
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 5, "value": 25},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    await air.async_set_fan_mode("high")
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 2, "value": 3},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    assert {item["piid"] for params in payloads for item in params} == {1, 2, 3, 5}
    assert all(item["piid"] not in {7, 8, 9, 10} for params in payloads for item in params)
```

The Heat assertion deliberately expects a power write even when the cached state is already on, matching the approved requirement that selecting Heat reasserts only `prop.2.10`. Do not weaken this to a no-op and do not write a mode property because the floor-heating converter has none.

- [ ] **Step 3: Add Fan conversion and exact write tests**

Append:

```python
def test_fresh_air_speed_mapping(make_device, load_miot_spec):
    _, _, fan = control_entities(model_device(make_device, load_miot_spec))

    assert fan._conv_power.prop.unique_prop == "prop.2.9"
    assert fan._conv_speed.prop.unique_prop == "prop.2.7"
    assert fan.speed_count == 3
    assert fan.supported_features & FanEntityFeature.SET_SPEED

    for raw, description in [(1, "Low"), (2, "Medium"), (3, "High")]:
        fan.set_state({fan._conv_speed.full_name: description, fan._conv_power.full_name: True})
        assert fan.percentage == ordered_list_item_to_percentage(["Low", "Medium", "High"], description)
        encoded = fan.device.encode({fan._conv_speed.full_name: description})
        assert encoded["params"][0]["value"] == raw


@pytest.mark.asyncio
async def test_fresh_air_write_matrix(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    _, _, fan = control_entities(device)
    device.async_set_properties = AsyncMock(return_value=[{"code": 0}])
    payloads = []

    fan._attr_is_on = True
    await fan.async_set_percentage(1)
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 7, "value": 1},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    await fan.async_set_percentage(100)
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 7, "value": 3},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    fan._attr_is_on = False
    await fan.async_set_percentage(67)
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 9, "value": True},
        {"did": device.did, "siid": 2, "piid": 7, "value": 2},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    await fan.async_set_percentage(0)
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 9, "value": False},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    fan._attr_is_on = False
    await fan.async_turn_on()
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 9, "value": True},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    await fan.async_turn_off()
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 9, "value": False},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    assert all(item["piid"] not in {2, 3} for params in payloads for item in params)
```

The retained `payloads` list covers all six operations, proves percentages encode to raw levels 1, 2, and 3, and proves PIIDs 2 and 3 never occur.

- [ ] **Step 4: Run model runtime tests and verify behavior**

Run:

```bash
pytest -q tests/test_cnhdm_airrtc_wkq01.py -k "entity_set or modes or heating or air_conditioner or fresh_air"
```

Expected: all selected tests pass. The ordered-list assertions use Home Assistant's helper directly, and the retained payload list proves the complete approved Fan write matrix without duplicating Home Assistant's percentage-rounding implementation.

- [ ] **Step 5: Run all focused tests**

Run:

```bash
pytest -q tests/test_converter_options.py tests/test_cnhdm_airrtc_wkq01.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit runtime regressions**

```bash
git add tests/test_cnhdm_airrtc_wkq01.py
git commit -m "🧪 pin multi-control climate and fan behavior"
```

---

### Task 7: Prove Entity Registry migration and add stable pytest CI

**Files:**
- Modify: `tests/test_cnhdm_airrtc_wkq01.py`
- Modify: `.github/workflows/validate.yml`

**Interfaces:**
- Consumes: Home Assistant Entity Platform/Registry, `Device.add_entities()`, stable unique IDs from Tasks 3 and 5.
- Produces: one registry-backed upgrade/reload regression and one stable-only pytest workflow job.

- [ ] **Step 1: Add a real config-entry registry lifecycle test**

Append to `tests/test_cnhdm_airrtc_wkq01.py`. The integration's normal config-entry setup forwards every supported domain through Home Assistant's real Entity Platforms; patch only device I/O/spec loading so the test remains local and deterministic:

```python
from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_TOKEN
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_miot import DOMAIN
from custom_components.xiaomi_miot.core.device import Device


@pytest.mark.asyncio
async def test_registry_preserves_air_conditioner_identity_across_reload(
    hass,
    load_miot_spec,
):
    mac = "aa:bb:cc:dd:ee:ff"
    air_unique_id = f"{mac}-2"
    floor_unique_id = f"{mac}-floor_heating"
    fresh_unique_id = f"{mac}-fresh_air"
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "climate",
        DOMAIN,
        air_unique_id,
        suggested_object_id="living_room_ac",
    )
    registry.async_update_entity(old.entity_id, new_entity_id="climate.living_room_ac")
    original_registry_id = old.id

    spec = load_miot_spec("cnhdm.airrtc.wkq01.json")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "did": "test-device",
            "mac": mac,
            CONF_NAME: "Living Room Air System",
            CONF_HOST: "127.0.0.1",
            CONF_TOKEN: "0" * 32,
            "model": MODEL,
            "urn": spec.type,
        },
    )
    entry.add_to_hass(hass)

    async def async_init_from_fixture(device):
        device.spec = load_miot_spec("cnhdm.airrtc.wkq01.json")
        device.init_converters()

    def control_entries():
        return {
            item.unique_id: item
            for item in registry.entities.values()
            if item.platform == DOMAIN
            and item.domain in {"climate", "fan"}
        }

    with patch.object(Device, "async_init", async_init_from_fixture):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        first = control_entries()
        assert set(first) == {air_unique_id, floor_unique_id, fresh_unique_id}
        assert first[air_unique_id].id == original_registry_id
        assert first[air_unique_id].entity_id == "climate.living_room_ac"
        assert first[floor_unique_id].entity_id.endswith("_floor_heating")
        assert first[fresh_unique_id].entity_id.endswith("_fresh_air")
        assert len([item for item in first.values() if item.domain == "climate"]) == 2
        assert len([item for item in first.values() if item.domain == "fan"]) == 1
        first_ids = {unique_id: item.entity_id for unique_id, item in first.items()}

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

        reloaded = control_entries()
        assert set(reloaded) == {air_unique_id, floor_unique_id, fresh_unique_id}
        assert {unique_id: item.entity_id for unique_id, item in reloaded.items()} == first_ids
        assert reloaded[air_unique_id].id == original_registry_id
        assert len([item for item in reloaded.values() if item.domain == "climate"]) == 2
        assert len([item for item in reloaded.values() if item.domain == "fan"]) == 1
        assert not reloaded[floor_unique_id].entity_id.endswith(("_2", "_3"))
        assert not reloaded[fresh_unique_id].entity_id.endswith(("_2", "_3"))

        floor = next(
            entity
            for entity in hass.data[DOMAIN]["entities"].values()
            if entity.unique_id == floor_unique_id
        )
        floor.set_state({floor._conv_power.full_name: True})
        assert (floor.is_on, floor.hvac_mode, floor.hvac_action) == (
            True,
            HVACMode.HEAT,
            HVACAction.HEATING,
        )
```

The assertions intentionally capture the generated floor-heating and fresh-air entity IDs from the first real setup rather than assuming simplified IDs. Only their required attr-based suffixes are fixed; `MiotSpec.generate_entity_id()` also includes the model and MAC suffix.

- [ ] **Step 2: Run the registry lifecycle regression**

Run:

```bash
pytest -q tests/test_cnhdm_airrtc_wkq01.py::test_registry_preserves_air_conditioner_identity_across_reload
```

Expected: Home Assistant reuses the original `climate.living_room_ac` registry row, registers exactly two Climate and one Fan controls, preserves every entity ID through a real config-entry reload, creates no `_2`/`_3` collisions, and the reloaded floor entity establishes `HEAT/HEATING` on its first power update.

- [ ] **Step 3: Verify registry state is stable after reload**

Keep these invariant assertions in the completed test:

```python
assert reloaded[air_unique_id].id == original_registry_id
assert {unique_id: item.entity_id for unique_id, item in reloaded.items()} == first_ids
assert len([item for item in reloaded.values() if item.domain == "climate"]) == 2
assert len([item for item in reloaded.values() if item.domain == "fan"]) == 1
assert (floor.is_on, floor.hvac_mode, floor.hvac_action) == (
    True,
    HVACMode.HEAT,
    HVACAction.HEATING,
)
```

Run the same focused command. Expected: `1 passed`.

- [ ] **Step 4: Add a stable-only pytest workflow job**

Append a separate job to `.github/workflows/validate.yml` without changing `validate-homeassistant.strategy.matrix`:

```yaml
  test-pytest:
    name: Pytest with stable Home Assistant
    runs-on: ubuntu-latest
    steps:
      - name: 📥 Checkout the repository
        uses: actions/checkout@v4

      - name: 🐍 Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip

      - name: 📦 Install test dependencies
        run: pip install -r requirements_test.txt

      - name: 🧪 Run focused tests
        run: pytest -q
```

- [ ] **Step 5: Run complete local verification**

Run:

```bash
pytest -q
python3 -m compileall -q custom_components/xiaomi_miot tests
```

Expected: all tests pass and compileall exits 0.

- [ ] **Step 6: Inspect the workflow diff and preserve the existing matrix**

Run:

```bash
git diff -- .github/workflows/validate.yml
```

Expected: the diff only adds `test-pytest`; the existing line remains exactly:

```yaml
        channel: [stable, dev, "2023.7.0"]
```

- [ ] **Step 7: Commit registry and CI coverage**

```bash
git add tests/test_cnhdm_airrtc_wkq01.py .github/workflows/validate.yml
git commit -m "✅ verify converter entities in stable Home Assistant"
```

---

## Final Verification

- [ ] Run the focused suite:

```bash
pytest -q tests/test_converter_options.py tests/test_cnhdm_airrtc_wkq01.py
```

Expected: all tests pass.

- [ ] Run syntax compilation:

```bash
python3 -m compileall -q custom_components/xiaomi_miot tests
```

Expected: exit 0 with no output.

- [ ] Confirm no unintended files are staged:

```bash
git status --short
git diff --check
```

Expected: `git diff --check` exits 0; `.claude/settings.local.json` and `.claude/worktrees/` remain untracked and are not staged.

- [ ] Confirm design invariants in the finished suite:

```bash
pytest -q \
  tests/test_converter_options.py -k "model_converters or unique_id or fixed_mode or real_mode" \
  && pytest -q \
  tests/test_cnhdm_airrtc_wkq01.py -k "entity_set or mapping or registry or fresh_air or floor_heating"
```

Expected: both commands pass, covering replacement semantics, option precedence, real-mode precedence, six-entity mapping, isolated writes, and registry migration.
