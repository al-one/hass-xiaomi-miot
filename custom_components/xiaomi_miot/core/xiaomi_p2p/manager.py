"""Entry-owned MISS session sharing and generation-bound leases."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import MediaContract, MissError, MissErrorCategory, SessionKey


class MonotonicClock:
    @property
    def now(self) -> float:
        return time.monotonic()

    async def sleep(self, delay: float) -> None:
        await asyncio.sleep(delay)


@dataclass(frozen=True, slots=True)
class LeaseKey:
    entry_id: str
    region: str
    did: str = field(repr=False)
    lens: str
    raw_quality: int
    transport: str
    request_audio: bool


@dataclass(slots=True)
class SessionLease:
    session: Any = field(repr=False)
    contract: MediaContract
    generation: int
    contract_changed: asyncio.Event = field(repr=False)
    subscription_key: SessionKey = field(repr=False)
    _frames: asyncio.Queue[Any] = field(repr=False)
    _manager: ChannelSessionManager = field(repr=False)
    _released: bool = field(default=False, init=False, repr=False)

    async def next_frame(self) -> Any:
        return await self._frames.get()

    async def release(self) -> None:
        await self._manager.release(self)


@dataclass(slots=True)
class _SessionRecord:
    key: LeaseKey
    session: Any = field(repr=False)
    leases: list[SessionLease] = field(default_factory=list, repr=False)
    idle_task: asyncio.Task[None] | None = field(default=None, repr=False)
    reader_task: asyncio.Task[None] | None = field(default=None, repr=False)


class ChannelSessionManager:
    MAX_ACTIVE_SOURCES = 4
    IDLE_TIMEOUT = 30.0

    def __init__(
        self,
        *,
        session_factory: Callable[[LeaseKey, float], Any],
        idle_timeout: float = IDLE_TIMEOUT,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self._session_factory = session_factory
        self._idle_timeout = idle_timeout
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._records: dict[LeaseKey, _SessionRecord] = {}
        self._bridges: set[Any] = set()
        self._closed = False

    async def acquire(self, key: LeaseKey, deadline: float) -> SessionLease:
        async with self._lock:
            if self._closed:
                raise MissError(MissErrorCategory.MEDIA, "manager_closed")
            record = self._records.get(key)
            reused = record is not None
            if record is None:
                session = self._session_factory(key, deadline)
                if inspect.isawaitable(session):
                    session = await session
                await session.connect_and_start(deadline)
                record = _SessionRecord(key=key, session=session)
                if hasattr(session, "read_and_publish"):
                    record.reader_task = asyncio.create_task(
                        self._read_session(record)
                    )
                self._records[key] = record
            elif record.idle_task is not None:
                record.idle_task.cancel()
                record.idle_task = None
            if len(record.leases) >= self.MAX_ACTIVE_SOURCES:
                raise MissError(MissErrorCategory.MEDIA, "active_source_limit")
            record.session.acquire_lease()
            try:
                if reused and not record.session.has_recent_video(10.0):
                    await record.session.run_stall_recovery(deadline=deadline)
                contract = record.session.contract
                if contract is None:
                    raise MissError(MissErrorCategory.MEDIA, "contract_missing")
                subscription_key, frames, changed = record.session.subscribe_frames(
                    record.session.generation
                )
            except BaseException:
                record.session.release_lease()
                raise
            lease = SessionLease(
                session=record.session,
                contract=contract,
                generation=record.session.generation,
                contract_changed=changed,
                subscription_key=subscription_key,
                _frames=frames,
                _manager=self,
            )
            record.leases.append(lease)
            return lease

    async def release(self, lease: SessionLease) -> None:
        async with self._lock:
            if lease._released:
                return
            lease._released = True
            record = self._record_for_session(lease.session)
            if record is None:
                return
            if lease in record.leases:
                record.leases.remove(lease)
            lease.session.unsubscribe_frames(lease.subscription_key)
            lease.session.release_lease()
            if not record.leases and record.idle_task is None:
                record.idle_task = asyncio.create_task(self._expire_idle(record))

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "lens": record.key.lens,
                "generation": record.session.generation,
                "active_leases": len(record.leases),
            }
            for record in self._records.values()
        )

    def register_bridge(self, bridge: Any) -> None:
        self._bridges.add(bridge)

    def unregister_bridge(self, bridge: Any) -> None:
        self._bridges.discard(bridge)

    async def close_bridges(self) -> None:
        bridges, self._bridges = tuple(self._bridges), set()
        if bridges:
            await asyncio.gather(
                *(bridge.request_close("unload") for bridge in bridges),
                return_exceptions=True,
            )

    async def async_close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            records, self._records = tuple(self._records.values()), {}
            readers = []
            for record in records:
                if record.idle_task is not None:
                    record.idle_task.cancel()
                if record.reader_task is not None:
                    record.reader_task.cancel()
                    readers.append(record.reader_task)
                for lease in tuple(record.leases):
                    if not lease._released:
                        lease._released = True
                        record.session.unsubscribe_frames(lease.subscription_key)
                        record.session.release_lease()
                record.leases.clear()
        await self.close_bridges()
        if readers:
            await asyncio.gather(*readers, return_exceptions=True)
        await asyncio.gather(
            *(record.session.close() for record in records),
            return_exceptions=True,
        )

    async def _read_session(self, record: _SessionRecord) -> None:
        while True:
            try:
                await record.session.read_and_publish(timeout=1.0)
            except asyncio.CancelledError:
                return
            except MissError as err:
                if err.category is MissErrorCategory.TIMEOUT:
                    continue
                for lease in tuple(record.leases):
                    lease.contract_changed.set()
                return

    async def _expire_idle(self, record: _SessionRecord) -> None:
        try:
            await self._sleep(self._idle_timeout)
            async with self._lock:
                if record.leases or self._records.get(record.key) is not record:
                    return
                self._records.pop(record.key, None)
                record.idle_task = None
            if record.reader_task is not None:
                record.reader_task.cancel()
                await asyncio.gather(record.reader_task, return_exceptions=True)
            try:
                await record.session.stop_media()
            finally:
                await record.session.close()
        except asyncio.CancelledError:
            return

    def _record_for_session(self, session: Any) -> _SessionRecord | None:
        return next(
            (
                record
                for record in self._records.values()
                if record.session is session
            ),
            None,
        )


__all__ = ["ChannelSessionManager", "LeaseKey", "SessionLease"]
