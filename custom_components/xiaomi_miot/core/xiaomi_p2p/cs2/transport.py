"""CS2 transport protocols.

`Cs2Transport` describes the post-discovery transport interface used
by the MISS session and media layers. `Cs2Connector` describes the
one-shot discovery + handoff that produces an established transport.
Concrete UDP/TCP transports live in `udp.py` and `tcp.py` and are
returned by the connector after a single successful discovery exchange.
"""

from __future__ import annotations

from typing import Literal, Protocol

from .protocol import Cs2Command, Cs2MediaPacket


TransportModeStr = Literal["udp", "tcp"]


class Cs2Transport(Protocol):
    """Established CS2 transport surface used by the MISS session."""

    negotiated_mode: TransportModeStr

    async def read_command(
        self, timeout: float | None = None
    ) -> Cs2Command: ...

    async def write_command(self, command: Cs2Command) -> None: ...

    async def read_media_packet(
        self,
        timeout: float | None = None,
    ) -> Cs2MediaPacket: ...

    async def write_media_packet(self, packet: Cs2MediaPacket) -> None: ...

    async def close(self) -> None: ...


class Cs2Connector(Protocol):
    """Performs a single CS2 discovery exchange and returns an established transport."""

    async def connect(
        self,
        bootstrap: object,
        policy: str,
        deadline: float,
    ) -> Cs2Transport: ...


__all__ = ["Cs2Connector", "Cs2Transport", "TransportModeStr"]