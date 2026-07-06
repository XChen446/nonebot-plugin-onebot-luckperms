from __future__ import annotations

import logging
from typing import Callable, Optional

from .bytebin import BytebinClient
from .websocket import BytesocksClient

log = logging.getLogger("oblp.webeditor")

EDITOR_BASE_URL = "https://luckperms.net/editor"
DEFAULT_BYTESOCKS_URL = "https://usersockets.luckperms.net"


class WebEditorSession:
    def __init__(
        self,
        get_payload: Callable[[], dict],
        apply_changes: Callable[[dict], None],
        bytebin_url: Optional[str] = None,
        bytesocks_url: Optional[str] = None,
    ):
        self.get_payload = get_payload
        self.apply_changes = apply_changes
        self.bytebin = BytebinClient(bytebin_url) if bytebin_url else BytebinClient()
        self.bytesocks_url = bytesocks_url
        self._socks: Optional[BytesocksClient] = None
        self._code: Optional[str] = None
        self._channel: Optional[str] = None
        self._closed = True

    async def open(self) -> str:
        if self._socks is not None:
            await self.close()

        socks = BytesocksClient(
            base_url=self.bytesocks_url or DEFAULT_BYTESOCKS_URL,
            on_hello=self._on_hello,
            on_connected=self._on_connected,
            on_change_request=self._on_change_request,
        )
        self._socks = socks
        self._channel = await socks.create_channel()
        await socks.start()

        payload = self.get_payload()
        payload["socket"] = {
            "protocolVersion": 1,
            "channelId": self._channel,
            "publicKey": "",
        }

        self._code = await self.bytebin.upload(payload)

        self._closed = False
        url = f"{EDITOR_BASE_URL}/{self._code}"
        log.info("Web Editor session opened: %s (channel=%s)", url, self._channel)
        return url

    async def close(self) -> None:
        self._closed = True
        self._code = None
        self._channel = None
        if self._socks:
            await self._socks.stop()
            self._socks = None
        log.info("Web Editor session closed")

    async def apply_edits(self, code: str) -> None:
        log.info("Downloading and applying edits: %s", code)
        payload = await self.bytebin.download(code)
        self.apply_changes(payload)
        log.info("Edits applied")

    @staticmethod
    async def _on_hello(nonce: str) -> None:
        log.debug("Web Editor handshake: nonce=%s", nonce)

    @staticmethod
    async def _on_connected() -> None:
        log.info("Web Editor frontend connected")

    async def _on_change_request(self, code: str) -> None:
        if self._closed or self._socks is None:
            return
        log.info("Received change-request: code=%s", code)

        try:
            await self._socks.send_change_response("accepted")

            await self.apply_edits(code)

            new_payload = self.get_payload()
            new_payload["socket"] = {
                "protocolVersion": 1,
                "channelId": self._channel,
                "publicKey": "",
            }
            new_code = await self.bytebin.upload(new_payload)

            await self._socks.send_change_response("applied", new_code)
            self._code = new_code
            log.info("Pushed new session code: %s", new_code)
        except Exception:
            log.exception("Failed to process change-request")

    @property
    def is_active(self) -> bool:
        return not self._closed and self._socks is not None and self._socks.is_active
