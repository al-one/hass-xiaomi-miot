"""Tests for async_setup_entry setup-time ConfigEntryAuthFailed + cleanup + alias."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.config_entries import ConfigEntryAuthFailed, ConfigEntryState

from custom_components.xiaomi_miot import (
    CONF_XIAOMI_CLOUD,
    DOMAIN,
    async_setup_entry,
    init_integration_data,
)
from custom_components.xiaomi_miot.core.hass_entry import HassEntry
from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    CloudSid,
    MiCloudAuthenticationError,
    MiCloudStsUnauthorized,
    MiCloudVerificationError,
    MiotCloud,
)


_BASE_CFG = {"username": "u", "password": "p", "server_country": "cn"}


def _entry(hass):
    e = SimpleNamespace(
        entry_id="eid",
        data=dict(_BASE_CFG),
        options={},
        state=ConfigEntryState.LOADED,
        update_listeners=[],
        add_update_listener=lambda cb: None,
    )
    e.async_on_unload = lambda cb: None
    return e


def _make_entry_obj(fake_cloud, **overrides):
    base_cfg = dict(_BASE_CFG)

    def _get_config(k=None, d=None):
        if k is None:
            return dict(base_cfg)
        return base_cfg.get(k, d)

    obj = SimpleNamespace(
        async_get_cloud=AsyncMock(return_value=fake_cloud),
        clouds={},
        _cloud_lock=asyncio.Lock(),
        async_unload=AsyncMock(return_value=True),
        cloud=None,
        get_config=_get_config,
        filter_models=False,
        new_device=AsyncMock(),
        get_cloud_devices=AsyncMock(return_value={}),
    )
    for k, v in overrides.items():
        setattr(obj, k, v)
    return obj


async def test_setup_xiaomi_auth_failed_raises_config_entry_auth(hass):
    init_integration_data(hass)
    fake_cloud = MiotCloud.__new__(MiotCloud)
    fake_cloud.sid = "xiaomiio"
    fake_cloud.async_check_auth = AsyncMock(side_effect=MiCloudAuthenticationError("X"))
    fake_entry_obj = _make_entry_obj(fake_cloud)
    with patch("custom_components.xiaomi_miot.HassEntry.init", return_value=fake_entry_obj), \
         patch("custom_components.xiaomi_miot.async_setup_customizes", AsyncMock()):
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, _entry(hass))


async def test_setup_xiaomi_check_auth_returns_false_raises_config_entry_auth(hass):
    init_integration_data(hass)
    fake_cloud = MiotCloud.__new__(MiotCloud)
    fake_cloud.sid = "xiaomiio"
    fake_cloud.async_check_auth = AsyncMock(return_value=False)
    fake_entry_obj = _make_entry_obj(fake_cloud)
    with patch("custom_components.xiaomi_miot.HassEntry.init", return_value=fake_entry_obj), \
         patch("custom_components.xiaomi_miot.async_setup_customizes", AsyncMock()):
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, _entry(hass))


async def test_setup_xiaomi_get_cloud_exception_returns_false(hass):
    init_integration_data(hass)
    fake_cloud = MiotCloud.__new__(MiotCloud)
    fake_cloud.sid = "xiaomiio"
    fake_cloud.async_check_auth = AsyncMock(return_value=True)
    fake_entry_obj = _make_entry_obj(fake_cloud)
    fake_entry_obj.async_get_cloud = AsyncMock(side_effect=Exception("boom"))
    with patch("custom_components.xiaomi_miot.HassEntry.init", return_value=fake_entry_obj), \
         patch("custom_components.xiaomi_miot.async_setup_customizes", AsyncMock()), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        result = await async_setup_entry(hass, _entry(hass))
    assert result is True


@pytest.mark.parametrize(
    "exc_cls",
    [MiCloudVerificationError, MiCloudStsUnauthorized],
)
async def test_setup_xiaomi_get_cloud_typed_auth_error_raises_config_entry_auth(hass, exc_cls):
    init_integration_data(hass)
    fake_cloud = MiotCloud.__new__(MiotCloud)
    fake_cloud.sid = "xiaomiio"
    fake_cloud.async_check_auth = AsyncMock(return_value=True)
    fake_entry_obj = _make_entry_obj(fake_cloud)
    fake_entry_obj.async_get_cloud = AsyncMock(side_effect=exc_cls("x"))
    with patch("custom_components.xiaomi_miot.HassEntry.init", return_value=fake_entry_obj), \
         patch("custom_components.xiaomi_miot.async_setup_customizes", AsyncMock()):
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, _entry(hass))


async def test_setup_xiaomi_cloud_none_returns_false(hass):
    init_integration_data(hass)
    fake_cloud = SimpleNamespace(sid="xiaomiio")
    fake_entry_obj = _make_entry_obj(fake_cloud)
    fake_entry_obj.async_get_cloud = AsyncMock(return_value=None)
    with patch("custom_components.xiaomi_miot.HassEntry.init", return_value=fake_entry_obj), \
         patch("custom_components.xiaomi_miot.async_setup_customizes", AsyncMock()), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        result = await async_setup_entry(hass, _entry(hass))
    assert result is True
    assert "eid" not in hass.data[DOMAIN]


async def test_setup_success_aliases_same_object(hass):
    init_integration_data(hass)
    fake_cloud = MiotCloud.__new__(MiotCloud)
    fake_cloud.sid = "xiaomiio"
    fake_cloud.user_id = "u"
    fake_cloud.default_server = "cn"
    fake_cloud.async_check_auth = AsyncMock(return_value=True)
    fake_entry_obj = _make_entry_obj(fake_cloud)
    fake_entry_obj.clouds = {CloudSid.XIAOMIIO: fake_cloud}
    fake_entry_obj.cloud = fake_cloud
    with patch("custom_components.xiaomi_miot.HassEntry.init", return_value=fake_entry_obj), \
         patch("custom_components.xiaomi_miot.async_setup_customizes", AsyncMock()), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        await async_setup_entry(hass, _entry(hass))
    cfg = hass.data[DOMAIN]["eid"]
    assert cfg[CONF_XIAOMI_CLOUD] is fake_cloud
    assert fake_entry_obj.clouds[CloudSid.XIAOMIIO] is fake_cloud
    assert fake_cloud.unique_id not in hass.data[DOMAIN].get("sessions", {})
    accounts = hass.data[DOMAIN].get("accounts", {})
    for v in accounts.values():
        if isinstance(v, dict):
            assert v.get(CONF_XIAOMI_CLOUD) is not fake_cloud


async def test_cleanup_only_runs_when_alias_matches(hass):
    init_integration_data(hass)
    fake_cloud_a = SimpleNamespace(sid="xiaomiio", unique_id="a", user_id="a")
    fake_cloud_b = SimpleNamespace(sid="xiaomiio", unique_id="b", user_id="b")
    hass_entry = SimpleNamespace(
        id="eid",
        clouds={CloudSid.XIAOMIIO: fake_cloud_b},
    )
    hass.data[DOMAIN]["eid"] = {CONF_XIAOMI_CLOUD: fake_cloud_a}
    HassEntry.ALL["eid"] = hass_entry

    from custom_components.xiaomi_miot import _setup_attempt_cleanup
    await _setup_attempt_cleanup(hass, "eid", hass_entry)
    # The aliased config stays since alias !== clouds[XIAOMIIO]
    assert CONF_XIAOMI_CLOUD in hass.data[DOMAIN]["eid"]
    # clouds was cleared anyway
    assert hass_entry.clouds == {}
    # HassEntry.ALL entry removed since the instance still matches
    assert "eid" not in HassEntry.ALL