import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.xiaomi_miot import DOMAIN, init_integration_data
from custom_components.xiaomi_miot.core.device import Device, DeviceInfo
from custom_components.xiaomi_miot.core.const import (
    CONF_CONN_MODE,
    DATA_CUSTOMIZE,
)
from homeassistant.const import CONF_USERNAME
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


@pytest.fixture
def make_p2p_device(hass, load_miot_spec, request):
    """Factory that builds a Device whose P2P preflight is fully mocked.

    Returns an async function ``make(fixture_name, account, conn_mode, vendor)``
    that:
      * loads the MIoT spec from ``tests/fixtures/<fixture_name>``,
      * attaches a mock entry whose ``cloud`` and ``p2p_cache`` are configured
        to mirror the chosen account ownership, connection mode, and vendor
        preflight result,
      * awaits ``Device.async_init`` so the production preflight path runs,
      * yields the resulting Device with the resolved ``p2p_*`` state.
    """

    originals: dict[str, object | None] = {}

    def _entry_config(config):
        def _get(key=None, default=None):
            if key is None:
                return config
            return config.get(key, default)

        return _get

    async def _make(
        fixture_name: str,
        *,
        account: bool = False,
        conn_mode: str = "auto",
        vendor: int | None = 4,
        host: str = "192.168.1.20",
        did: str = "device-did",
        model: str | None = None,
        entry_id: str = "test-entry",
    ) -> Device:
        spec = load_miot_spec(fixture_name)
        if model is None:
            model = (
                spec.type.split(":")[4]
                if ":" in spec.type
                else "test.device.model"
            )
        if model not in originals:
            originals[model] = DEVICE_CUSTOMIZES.get(model)

        config: dict = {CONF_CONN_MODE: conn_mode}
        if account:
            config[CONF_USERNAME] = "account-user"

        cloud = MagicMock(name="cloud") if account else None
        if cloud is not None:
            cloud.default_server = "cn"

        cache = MagicMock(name="p2p_cache")
        if vendor is None:
            cache.get_or_probe = AsyncMock(side_effect=AssertionError("should not probe"))
        else:
            cache.get_or_probe = AsyncMock(return_value=vendor)

        entry = SimpleNamespace(
            hass=hass,
            cloud=cloud,
            id=entry_id,
            adders={},
            get_config=_entry_config(config),
            p2p_cache=cache,
        )

        info = DeviceInfo({
            "did": did,
            "mac": "aa:bb:cc:dd:ee:ff",
            "name": "Test Camera",
            "model": model,
            "urn": spec.type,
            "localip": host,
        })
        device = Device(info, entry)
        device.spec = spec
        device.init_converters()
        await device.async_init()
        return device

    def restore():
        for model, original in originals.items():
            if original is None:
                DEVICE_CUSTOMIZES.pop(model, None)
            else:
                DEVICE_CUSTOMIZES[model] = original

    request.addfinalizer(restore)
    return _make
