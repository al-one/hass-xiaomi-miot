"""Deterministic clock for MISS+CS2 tests.

The real clock MUST NOT be used by transport state machines; tests
should advance a `FakeClock` and rely on it exclusively.
"""

from __future__ import annotations

import asyncio


class FakeClock:
    def __init__(self, *, start: float = 1000.0) -> None:
        self._now = start

    @property
    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("FakeClock cannot rewind")
        self._now += seconds

    async def sleep(self, seconds: float) -> None:
        # The clock advances even when no task awaits the sleep, so tests
        # can deterministically fast-forward past retransmission timers.
        self._now += seconds
        await asyncio.sleep(0)