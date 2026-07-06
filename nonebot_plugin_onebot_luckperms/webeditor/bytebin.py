from __future__ import annotations

import gzip
import json
import logging
from typing import Any

import aiohttp

log = logging.getLogger("oblp.webeditor")

DEFAULT_BYTEBIN_URL = "https://usercontent.luckperms.net"


class BytebinClient:
    def __init__(self, base_url: str = DEFAULT_BYTEBIN_URL):
        self.base_url = base_url.rstrip("/")

    async def upload(self, payload: dict[str, Any]) -> str:
        json_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        compressed = gzip.compress(json_bytes)

        headers = {
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
            "User-Agent": "LuckPerms/5.4.0/editor",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/post",
                data=compressed,
                headers=headers,
            ) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    raise RuntimeError(
                        f"Bytebin upload failed: HTTP {resp.status} - {text}"
                    )

                key: str | None = None
                location = resp.headers.get("Location")
                if location:
                    key = location.rstrip("/").split("/")[-1]

                if not key:
                    result = await resp.json()
                    key = result.get("key") or result.get("code") or result.get("id")

                if not key:
                    raise RuntimeError(f"Bytebin invalid response: {await resp.text()}")
                log.info("Bytebin upload OK, key=%s", key)
                return key

    async def download(self, code: str) -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/{code}",
                headers={"User-Agent": "LuckPerms/5.4.0/editor"},
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(
                        f"Bytebin download failed: HTTP {resp.status} - {text}"
                    )
                raw = await resp.read()
                try:
                    decompressed = gzip.decompress(raw)
                except Exception:
                    decompressed = raw
                return json.loads(decompressed.decode("utf-8"))
