from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional

import aiohttp

log = logging.getLogger("oblp.webeditor")

DEFAULT_BYTESOCKS_URL = "https://usersockets.luckperms.net"


class BytesocksClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BYTESOCKS_URL,
        on_hello: Optional[Callable[[str], None]] = None,
        on_connected: Optional[Callable[[], None]] = None,
        on_change_request: Optional[Callable[[str], None]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.on_hello = on_hello
        self.on_connected = on_connected
        self.on_change_request = on_change_request
        self.channel: Optional[str] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def create_channel(self) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/create",
                headers={"User-Agent": "LuckPerms/5.4.0"},
                allow_redirects=False,
            ) as resp:
                if resp.status != 201:
                    text = await resp.text()
                    raise RuntimeError(
                        f"Bytesocks create channel failed: HTTP {resp.status} - {text}"
                    )

                key: str | None = None
                location = resp.headers.get("Location")
                if location:
                    key = location.rstrip("/").split("/")[-1]

                if not key:
                    try:
                        result = await resp.json()
                        key = result.get("key")
                    except Exception:
                        pass

                if not key:
                    raise RuntimeError(f"Bytesocks invalid response: {await resp.text()}")

                self.channel = key
                log.info("Bytesocks channel created: %s", key)
                return key

    async def start(self) -> None:
        if self._running:
            return
        if not self.channel:
            raise RuntimeError("Must call create_channel() first")
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._session:
            await self._session.close()
            self._session = None

    async def _run(self) -> None:
        if self.base_url.startswith("https://"):
            ws_url = "wss://" + self.base_url[8:]
        elif self.base_url.startswith("http://"):
            ws_url = "ws://" + self.base_url[7:]
        else:
            ws_url = self.base_url

        url = f"{ws_url}/{self.channel}"
        self._session = aiohttp.ClientSession()

        try:
            async with self._session.ws_connect(url) as ws:
                self._ws = ws
                log.info("Bytesocks connected: %s", url)

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(msg.data)
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("Bytesocks connection error: %s", e)
        finally:
            self._running = False
            log.info("Bytesocks disconnected")

    async def _handle_message(self, data: str) -> None:
        try:
            frame = json.loads(data)
        except json.JSONDecodeError:
            log.warning("Invalid JSON: %s", data[:200])
            return

        inner_msg = frame.get("msg", "")
        if not inner_msg:
            return

        try:
            msg = json.loads(inner_msg)
        except json.JSONDecodeError:
            log.warning("Invalid inner message: %s", inner_msg[:200])
            return

        msg_type = msg.get("type", "").lower()

        if msg_type == "hello":
            nonce = msg.get("nonce", "")
            await self._send({"type": "hello-reply", "nonce": nonce, "state": "trusted"})
            if self.on_hello:
                try:
                    await self.on_hello(nonce)
                except Exception:
                    log.exception("on_hello callback error")

        elif msg_type == "connected":
            if self.on_connected:
                try:
                    await self.on_connected()
                except Exception:
                    log.exception("on_connected callback error")

        elif msg_type == "change-request":
            code = msg.get("code", "")
            if self.on_change_request:
                try:
                    await self.on_change_request(code)
                except Exception:
                    log.exception("on_change_request callback error")

        elif msg_type == "ping":
            await self._send({"type": "pong"})

    async def _send(self, data: dict) -> None:
        if self._ws is None or self._ws.closed:
            return
        inner = json.dumps(data)
        frame = {"msg": inner, "signature": ""}
        await self._ws.send_str(json.dumps(frame))

    async def send_change_response(self, state: str, new_session_code: Optional[str] = None) -> None:
        payload: dict = {"type": "change-response", "state": state}
        if new_session_code:
            payload["newSessionCode"] = new_session_code
        await self._send(payload)

    @property
    def is_active(self) -> bool:
        return self._running and self._ws is not None and not self._ws.closed
