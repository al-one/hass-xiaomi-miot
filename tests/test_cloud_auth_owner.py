"""Tests for owner awareness — hass_entry propagation through MiotCloud lifecycle."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.xiaomi_miot import init_integration_data
from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud


def _entry():
    return SimpleNamespace()


def _cloud(hass, **kw):
    return MiotCloud(hass, "u", "p", "cn", "xiaomiio", **kw)


async def test_miot_cloud_init_accepts_hass_entry(hass):
    fake_entry = SimpleNamespace()
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio", hass_entry=fake_entry)
    assert c.hass_entry is fake_entry


async def test_miot_cloud_init_default_hass_entry_is_none(hass):
    init_integration_data(hass)
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    assert c.hass_entry is None


async def test_entry_bound_login_skips_global_session(hass):
    init_integration_data(hass)
    fake_entry = SimpleNamespace()
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio", hass_entry=fake_entry)
    c._login_request = lambda login_data=None: True
    with patch.object(c, "async_stored_auth", AsyncMock(return_value={})):
        await c.async_login()
    assert c.unique_id not in hass.data["xiaomi_miot"]["sessions"]


async def test_entry_bound_change_sid_keeps_owner(hass):
    init_integration_data(hass)
    fake_entry = SimpleNamespace()
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio", hass_entry=fake_entry)
    c._login_request = lambda login_data=None: True

    async def _persist(self, *args, **kwargs):
        return {}

    # Patch on the class so the new MiotCloud created inside from_token
    # also sees the stub.
    with patch.object(MiotCloud, "async_stored_auth", _persist), \
         patch.object(MiotCloud, "async_login", AsyncMock(return_value=True)):
        new = await c.async_change_sid("micoapi")
    assert new.hass_entry is fake_entry
    assert new.sid == "micoapi"


async def test_ownerless_login_registers_in_sessions(hass):
    init_integration_data(hass)
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    c._login_request = lambda login_data=None: True
    with patch.object(c, "async_stored_auth", AsyncMock(return_value={})):
        await c.async_login()
    assert hass.data["xiaomi_miot"]["sessions"][c.unique_id] is c


async def test_from_token_reused_session_clones_with_new_hass_entry(hass):
    """Cache hit must clone the cached mic, then attach the new hass_entry
    so reauth notifications route to the correct entry."""
    init_integration_data(hass)
    cached = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    cached.user_id = "u"
    cached.service_token = "TOK"
    hass.data["xiaomi_miot"]["sessions"][cached.unique_id] = cached

    fake_entry = SimpleNamespace()
    out = await MiotCloud.from_token(
        hass,
        {"username": "u", "password": "p", "server_country": "cn",
         "sid": "xiaomiio", "user_id": "u", "service_token": "TOK"},
        login=False,
        hass_entry=fake_entry,
    )

    assert out is not cached
    assert out.hass_entry is fake_entry
    assert cached.hass_entry is None


async def test_from_token_reused_session_does_not_mutate_cached_state(hass):
    """merger_config on the clone must not affect the cached mic's session."""
    init_integration_data(hass)
    cached = MiotCloud(hass, "u", "OLD", "cn", "xiaomiio")
    cached.user_id = "u"
    cached.service_token = "CACHED_TOK"
    cached.ssecurity = "CACHED_SEC"
    hass.data["xiaomi_miot"]["sessions"][cached.unique_id] = cached

    fake_entry = SimpleNamespace()
    out = await MiotCloud.from_token(
        hass,
        {"username": "u", "password": "NEW", "server_country": "cn",
         "sid": "xiaomiio", "user_id": "u"},
        login=False,
        hass_entry=fake_entry,
    )

    assert out.password == "NEW"
    assert out.service_token is None
    assert out.ssecurity is None
    assert cached.password == "OLD"
    assert cached.service_token == "CACHED_TOK"
    assert cached.ssecurity == "CACHED_SEC"


async def test_from_token_reused_session_without_hass_entry_keeps_none(hass):
    """If caller still passes hass_entry=None, clone's hass_entry stays None."""
    init_integration_data(hass)
    cached = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    cached.user_id = "u"
    hass.data["xiaomi_miot"]["sessions"][cached.unique_id] = cached

    out = await MiotCloud.from_token(
        hass,
        {"username": "u", "password": "p", "server_country": "cn",
         "sid": "xiaomiio", "user_id": "u"},
        login=False,
    )

    assert out is not cached
    assert out.hass_entry is None