"""Tests for ContextProvider system and NodeRegistry default integration."""
import pytest
from nonebot_plugin_onebot_luckperms.core.models import ContextSet, User, QueryOptions, PermissionNode
from nonebot_plugin_onebot_luckperms.core.engine import PermissionEngine
from nonebot_plugin_onebot_luckperms.core.registry import NodeRegistry, register_node
from nonebot_plugin_onebot_luckperms.core.context_provider import (
    register_context_provider,
    DuplicateProviderError,
    _context_providers,
    get_context_providers,
    clear_providers,
)


class TestRegistryDefaults:
    def setup_method(self):
        NodeRegistry._nodes.clear()

    def test_default_without_context(self):
        NodeRegistry._nodes.clear()
        NodeRegistry._nodes["myplugin.ban"] = {"key": "myplugin.ban", "description": "", "default": False, "contexts": ContextSet()}
        default = NodeRegistry.get_default("myplugin.ban")
        assert default is False

    def test_default_grant_for_owner(self):
        NodeRegistry._nodes.clear()
        NodeRegistry._nodes["myplugin.admincmd"] = {
            "key": "myplugin.admincmd",
            "description": "",
            "default": True,
            "contexts": ContextSet({"role": "owner"}),
        }
        default = NodeRegistry.get_default("myplugin.admincmd")
        assert default is True

    def test_default_not_applied_wrong_context(self):
        NodeRegistry._nodes.clear()
        register_node("myplugin.ban", default=True, contexts=ContextSet({"role": "owner"}))

        ctx_owner = ContextSet({"role": "owner"})
        ctx_member = ContextSet({"role": "member"})

        assert ctx_owner.matches(NodeRegistry._nodes["myplugin.ban"]["contexts"]) is True
        assert ctx_member.matches(NodeRegistry._nodes["myplugin.ban"]["contexts"]) is False


class FakeStoreWithDefaults:
    def __init__(self):
        self.groups = {}
    async def get_group(self, name):
        return self.groups.get(name)


class TestEngineRegistryDefaultIntegration:
    @pytest.mark.asyncio
    async def test_registry_default_applied_in_resolve(self):
        NodeRegistry._nodes.clear()
        NodeRegistry._nodes["myplugin.ban"] = {"key": "myplugin.ban", "description": "", "default": True, "contexts": ContextSet()}
        store = FakeStoreWithDefaults()
        user = User(user_id="123")
        opts = QueryOptions(mode="contextual", contexts=ContextSet(), flags={"include_inherited", "resolve_inheritance"})
        resolved = await user.get_effective_nodes(store, opts, ContextSet({"role": "owner"}))
        assert resolved.get("myplugin.ban") is True

    @pytest.mark.asyncio
    async def test_registry_default_blocked_by_explicit_deny(self):
        NodeRegistry._nodes.clear()
        NodeRegistry._nodes["myplugin.ban"] = {"key": "myplugin.ban", "description": "", "default": True, "contexts": ContextSet()}
        store = FakeStoreWithDefaults()
        user = User(user_id="123", nodes=[PermissionNode(key="myplugin.ban", value=False)])
        opts = QueryOptions(mode="contextual", contexts=ContextSet(), flags={"include_inherited", "resolve_inheritance"})
        resolved = await user.get_effective_nodes(store, opts, ContextSet({"role": "owner"}))
        assert resolved.get("myplugin.ban") is False

    @pytest.mark.asyncio
    async def test_registry_default_context_restricted(self):
        NodeRegistry._nodes.clear()
        NodeRegistry._nodes["myplugin.ban"] = {"key": "myplugin.ban", "description": "", "default": True, "contexts": ContextSet({"role": "owner"})}
        store = FakeStoreWithDefaults()
        user = User(user_id="123")
        opts = QueryOptions(mode="contextual", contexts=ContextSet(), flags={"include_inherited", "resolve_inheritance"})

        resolved_member = await user.get_effective_nodes(store, opts, ContextSet({"role": "member"}))
        assert "myplugin.ban" not in resolved_member

        resolved_owner = await user.get_effective_nodes(store, opts, ContextSet({"role": "owner"}))
        assert resolved_owner.get("myplugin.ban") is True


