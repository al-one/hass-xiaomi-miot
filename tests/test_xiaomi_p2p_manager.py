from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from custom_components.xiaomi_miot import init_integration_data
from custom_components.xiaomi_miot.core.const import DOMAIN
from custom_components.xiaomi_miot.core.hass_entry import HassEntry

from custom_components.xiaomi_miot.core.xiaomi_p2p import (
    DEFAULT_P2P_PROFILE,
    MediaContract,
    MissError,
    MissErrorCategory,
    SessionKey,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.manager import (
    ChannelSessionManager,
    LeaseKey,
)


def make_contract(video_codec: int = 4) -> MediaContract:
    return MediaContract(
        video_codec=video_codec,
        audio_codec=1027,
        video_sps=b"sps",
        video_pps=b"pps",
        vps=None,
        width=1920,
        height=1080,
        fps=20,
        sample_rate=8000,
        channels=1,
    )


def make_key(**changes) -> LeaseKey:
    values = {
        "entry_id": "entry-1",
        "region": "cn",
        "did": "device-1",
        "lens": "primary",
        "raw_quality": 2,
        "transport": "prefer_udp",
        "request_audio": True,
    }
    values.update(changes)
    return LeaseKey(**values)


@dataclass
class FakeSession:
    contract: MediaContract = field(default_factory=make_contract)
    generation: int = 1
    connect_calls: int = 0
    acquire_calls: int = 0
    release_calls: int = 0
    stop_calls: int = 0
    close_calls: int = 0
    read_started: asyncio.Event = field(default_factory=asyncio.Event)
    read_gate: asyncio.Event = field(default_factory=asyncio.Event)
    video_fresh: bool = True
    recovery_calls: int = 0
    subscriptions: dict[SessionKey, tuple[asyncio.Queue, asyncio.Event]] = field(
        default_factory=dict
    )

    async def connect_and_start(self, deadline: float) -> MediaContract:
        self.connect_calls += 1
        return self.contract

    def acquire_lease(self) -> None:
        self.acquire_calls += 1

    def release_lease(self) -> None:
        self.release_calls += 1

    def subscribe_frames(self, generation: int):
        assert generation == self.generation
        key = SessionKey(token=f"sub-{len(self.subscriptions)}".encode())
        queue: asyncio.Queue = asyncio.Queue()
        changed = asyncio.Event()
        self.subscriptions[key] = (queue, changed)
        return key, queue, changed

    def unsubscribe_frames(self, key: SessionKey) -> None:
        queue, _changed = self.subscriptions.pop(key)
        queue.put_nowait(None)

    async def read_and_publish(self, timeout: float) -> None:
        self.read_started.set()
        await self.read_gate.wait()

    async def run_stall_recovery(self, *, deadline: float) -> MediaContract:
        self.recovery_calls += 1
        self.video_fresh = True
        return self.contract

    def has_recent_video(self, max_age: float) -> bool:
        assert max_age == 10.0
        return self.video_fresh

    async def stop_media(self) -> None:
        self.stop_calls += 1

    async def close(self) -> None:
        self.close_calls += 1


@pytest.fixture
def manager_parts():
    sessions: list[FakeSession] = []

    def factory(_key: LeaseKey, _deadline: float) -> FakeSession:
        session = FakeSession()
        sessions.append(session)
        return session

    manager = ChannelSessionManager(
        session_factory=factory,
        idle_timeout=0.01,
    )
    return manager, sessions


async def test_four_gets_share_session_and_fifth_is_rejected(manager_parts):
    manager, sessions = manager_parts
    leases = [await manager.acquire(make_key(), deadline=100) for _ in range(4)]

    assert len({id(lease.session) for lease in leases}) == 1
    assert len(sessions) == 1
    with pytest.raises(MissError) as excinfo:
        await manager.acquire(make_key(), deadline=100)
    assert excinfo.value.category is MissErrorCategory.MEDIA
    assert excinfo.value.detail == "active_source_limit"

    for lease in leases:
        await lease.release()
    await manager.async_close()


async def test_lenses_entries_and_regions_are_isolated(manager_parts):
    manager, _sessions = manager_parts
    primary = await manager.acquire(make_key(), deadline=100)
    secondary = await manager.acquire(make_key(lens="secondary"), deadline=100)
    other_entry = await manager.acquire(make_key(entry_id="entry-2"), deadline=100)
    other_region = await manager.acquire(make_key(region="de"), deadline=100)

    assert len({id(lease.session) for lease in (
        primary, secondary, other_entry, other_region
    )}) == 4
    await manager.async_close()


async def test_lease_captures_contract_generation_and_frames(manager_parts):
    manager, _sessions = manager_parts
    lease = await manager.acquire(make_key(), deadline=100)
    queue, changed = lease.session.subscriptions[lease.subscription_key]
    queue.put_nowait(b"frame")

    assert lease.contract == make_contract()
    assert lease.generation == 1
    assert await lease.next_frame() == b"frame"
    assert lease.contract_changed is changed
    await manager.async_close()


async def test_release_is_exact_once_and_final_release_starts_idle_timer(
    manager_parts,
):
    manager, sessions = manager_parts
    first = await manager.acquire(make_key(), deadline=100)
    second = await manager.acquire(make_key(), deadline=100)

    await first.release()
    await first.release()
    assert sessions[0].release_calls == 1
    await asyncio.sleep(0.02)
    assert sessions[0].close_calls == 0

    await second.release()
    assert sessions[0].stop_calls == 0
    await asyncio.sleep(0.02)
    assert sessions[0].stop_calls == 1
    assert sessions[0].close_calls == 1
    await manager.async_close()


async def test_reacquire_before_idle_expiry_reuses_session(manager_parts):
    manager, sessions = manager_parts
    first = await manager.acquire(make_key(), deadline=100)
    await first.release()
    await asyncio.sleep(0)
    second = await manager.acquire(make_key(), deadline=100)

    assert second.session is first.session
    assert len(sessions) == 1
    await manager.async_close()




async def test_reacquire_fresh_idle_session_does_not_recover(manager_parts):
    manager, sessions = manager_parts
    first = await manager.acquire(make_key(), deadline=100)
    await first.release()

    second = await manager.acquire(make_key(), deadline=100)

    assert second.session is first.session
    assert sessions[0].recovery_calls == 0
    await manager.async_close()


async def test_reacquire_stale_idle_session_recovers_immediately(manager_parts):
    manager, sessions = manager_parts
    first = await manager.acquire(make_key(), deadline=100)
    await first.release()
    sessions[0].video_fresh = False

    second = await manager.acquire(make_key(), deadline=100)

    assert second.session is first.session
    assert sessions[0].recovery_calls == 1
    await manager.async_close()


async def test_idle_expiry_removes_session_for_later_acquire(manager_parts):
    manager, sessions = manager_parts
    first = await manager.acquire(make_key(), deadline=100)
    await first.release()
    await asyncio.sleep(0.02)
    second = await manager.acquire(make_key(), deadline=100)

    assert second.session is not first.session
    assert len(sessions) == 2
    await manager.async_close()




async def test_one_manager_reader_is_shared_by_all_leases(manager_parts):
    manager, sessions = manager_parts
    leases = [await manager.acquire(make_key(), deadline=100) for _ in range(4)]

    await asyncio.wait_for(sessions[0].read_started.wait(), 0.1)
    assert len(sessions) == 1

    for lease in leases:
        await lease.release()
    await manager.async_close()


async def test_snapshot_excludes_sensitive_session_key_fields(manager_parts):
    manager, _sessions = manager_parts
    lease = await manager.acquire(make_key(), deadline=100)

    snapshot = manager.snapshot()

    assert snapshot == ({
        "lens": "primary",
        "generation": 1,
        "active_leases": 1,
    },)
    assert "did" not in repr(snapshot)
    assert "region" not in repr(snapshot)
    await lease.release()
    await manager.async_close()


async def test_async_close_closes_active_session_and_unblocks_frame_waiter(
    manager_parts,
):
    manager, sessions = manager_parts
    lease = await manager.acquire(make_key(), deadline=100)
    waiter = asyncio.create_task(lease.next_frame())
    await manager.async_close()

    assert await waiter is None
    assert sessions[0].close_calls == 1


class FakeLoopbackServer:
    def __init__(self) -> None:
        self.acquire_calls = 0
        self.release_calls = 0
        self.acquire_gate = asyncio.Event()
        self.acquire_gate.set()

    async def acquire_entry(self) -> None:
        self.acquire_calls += 1
        await self.acquire_gate.wait()

    async def release_entry(self) -> None:
        self.release_calls += 1


class FakeManager:
    def __init__(self) -> None:
        self.close_calls = 0

    async def async_close(self) -> None:
        self.close_calls += 1


def make_hass_entry(*, eligible: bool = True):
    hass = SimpleNamespace(data={})
    init_integration_data(hass)
    entry = SimpleNamespace(entry_id="entry-1", data={}, options={})
    owner = HassEntry(hass, entry)
    owner.devices = {
        "device": SimpleNamespace(p2p_enabled=eligible)
    }
    server = FakeLoopbackServer()
    hass.data[DOMAIN]["p2p_media_server"] = server
    return owner, server


def test_integration_data_owns_single_p2p_resources():
    hass = SimpleNamespace(data={})

    init_integration_data(hass)
    first = (
        hass.data[DOMAIN]["p2p_media_server"],
        hass.data[DOMAIN]["p2p_port_allocator"],
        hass.data[DOMAIN]["p2p_capability_cache"],
    )
    init_integration_data(hass)

    assert first == (
        hass.data[DOMAIN]["p2p_media_server"],
        hass.data[DOMAIN]["p2p_port_allocator"],
        hass.data[DOMAIN]["p2p_capability_cache"],
    )


async def test_async_ensure_p2p_is_single_flight(monkeypatch):
    owner, server = make_hass_entry()
    manager = FakeManager()
    create_calls = 0

    def create_manager():
        nonlocal create_calls
        create_calls += 1
        return manager

    monkeypatch.setattr(owner, "_create_p2p_manager", create_manager)
    server.acquire_gate.clear()
    first = asyncio.create_task(owner.async_ensure_p2p())
    second = asyncio.create_task(owner.async_ensure_p2p())
    await asyncio.sleep(0)
    server.acquire_gate.set()

    assert await first is manager
    assert await second is manager
    assert create_calls == 1
    assert server.acquire_calls == 1


async def test_ineligible_entry_does_not_acquire_p2p_resources(monkeypatch):
    owner, server = make_hass_entry(eligible=False)
    monkeypatch.setattr(
        owner,
        "_create_p2p_manager",
        lambda: pytest.fail("manager must not be created"),
    )

    assert await owner.async_ensure_p2p() is None
    assert server.acquire_calls == 0


async def test_close_p2p_releases_manager_and_server_once(monkeypatch):
    owner, server = make_hass_entry()
    manager = FakeManager()
    monkeypatch.setattr(owner, "_create_p2p_manager", lambda: manager)
    await owner.async_ensure_p2p()

    await owner.async_close_p2p()
    await owner.async_close_p2p()

    assert manager.close_calls == 1
    assert server.release_calls == 1


async def test_entry_session_factory_propagates_fresh_deadlines(monkeypatch):
    owner, _server = make_hass_entry()
    owner.did_to_unique = {"device-1": "device"}
    owner.devices = {
        "device": SimpleNamespace(
            p2p_enabled=True,
            p2p_profile=DEFAULT_P2P_PROFILE,
            info=SimpleNamespace(host="192.168.1.2"),
        )
    }
    cloud = object()

    async def get_cloud():
        return cloud

    owner.get_cloud = get_cloud
    calls = []
    bootstraps = [object(), object()]
    transports = [SimpleNamespace(), SimpleNamespace()]

    async def get_bootstrap(actual_cloud, did, host, deadline):
        calls.append(("bootstrap", actual_cloud, did, host, deadline))
        index = sum(call[0] == "bootstrap" for call in calls) - 1
        return bootstraps[index]

    class FakeConnector:
        async def connect(self, bootstrap, policy, deadline):
            calls.append(("connect", bootstrap, policy, deadline))
            index = sum(call[0] == "connect" for call in calls) - 1
            return transports[index]

    monkeypatch.setattr(
        "custom_components.xiaomi_miot.core.xiaomi_p2p.cloud.async_miss_get_vendor_impl",
        get_bootstrap,
    )
    monkeypatch.setattr(
        "custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.discovery.create_default_connector",
        lambda _clock: FakeConnector(),
    )

    session = await owner._create_p2p_session(make_key(), 25.0)
    reconnect = await session.bootstrap_factory(40.0)

    assert session.bootstrap is bootstraps[0]
    assert session.transport is transports[0]
    assert reconnect == (bootstraps[1], transports[1])
    assert calls == [
        ("bootstrap", cloud, "device-1", "192.168.1.2", 25.0),
        ("connect", bootstraps[0], "prefer_udp", 25.0),
        ("bootstrap", cloud, "device-1", "192.168.1.2", 40.0),
        ("connect", bootstraps[1], "prefer_udp", 40.0),
    ]
