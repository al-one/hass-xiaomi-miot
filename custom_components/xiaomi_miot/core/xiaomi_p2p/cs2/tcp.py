"""Established CS2 TCP transport (stub for Task 6).

`TcpCs2Transport` is the TCP counterpart of `UdpCs2Transport`. This
file ships a minimum stub that lets `DefaultCs2Connector` resolve the
lazy import when the peer signals TCP-ready; Task 6 will replace the
stub body with the full TCP state machine.
"""

from __future__ import annotations

from typing import Optional

from .. import MissError, MissErrorCategory
from .protocol import Cs2Command, Cs2MediaPacket


class TcpCs2Transport:
    """Stub TCP transport. Task 6 fills in the state machine."""

    negotiated_mode = "tcp"

    def __init__(self, *, reader, writer) -> None:
        self._reader = reader
        self._writer = writer
        self._closed = False

    async def read_command(self, timeout: float | None = None) -> Cs2Command:
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        raise NotImplementedError("TcpCs2Transport.read_command is added in Task 6")

    async def write_command(self, command: Cs2Command) -> None:
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        raise NotImplementedError("TcpCs2Transport.write_command is added in Task 6")

    async def read_media_packet(
        self, timeout: float | None = None
    ) -> Cs2MediaPacket:
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        raise NotImplementedError("TcpCs2Transport.read_media_packet is added in Task 6")

    async def write_media_packet(self, packet: Cs2MediaPacket) -> None:
        if self._closed:
            raise MissError(MissErrorCategory.TRANSPORT, "transport_closed")
        raise NotImplementedError("TcpCs2Transport.write_media_packet is added in Task 6")

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        writer = self._writer
        if writer is not None:
            try:
                close = getattr(writer, "close", None)
                if close is not None:
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
            except Exception:  # pragma: no cover - defensive
                pass


__all__ = ["TcpCs2Transport"]
