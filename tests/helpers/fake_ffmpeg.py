from __future__ import annotations

import asyncio


class FakePipe:
    def __init__(self) -> None:
        self._chunks: asyncio.Queue[bytes] = asyncio.Queue()
        self.closed = False
        self.readers = 0
        self.writes: list[bytes] = []

    def feed(self, chunk: bytes) -> None:
        self._chunks.put_nowait(chunk)

    async def read(self, _size: int) -> bytes:
        self.readers += 1
        try:
            return await self._chunks.get()
        finally:
            self.readers -= 1

    def write(self, body: bytes) -> None:
        self.writes.append(body)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._chunks.put_nowait(b"")

    async def wait_closed(self) -> None:
        await asyncio.sleep(0)


class FakeFfmpegProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.started = asyncio.Event()
        self.stdin = FakePipe()
        self.stdout = FakePipe()
        self.stderr = FakePipe()
        self.terminated = 0
        self.killed = 0
        self.wait_calls = 0
        self._exited = asyncio.Event()

    async def wait(self) -> int:
        self.wait_calls += 1
        await self._exited.wait()
        return self.returncode or 0

    def terminate(self) -> None:
        self.terminated += 1
        self.exit(0)

    def kill(self) -> None:
        self.killed += 1
        self.exit(-9)

    def exit(self, returncode: int) -> None:
        self.returncode = returncode
        self._exited.set()
        self.stdout.close()
        self.stderr.close()


class FakeResponse:
    def __init__(self) -> None:
        self.prepared = False
        self.status: int | None = None
        self.headers: dict[str, str] = {}
        self.writes: list[bytes] = []
        self.eof_calls = 0

    def set_status(self, status: int) -> None:
        self.status = status

    async def prepare(self, _request) -> FakeResponse:
        self.prepared = True
        return self

    async def write(self, chunk: bytes) -> None:
        self.writes.append(chunk)

    async def write_eof(self) -> None:
        self.eof_calls += 1
