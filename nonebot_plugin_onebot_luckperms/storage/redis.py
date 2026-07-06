import json
import logging
import time
from typing import Optional, List

import redis.asyncio as aioredis

from ..core.models import User, Group, PermissionNode, ContextSet

logger = logging.getLogger("oblp")


class RedisStore:
    def __init__(self, url: str = "redis://localhost:6379/0"):
        self.url = url
        self._redis: Optional[aioredis.Redis] = None
        self._prefix = "oblp"

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self.url, decode_responses=True)
        return self._redis

    async def _set_ttl(self, key: str, node: PermissionNode):
        if node.expiry is not None:
            ttl = int(node.expiry - time.time())
            if ttl > 0:
                r = await self._get_redis()
                await r.expire(key, ttl)

    async def get_user(self, user_id: str) -> Optional[User]:
        r = await self._get_redis()
        data = await r.hgetall(f"{self._prefix}:user:{user_id}")
        if not data:
            return None
        return User(
            user_id=data.get("user_id", user_id),
            username=data.get("username"),
            primary_group=data.get("primary_group"),
            groups=json.loads(data.get("groups", "[]")),
            nodes=[self._node_from_dict(n) for n in json.loads(data.get("nodes", "[]"))],
        )

    async def save_user(self, user: User) -> None:
        r = await self._get_redis()
        key = f"{self._prefix}:user:{user.user_id}"
        await r.hset(
            key,
            mapping={
                "user_id": user.user_id,
                "username": user.username or "",
                "primary_group": user.primary_group or "",
                "groups": json.dumps(user.groups),
                "nodes": json.dumps([self._node_to_dict(n) for n in user.nodes]),
            },
        )
        max_expiry = min((n.expiry for n in user.nodes if n.expiry), default=None)
        if max_expiry:
            await r.expire(key, int(max_expiry - time.time()))

    async def delete_user(self, user_id: str) -> None:
        r = await self._get_redis()
        await r.delete(f"{self._prefix}:user:{user_id}")

    async def list_users(self) -> List[str]:
        r = await self._get_redis()
        cursor = "0"
        keys = []
        while cursor != 0:
            cursor, batch = await r.scan(cursor=cursor, match=f"{self._prefix}:user:*")
            keys.extend([k.split(":", 2)[2] for k in batch])
            cursor = int(cursor)
        return keys

    async def get_group(self, name: str) -> Optional[Group]:
        r = await self._get_redis()
        data = await r.hgetall(f"{self._prefix}:group:{name}")
        if not data:
            return None
        return Group(
            name=name,
            display_name=data.get("display_name"),
            weight=int(data.get("weight", 0)),
            parents=json.loads(data.get("parents", "[]")),
            nodes=[self._node_from_dict(n) for n in json.loads(data.get("nodes", "[]"))],
        )

    async def save_group(self, group: Group) -> None:
        r = await self._get_redis()
        key = f"{self._prefix}:group:{group.name}"
        await r.hset(
            key,
            mapping={
                "display_name": group.display_name or "",
                "weight": str(group.weight),
                "parents": json.dumps(group.parents),
                "nodes": json.dumps([self._node_to_dict(n) for n in group.nodes]),
            },
        )
        max_expiry = min((n.expiry for n in group.nodes if n.expiry), default=None)
        if max_expiry:
            await r.expire(key, int(max_expiry - time.time()))

    async def delete_group(self, name: str) -> None:
        r = await self._get_redis()
        await r.delete(f"{self._prefix}:group:{name}")

    async def list_groups(self) -> List[str]:
        r = await self._get_redis()
        cursor = "0"
        keys = []
        while cursor != 0:
            cursor, batch = await r.scan(cursor=cursor, match=f"{self._prefix}:group:*")
            keys.extend([k.split(":", 2)[2] for k in batch])
            cursor = int(cursor)
        return keys

    async def get_registered_nodes(self) -> List[PermissionNode]:
        r = await self._get_redis()
        raw = await r.get(f"{self._prefix}:registry")
        if not raw:
            return []
        return [self._node_from_dict(n) for n in json.loads(raw)]

    async def save_registered_node(self, node: PermissionNode) -> None:
        existing = await self.get_registered_nodes()
        existing_dict = {n.key: n for n in existing}
        existing_dict[node.key] = node
        r = await self._get_redis()
        await r.set(
            f"{self._prefix}:registry",
            json.dumps([self._node_to_dict(n) for n in existing_dict.values()]),
        )

    async def load_all(self) -> None:
        pass

    async def save_all(self) -> None:
        pass

    async def close(self):
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    @staticmethod
    def _node_to_dict(node: PermissionNode) -> dict:
        return {
            "key": node.key,
            "value": node.value,
            "expiry": node.expiry,
            "contexts": node.contexts.to_dict(),
        }

    @staticmethod
    def _node_from_dict(d: dict) -> PermissionNode:
        return PermissionNode(
            key=d["key"],
            value=d.get("value", True),
            expiry=d.get("expiry"),
            contexts=ContextSet.from_dict(d.get("contexts", {})),
        )
