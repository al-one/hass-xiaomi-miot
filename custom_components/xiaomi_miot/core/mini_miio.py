# https://github.com/AlexxIT/XiaomiGateway3/blob/02aaddc3c16f63df116a95578f44d5b0da1c4f2c/custom_components/xiaomi_gateway3/core/mini_miio.py
import asyncio
import hashlib
import json
import logging
import random
import socket
import time
from asyncio import DatagramProtocol, Future
from asyncio.protocols import BaseProtocol
from asyncio.transports import DatagramTransport
from typing import Union

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__package__ + ".miio")

HELLO = bytes.fromhex(
    "21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
)


class BasemiIO:
    """A simple class that implements the miIO protocol."""

    device_id = None
    delta_ts = None
    debug = False

    def __init__(self, host: str, token: str, timeout: float = 3):
        self.addr = (host, 54321)
        self.token = bytes.fromhex(token)
        self.timeout = timeout

        key = hashlib.md5(self.token).digest()
        iv = hashlib.md5(key + self.token).digest()
        self.cipher = Cipher(
            algorithms.AES(key), modes.CBC(iv), backend=default_backend()
        )

    def _encrypt(self, plaintext: bytes):
        padder = padding.PKCS7(128).padder()
        padded_plaintext = padder.update(plaintext) + padder.finalize()

        encryptor = self.cipher.encryptor()
        return encryptor.update(padded_plaintext) + encryptor.finalize()

    def _decrypt(self, ciphertext: bytes):
        decryptor = self.cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(padded_plaintext) + unpadder.finalize()

    def _pack_raw(self, msg_id: int, method: str, params: Union[dict, list] = None):
        # latest zero unnecessary
        payload = (
            json.dumps(
                {"id": msg_id, "method": method, "params": params or []},
                separators=(",", ":"),
            ).encode()
            + b"\x00"
        )

        data = self._encrypt(payload)

        raw = b"\x21\x31"
        raw += (32 + len(data)).to_bytes(2, "big")  # total length
        raw += b"\x00\x00\x00\x00"  # unknow
        raw += self.device_id.to_bytes(4, "big")
        raw += int(time.time() - self.delta_ts).to_bytes(4, "big")

        raw += hashlib.md5(raw + self.token + data).digest()
        raw += data

        assert len(raw) < 1024, "Exceeded message size"

        return raw

    def _unpack_raw(self, raw: bytes):
        assert raw[:2] == b"\x21\x31"
        # length = int.from_bytes(raw[2:4], 'big')
        # unknown = raw[4:8]
        # device_id = int.from_bytes(raw[8:12], 'big')
        # ts = int.from_bytes(raw[12:16], 'big')
        # checksum = raw[16:32]
        return self._decrypt(raw[32:])


class SyncMiIO(BasemiIO):
    """Synchronous miIO protocol."""

    def ping(self, sock: socket) -> bool:
        """Returns `true` if the connection to the miio device is working. The
        token is not verified at this stage.
        """
        try:
            sock.sendto(HELLO, self.addr)
            raw = sock.recv(1024)
            if raw[:2] == b"\x21\x31":
                self.device_id = int.from_bytes(raw[8:12], "big")
                self.delta_ts = time.time() - int.from_bytes(raw[12:16], "big")
                return True
        except Exception:
            pass
        return False

    def send(self, method: str, params: Union[dict, list] = None):
        """Send command to miIO device and get result from it. Params can be
        dict or list depend on command.
        """
        pings = 0
        for times in range(1, 4):
            try:
                # create socket every time for reset connection, because we can
                # reseive answer on previous request or request from another
                # thread
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(self.timeout)

                # need device_id for send command, can get it from ping cmd
                if self.delta_ts is None and not self.ping(sock):
                    pings += 1
                    continue

                # pack each time for new message id
                msg_id = random.randint(100000000, 999999999)
                raw_send = self._pack_raw(msg_id, method, params)
                t = time.monotonic()
                sock.sendto(raw_send, self.addr)
                # can receive more than 1024 bytes (1056 approximate maximum)
                raw_recv = sock.recv(10240)
                t = time.monotonic() - t
                data = self._unpack_raw(raw_recv).rstrip(b"\x00")

                if data == b"":
                    # mgl03 fw 1.4.6_0012 without Internet respond on miIO.info
                    # command with empty answer
                    data = {"result": ""}
                    break

                data = json.loads(data)
                # check if we received response for our cmd
                if data["id"] == msg_id:
                    break

                _LOGGER.debug(f"{self.addr[0]} | wrong ID")

            except socket.timeout:
                _LOGGER.debug(f"{self.addr[0]} | timeout {times}")
            except Exception as e:
                _LOGGER.debug(f"{self.addr[0]}", exc_info=e)

            # init ping again
            self.delta_ts = None

        else:
            _LOGGER.debug(
                f"{self.addr[0]} | Device offline"
                if pings >= 2
                else f"{self.addr[0]} | Can't send {method} {params}"
            )
            return None

        if self.debug:
            _LOGGER.debug(
                f"{self.addr[0]} | Send {method} {len(raw_send)}B, "
                f"recv {len(raw_recv)}B in {t:.1f} sec and {times} try"
            )

        if "result" in data:
            return data["result"]
        else:
            _LOGGER.debug(f"{self.addr[0]} | {data}")
            return None

    def send_bulk(self, method: str, params: list):
        """Sends a command with a large number of parameters. Splits into
        multiple requests when the size of one request is exceeded.
        """
        try:
            result = []
            # Chunk of 15 is seems like the best size. Because request should
            # be lower than 1024 and response should be not more than 1056.
            # {'did':'1234567890','siid': 2,'piid': 1,'value': False,'code': 0}
            for i in range(0, len(params), 15):
                result += self.send(method, params[i : i + 15])
            return result
        except Exception:
            return None

    def info(self) -> Union[dict, str, None]:
        """Get info about miIO device.

        Response dict - device ok, token ok
        Response empty string - device ok, token ok (mgl03 on fw 1.4.6_0012
            without cloud connection)
        Response None, device_id not None - device ok, token wrong
        Response None, device_id None - device offline
        """
        return self.send("miIO.info")


