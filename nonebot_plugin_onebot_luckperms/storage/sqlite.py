import json
import logging
from pathlib import Path
from typing import Optional, List, Dict

import aiosqlite

from ..core.models import User, Group, PermissionNode, ContextSet

logger = logging.getLogger("oblp")


class SQLiteStore:
    def __init__(self, db_path: str = "./data/oblp/permissions.db"):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def _ensure_dir(self):
        p = Path(self.db_path)
        p.parent.mkdir(parents=True, exist_ok=True)

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            await self._ensure_dir()
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def _init_tables(self):
        conn = await self._get_conn()
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                primary_group TEXT,
                groups_json TEXT NOT NULL DEFAULT '[]',
                nodes_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS groups (
                name TEXT PRIMARY KEY,
                display_name TEXT,
                weight INTEGER NOT NULL DEFAULT 0,
                parents_json TEXT NOT NULL DEFAULT '[]',
                nodes_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        await conn.commit()

    async def get_user(self, user_id: str) -> Optional[User]:
        await self._init_tables()
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return User(
            user_id=row["user_id"],
            username=row["username"],
            primary_group=row["primary_group"],
            groups=json.loads(row["groups_json"]),
            nodes=[self._node_from_dict(n) for n in json.loads(row["nodes_json"])],
        )

    async def save_user(self, user: User) -> None:
        await self._init_tables()
        conn = await self._get_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO users (user_id, username, primary_group, groups_json, nodes_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                user.user_id,
                user.username,
                user.primary_group,
                json.dumps(user.groups),
                json.dumps([self._node_to_dict(n) for n in user.nodes]),
            ),
        )
        await conn.commit()

    async def delete_user(self, user_id: str) -> None:
        await self._init_tables()
        conn = await self._get_conn()
        await conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await conn.commit()

    async def list_users(self) -> List[str]:
        await self._init_tables()
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT user_id FROM users")
        rows = await cursor.fetchall()
        return [row["user_id"] for row in rows]

    async def get_group(self, name: str) -> Optional[Group]:
        await self._init_tables()
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT * FROM groups WHERE name = ?", (name,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return Group(
            name=row["name"],
            display_name=row["display_name"],
            weight=row["weight"],
            parents=json.loads(row["parents_json"]),
            nodes=[self._node_from_dict(n) for n in json.loads(row["nodes_json"])],
        )

    async def save_group(self, group: Group) -> None:
        await self._init_tables()
        conn = await self._get_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO groups (name, display_name, weight, parents_json, nodes_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                group.name,
                group.display_name,
                group.weight,
                json.dumps(group.parents),
                json.dumps([self._node_to_dict(n) for n in group.nodes]),
            ),
        )
        await conn.commit()

    async def delete_group(self, name: str) -> None:
        await self._init_tables()
        conn = await self._get_conn()
        await conn.execute("DELETE FROM groups WHERE name = ?", (name,))
        await conn.commit()

    async def list_groups(self) -> List[str]:
        await self._init_tables()
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT name FROM groups")
        rows = await cursor.fetchall()
        return [row["name"] for row in rows]

    async def get_registered_nodes(self) -> List[PermissionNode]:
        await self._init_tables()
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT value FROM meta WHERE key = 'registered_nodes'")
        row = await cursor.fetchone()
        if row is None:
            return []
        return [self._node_from_dict(n) for n in json.loads(row["value"])]

    async def save_registered_node(self, node: PermissionNode) -> None:
        await self._init_tables()
        existing = await self.get_registered_nodes()
        existing_dict = {n.key: n for n in existing}
        existing_dict[node.key] = node
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('registered_nodes', ?)",
            (json.dumps([self._node_to_dict(n) for n in existing_dict.values()]),),
        )
        await conn.commit()

    async def load_all(self) -> None:
        await self._init_tables()

    async def save_all(self) -> None:
        await self._init_tables()

    async def close(self):
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

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
