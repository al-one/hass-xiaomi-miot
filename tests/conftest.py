import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.xiaomi_miot import DOMAIN, init_integration_data
from custom_components.xiaomi_miot.core.device import Device, DeviceInfo
from custom_components.xiaomi_miot.core.const import DATA_CUSTOMIZE
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
    hass.data.setdefault(DATA_CUSTOMIZE, {})


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
        if customizes is not None:
            DEVICE_CUSTOMIZES[model] = customizes

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
