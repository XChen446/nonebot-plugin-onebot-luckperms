import pytest
from nonebot_plugin_onebot_luckperms.core.models import ContextSet, PermissionNode, User, Group, QueryOptions
from nonebot_plugin_onebot_luckperms.core.engine import PermissionEngine
from nonebot_plugin_onebot_luckperms.core.registry import NodeRegistry
from nonebot_plugin_onebot_luckperms.core.exceptions import CircularInheritanceError


class TestContextSet:
    def test_empty(self):
        ctx = ContextSet()
        assert ctx.is_empty()

    def test_not_empty(self):
        ctx = ContextSet({"group_id": "123"})
        assert not ctx.is_empty()

    def test_matches_exact(self):
        ctx = ContextSet({"group_id": "123", "role": "admin"})
        req = ContextSet({"group_id": "123"})
        assert ctx.matches(req)

    def test_matches_fail(self):
        ctx = ContextSet({"group_id": "123"})
        req = ContextSet({"group_id": "456"})
        assert not ctx.matches(req)

    def test_matches_empty_requirement(self):
        ctx = ContextSet({"group_id": "123"})
        req = ContextSet()
        assert ctx.matches(req)

    def test_with_context(self):
        ctx = ContextSet({"a": "1"})
        ctx2 = ctx.with_context("b", "2")
        assert ctx2.data == {"a": "1", "b": "2"}
        assert ctx.data == {"a": "1"}

    def test_from_to_dict(self):
        d = {"a": "1", "b": "2"}
        ctx = ContextSet.from_dict(d)
        assert ctx.to_dict() == d

    def test_matches_partial(self):
        self = ContextSet({"group_id": "123", "role": "admin"})
        req = ContextSet({"group_id": "123", "role": "admin"})
        assert self.matches(req)


class TestPermissionNode:
    def test_is_expired_false(self):
        node = PermissionNode(key="test", expiry=None)
        assert not node.is_expired()

    def test_applies_in_matching(self):
        node = PermissionNode(key="test", contexts=ContextSet({"group_id": "123"}))
        ctx = ContextSet({"group_id": "123", "role": "admin"})
        assert node.applies_in(ctx)

    def test_applies_in_not_matching(self):
        node = PermissionNode(key="test", contexts=ContextSet({"group_id": "123"}))
        ctx = ContextSet({"group_id": "456"})
        assert not node.applies_in(ctx)

    def test_applies_in_empty_contexts(self):
        node = PermissionNode(key="test")
        ctx = ContextSet({"group_id": "123"})
        assert node.applies_in(ctx)


class FakeStore:
    def __init__(self):
        self.groups = {}

    async def get_group(self, name):
        return self.groups.get(name)


class TestGroup:
    @pytest.mark.asyncio
    async def test_get_effective_nodes_self_only(self):
        store = FakeStore()
        g = Group(name="admin", nodes=[PermissionNode(key="a.b", value=True)])
        nodes = await g.get_effective_nodes(store)
        assert len(nodes) == 1

    @pytest.mark.asyncio
    async def test_get_effective_nodes_with_parent(self):
        store = FakeStore()
        parent = Group(name="mod", nodes=[PermissionNode(key="x.y", value=True)])
        store.groups["mod"] = parent
        g = Group(name="admin", parents=["mod"], nodes=[PermissionNode(key="a.b", value=True)])
        nodes = await g.get_effective_nodes(store)
        assert len(nodes) == 2

    @pytest.mark.asyncio
    async def test_circular_inheritance(self):
        store = FakeStore()
        g1 = Group(name="a", parents=["b"])
        g2 = Group(name="b", parents=["a"])
        store.groups["a"] = g1
        store.groups["b"] = g2
        with pytest.raises(CircularInheritanceError):
            await g1.get_effective_nodes(store)


class TestUser:
    @pytest.mark.asyncio
    async def test_has_permission_no_nodes(self):
        store = FakeStore()
        u = User(user_id="123")
        opts = QueryOptions(mode="all")
        result = await u.has_permission("any.node", store, opts)
        assert result is False

    @pytest.mark.asyncio
    async def test_has_permission_direct(self):
        store = FakeStore()
        u = User(user_id="123", nodes=[PermissionNode(key="a.b", value=True)])
        opts = QueryOptions(mode="all")
        result = await u.has_permission("a.b", store, opts)
        assert result is True

    @pytest.mark.asyncio
    async def test_has_permission_deny(self):
        store = FakeStore()
        u = User(user_id="123", nodes=[PermissionNode(key="a.b", value=False)])
        opts = QueryOptions(mode="all")
        result = await u.has_permission("a.b", store, opts)
        assert result is False

    @pytest.mark.asyncio
    async def test_group_inherited_permission(self):
        store = FakeStore()
        group = Group(name="admin", nodes=[PermissionNode(key="a.b", value=True)])
        store.groups["admin"] = group
        u = User(user_id="123", groups=["admin"])
        opts = QueryOptions(mode="all", flags={"include_inherited", "resolve_inheritance"})
        result = await u.has_permission("a.b", store, opts)
        assert result is True


class TestEngine:
    def test_default_deny(self):
        assert PermissionEngine.check({}, "any.node") is False

    def test_exact_allow(self):
        assert PermissionEngine.check({"a.b": True}, "a.b") is True

    def test_exact_deny(self):
        assert PermissionEngine.check({"a.b": False}, "a.b") is False

    def test_parent_deny_inheritance(self):
        assert PermissionEngine.check({"a.*": True, "a.b": False}, "a.b.c") is False

    def test_wildcard_allow_exact_deny_overrides(self):
        assert PermissionEngine.check({"a.*": True, "a.b": False}, "a.b") is False

    def test_wildcard_allow_child(self):
        assert PermissionEngine.check({"a.*": True}, "a.b.c") is True

    def test_prefix_inheritance(self):
        assert PermissionEngine.check({"a.b": True}, "a.b.c") is True

    def test_prefix_deny(self):
        assert PermissionEngine.check({"a.b": False}, "a.b.c") is False

    def test_wildcard_deny_overrides_allow(self):
        assert PermissionEngine.check({"*": True, "specific": False}, "specific") is False

    def test_multi_level_wildcard(self):
        assert PermissionEngine.check({"a.b.*": True}, "a.b.c") is True

    def test_deep_nested(self):
        assert PermissionEngine.check({"a.b.c": True}, "a.b.c.d") is True

    def test_no_match(self):
        assert PermissionEngine.check({"x.y": True}, "a.b") is False


class TestRegistry:
    def test_register_and_get(self):
        NodeRegistry._nodes.clear()
        NodeRegistry.register("test.node", "A test node")
        info = NodeRegistry.get("test.node")
        assert info is not None
        assert info["key"] == "test.node"
        assert info["description"] == "A test node"
        assert info["default"] is False

    def test_register_idempotent(self):
        NodeRegistry._nodes.clear()
        NodeRegistry.register("test.node")
        NodeRegistry.register("test.node")
        assert len(NodeRegistry.list_all()) == 1

    def test_list_all(self):
        NodeRegistry._nodes.clear()
        NodeRegistry.register("a")
        NodeRegistry.register("b")
        assert len(NodeRegistry.list_all()) == 2

    def test_get_ancestors(self):
        NodeRegistry._nodes.clear()
        ancestors = NodeRegistry.get_ancestors("myplugin.admin.ban")
        assert ancestors == ["myplugin.admin", "myplugin"]
