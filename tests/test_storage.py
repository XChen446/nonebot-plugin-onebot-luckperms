import pytest
import tempfile
import os

from nonebot_plugin_onebot_luckperms.core.models import User, Group, PermissionNode
from nonebot_plugin_onebot_luckperms.storage.memory import MemoryStore
from nonebot_plugin_onebot_luckperms.storage.sqlite import SQLiteStore


class TestMemoryStore:
    @pytest.mark.asyncio
    async def test_user_crud(self):
        store = MemoryStore()
        user = User(user_id="123", username="test", primary_group="default", groups=["default"])
        await store.save_user(user)
        loaded = await store.get_user("123")
        assert loaded is not None
        assert loaded.user_id == "123"
        assert loaded.username == "test"

        await store.delete_user("123")
        assert await store.get_user("123") is None

    @pytest.mark.asyncio
    async def test_group_crud(self):
        store = MemoryStore()
        group = Group(name="admin", weight=10, parents=["mod"])
        await store.save_group(group)
        loaded = await store.get_group("admin")
        assert loaded is not None
        assert loaded.name == "admin"
        assert loaded.weight == 10

        groups = await store.list_groups()
        assert "admin" in groups

        await store.delete_group("admin")
        assert await store.get_group("admin") is None


class TestSQLiteStore:
    @pytest.mark.asyncio
    async def test_user_crud(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = SQLiteStore(db_path=db_path)
            user = User(user_id="123", username="test", groups=["default"])
            await store.save_user(user)
            loaded = await store.get_user("123")
            assert loaded is not None
            assert loaded.user_id == "123"
            assert loaded.groups == ["default"]

            await store.delete_user("123")
            assert await store.get_user("123") is None
            await store.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_group_crud(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = SQLiteStore(db_path=db_path)
            group = Group(name="admin", weight=20, parents=["mod"])
            await store.save_group(group)
            loaded = await store.get_group("admin")
            assert loaded is not None
            assert loaded.weight == 20
            assert loaded.parents == ["mod"]

            groups = await store.list_groups()
            assert "admin" in groups

            await store.delete_group("admin")
            assert await store.get_group("admin") is None
            await store.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_node_persistence(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = SQLiteStore(db_path=db_path)
            node = PermissionNode(key="test.permission", value=True)
            await store.save_registered_node(node)
            nodes = await store.get_registered_nodes()
            assert len(nodes) == 1
            assert nodes[0].key == "test.permission"
            await store.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
