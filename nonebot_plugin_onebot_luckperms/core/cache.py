from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

from ..config import oblp_config


class PermissionCache:
    _cache: Dict[str, Tuple[float, dict]] = {}

    @classmethod
    def get(cls, key: str) -> Optional[dict]:
        ttl = oblp_config.cache_ttl
        if ttl <= 0:
            return None
        entry = cls._cache.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > ttl:
            del cls._cache[key]
            return None
        return value

    @classmethod
    def set(cls, key: str, value: dict):
        ttl = oblp_config.cache_ttl
        if ttl <= 0:
            return
        cls._cache[key] = (time.time(), value)

    @classmethod
    def invalidate(cls, key: str):
        cls._cache.pop(key, None)

    @classmethod
    def invalidate_all(cls):
        cls._cache.clear()

    @classmethod
    def make_key(cls, user_id: str, ctx: "ContextSet") -> str:
        ctx_str = "&".join(f"{k}={v}" for k, v in sorted(ctx.data.items()))
        return f"{user_id}:{ctx_str}"