# noinspection PyUnusedLocal
class AsyncSocket(DatagramProtocol):
    timeout = 0
    transport: DatagramTransport = None
    response: Future = None

    def __init__(self):
        self.response = asyncio.get_event_loop().create_future()

    def connection_made(self, transport: DatagramTransport):
        # _LOGGER.debug(f"connection_made {transport}")
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        # _LOGGER.debug(f"datagram_received {data}")
        self.response.set_result(data)

    def settimeout(self, value: int):
        self.timeout = value

    def sendto(self, data: bytes):
        self.transport.sendto(data)

    def close(self):
        if not self.transport:
            return
        try:
            self.transport.close()
        except Exception as e:
            _LOGGER.error("Error when closing async socket", exc_info=e)

    async def connect(self, addr: tuple[str, int]):
        coro = asyncio.get_event_loop().create_datagram_endpoint(
            lambda: self, remote_addr=addr
        )
        if self.timeout:
            await asyncio.wait_for(coro, self.timeout)
        else:
            await coro

    async def recv(self, *args):
        self.response = asyncio.get_event_loop().create_future()
        if self.timeout:
            return await asyncio.wait_for(self.response, self.timeout)
        return await self.response


# noinspection PyMethodMayBeStatic,PyTypeChecker
class AsyncMiIO(BasemiIO, BaseProtocol):
    async def ping(self, sock: AsyncSocket) -> bool:
        """Returns `true` if the connection to the miio device is working. The
        token is not verified at this stage.
        """
        try:
            sock.sendto(HELLO)
            raw = await sock.recv(1024)
            if raw[:2] == b"\x21\x31":
                self.device_id = int.from_bytes(raw[8:12], "big")
                self.delta_ts = time.time() - int.from_bytes(raw[12:16], "big")
                return True
        except Exception:
            pass
        return False

    async def send(self, method: str, params: Union[dict, list] = None, tries=3):
        """Send command to miIO device and get result from it. Params can be
        dict or list depend on command.

        Possible results:
        - None - device offline
        - {} (empty dict) - device online but can't response on cmd
        - {'id':123,'result':...} - device answered on cmd with good result
        - {'id':123,'error':...}
        """
        offline = False
        for _ in range(0, tries):
            sock = AsyncSocket()
            sock.settimeout(self.timeout)
            try:
                # create socket every time for reset connection, because we can
                # reseive answer on previous request or request from another
                # thread
                await sock.connect(self.addr)

                # need device_id for send command, can get it from ping cmd
                if self.delta_ts is None and not await self.ping(sock):
                    # device doesn't answered on ping
                    offline = True
                    continue

                # pack each time for new message id
                msg_id = random.randint(100000000, 999999999)
                raw_send = self._pack_raw(msg_id, method, params)
                sock.sendto(raw_send)
                # can receive more than 1024 bytes (1056 approximate maximum)
                raw_recv = await sock.recv(10240)
                data = self._unpack_raw(raw_recv).rstrip(b"\x00")

                if data == b"":
                    # mgl03 fw 1.4.6_0012 without Internet respond on miIO.info
                    # command with empty answer
                    continue

                data = json.loads(data)
                # check if we received response for our cmd
                if data["id"] != msg_id:
                    _LOGGER.debug(f"{self.addr[0]} | wrong answer ID")
                    continue

                return data

            except (asyncio.TimeoutError, OSError):
                # OSError: [Errno 101] Network unreachable
                pass
            except Exception as e:
                _LOGGER.debug(f"{self.addr[0]} | {method}", exc_info=e)
            finally:
                sock.close()

            # init ping again
            self.delta_ts = None

        if offline:
            _LOGGER.debug(f"{self.addr[0]} | Device offline")
            return None

        _LOGGER.debug(f"{self.addr[0]} | No answer on {method} {params}")
        return {}

    async def send_bulk(self, method: str, params: list, chunk: int = 0) -> list:
        """Sends a command with a large number of parameters. Splits into
        multiple requests when the size of one request is exceeded.
        """
        if not chunk:
            chunk = 15
        try:
            result = []
            for i in range(0, len(params), chunk):
                resp = await self.send(method, params[i : i + chunk])
                result += resp["result"]
            return result
        except Exception:
            return None

    async def info(self, tries: int = 3) -> dict | None:
        """Get info about miIO device."""
        resp = await self.send("miIO.info", tries=tries)
        return resp.get("result") if resp else resp
