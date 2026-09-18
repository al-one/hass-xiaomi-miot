"""Tests for media_player.py lazy micoapi bootstrap via HassEntry."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.xiaomi_miot import DOMAIN, init_integration_data
from custom_components.xiaomi_miot.core.hass_entry import HassEntry
from custom_components.xiaomi_miot.core.xiaomi_cloud import CloudSid


class _FakeEntity:
    """Replicates the new async_added_to_hass shape under test."""

    def __init__(self, hass, intelligent_speaker=True, entry_id="eid"):
        self.hass = hass
        self._intelligent_speaker = intelligent_speaker
        self._config = {"entry_id": entry_id} if entry_id else {}
        self.xiaoai_cloud = None
        self.unique_id = "u-uniq"
        self.name_model = "Fake Speaker"
        self.logger = SimpleNamespace(warning=lambda *a, **k: None)

    async def async_added_to_hass(self):
        self.xiaoai_cloud = None
        if not self._intelligent_speaker:
            return
        entry_id = (self._config or {}).get("entry_id")
        owner = (entry_id and self.hass.data.get(DOMAIN, {}).get(entry_id)) or None
        if owner is None:
            return
        try:
            self.xiaoai_cloud = await owner.async_get_cloud(CloudSid.MICOAPI)
        except Exception as exc:
            self.logger.warning("%s: micoapi bootstrap failed: %s", self.name_model, exc)
            self.xiaoai_cloud = None


def _make_owner(fake_cloud):
    return SimpleNamespace(
        async_get_cloud=AsyncMock(return_value=fake_cloud),
        clouds={},
        _cloud_lock=asyncio.Lock(),
        cloud=None,
        get_config=lambda k=None, d=None: d,
        filter_models=False,
        new_device=AsyncMock(),
        get_cloud_devices=AsyncMock(return_value={}),
        async_unload=AsyncMock(return_value=True),
    )


async def test_lazy_micoapi_probe_uses_owner(hass):
    init_integration_data(hass)
    fake_cloud = SimpleNamespace(sid="micoapi", async_check_micoapi_auth=AsyncMock(return_value=True))
    he = _make_owner(fake_cloud)
    HassEntry.ALL["eid"] = he
    hass.data[DOMAIN]["eid"] = he
    ent = _FakeEntity(hass)
    await ent.async_added_to_hass()
    he.async_get_cloud.assert_awaited_once_with(CloudSid.MICOAPI)
    assert ent.xiaoai_cloud is fake_cloud


async def test_no_owner_skips_micoapi_probe(hass):
    init_integration_data(hass)
    ent = _FakeEntity(hass, entry_id=None)
    await ent.async_added_to_hass()
    assert ent.xiaoai_cloud is None


async def test_non_speaker_skips_micoapi_probe(hass):
    init_integration_data(hass)
    ent = _FakeEntity(hass, intelligent_speaker=False)
    await ent.async_added_to_hass()
    assert ent.xiaoai_cloud is None


async def test_owner_failure_leaves_xiaoai_cloud_none(hass):
    init_integration_data(hass)

    class _OwnerBoom:
        async def async_get_cloud(self, sid):
            raise RuntimeError("nope")

    hass.data[DOMAIN]["eid"] = _OwnerBoom()
    ent = _FakeEntity(hass)
    await ent.async_added_to_hass()
    assert ent.xiaoai_cloud is None