class TestContextSpecificOverride:
    """越精确越优先：同 key 不同 context 时，匹配更多上下文的节点获胜。"""

    @pytest.mark.asyncio
    async def test_context_specific_overrides_generic(self):
        """用户有两条相同 key：
           - myplugin.ban = false (无context)
           - myplugin.ban = true  (context: group_id=123)
           当前环境 group_id=123 → 精确匹配的 true 应该获胜。
        """
        store = FakeStoreWithDefaults()
        user = User(user_id="456", nodes=[
            PermissionNode(key="myplugin.ban", value=False),
            PermissionNode(key="myplugin.ban", value=True,
                           contexts=ContextSet({"group_id": "123"})),
        ])
        opts = QueryOptions(mode="contextual", contexts=ContextSet({"group_id": "123"}), flags={"include_inherited"})
        resolved = await user.get_effective_nodes(store, opts)
        assert resolved["myplugin.ban"] is True

    @pytest.mark.asyncio
    async def test_generic_wins_when_no_context_match(self):
        """当前环境 group_id=456 → 通用节点 (value=false) 应该生效。"""
        store = FakeStoreWithDefaults()
        user = User(user_id="456", nodes=[
            PermissionNode(key="myplugin.ban", value=False),
            PermissionNode(key="myplugin.ban", value=True,
                           contexts=ContextSet({"group_id": "123"})),
        ])
        opts = QueryOptions(mode="contextual", contexts=ContextSet({"group_id": "456"}), flags={"include_inherited"})
        resolved = await user.get_effective_nodes(store, opts)
        assert resolved["myplugin.ban"] is False

    @pytest.mark.asyncio
    async def test_more_contexts_more_specific(self):
        """三条记录：无ctx / group only / group+role
           当前匹配 group+role → 最精确的获胜。
        """
        store = FakeStoreWithDefaults()
        user = User(user_id="789", nodes=[
            PermissionNode(key="node.x", value=False),
            PermissionNode(key="node.x", value=True, contexts=ContextSet({"group_id": "123"})),
            PermissionNode(key="node.x", value=False, contexts=ContextSet({"group_id": "123", "role": "admin"})),
        ])
        opts = QueryOptions(mode="contextual", contexts=ContextSet({"group_id": "123", "role": "admin"}), flags={"include_inherited"})
        resolved = await user.get_effective_nodes(store, opts)
        # group+role 精确匹配 2 个键 → 最精确 → 获胜
        assert resolved["node.x"] is False


class TestContextProvider:
    def setup_method(self):
        clear_providers()

    def test_register_and_get(self):
        class MockProvider:
            context_keys = {"bind"}
            async def __call__(self, bot, event, current_ctx):
                return {"bind": "true"}
        register_context_provider(MockProvider())
        assert len(get_context_providers()) == 1

    def test_same_key_raises(self):
        class ProviderA:
            context_keys = {"x"}
            async def __call__(self, bot, event, current_ctx):
                return {"x": "1"}
        class ProviderB:
            context_keys = {"x"}
            async def __call__(self, bot, event, current_ctx):
                return {"x": "2"}
        register_context_provider(ProviderA())
        with pytest.raises(DuplicateProviderError):
            register_context_provider(ProviderB())

    def test_different_keys_ok(self):
        clear_providers()

        class ProviderA:
            context_keys = {"a"}
            async def __call__(self, bot, event, current_ctx):
                return {"a": "1"}
        class ProviderB:
            context_keys = {"b"}
            async def __call__(self, bot, event, current_ctx):
                return {"b": "2"}
        register_context_provider(ProviderA())
        register_context_provider(ProviderB())
        assert len(get_context_providers()) == 2

    def test_clear(self):
        clear_providers()
        assert len(get_context_providers()) == 0

    def test_no_context_keys_warns(self):
        clear_providers()
        class NoKeysProvider:
            async def __call__(self, bot, event, current_ctx):
                return {"x": "1"}
        register_context_provider(NoKeysProvider())
        assert len(get_context_providers()) == 1
