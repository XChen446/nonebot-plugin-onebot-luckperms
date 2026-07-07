from typing import Optional

from .protocol import PermissionStore
from .memory import MemoryStore
from .sqlite import SQLiteStore

_store: Optional[PermissionStore] = None


def _get_redis_store(**kwargs):
    from .redis import RedisStore
    return RedisStore(url=kwargs.get("redis_url", "redis://localhost:6379/0"))


def init_store(store_type: str, **kwargs) -> PermissionStore:
    global _store
    if store_type == "memory":
        _store = MemoryStore()
    elif store_type == "sqlite":
        _store = SQLiteStore(db_path=kwargs.get("db_path", "./data/oblp/permissions.db"))
    elif store_type == "redis":
        _store = _get_redis_store(**kwargs)
    else:
        raise ValueError(f"Unknown store type: {store_type}")
    return _store


def get_store() -> Optional[PermissionStore]:
    return _store
