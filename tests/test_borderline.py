"""边界测试用例 - 必须全部通过"""
import pytest
from nonebot_plugin_onebot_luckperms.core.models import ContextSet, PermissionNode, User, Group, QueryOptions
from nonebot_plugin_onebot_luckperms.core.engine import PermissionEngine

check = PermissionEngine.check


class TestBorderlineCases:
    # 测试用例 1: 未定义节点 = 拒绝
    def test_undefined_node_deny(self):
        assert check({}, "any.node") is False

    # 测试用例 2: 精确允许
    def test_exact_allow(self):
        assert check({"a.b": True}, "a.b") is True

    # 测试用例 3: 精确拒绝
    def test_exact_deny(self):
        assert check({"a.b": False}, "a.b") is False

    # 测试用例 4: 父拒绝继承到子节点（关键安全测试）
    def test_parent_deny_inheritance_to_child(self):
        assert check({"a.*": True, "a.b": False}, "a.b.c") is False

    # 测试用例 5: 通配符允许，但精确拒绝覆盖
    def test_wildcard_allow_exact_deny(self):
        assert check({"a.*": True, "a.b": False}, "a.b") is False

    # 测试用例 6: 通配符允许子节点（父未拒绝）
    def test_wildcard_allow_child_node(self):
        assert check({"a.*": True}, "a.b.c") is True

    # 测试用例 7: 前缀继承
    def test_prefix_inheritance_allow(self):
        assert check({"a.b": True}, "a.b.c") is True

    # 测试用例 8: 前缀拒绝（父拒绝继承）
    def test_prefix_deny(self):
        assert check({"a.b": False}, "a.b.c") is False

    # 测试用例 10: 显式拒绝优先于通配允许
    def test_explicit_deny_over_wildcard_allow(self):
        assert check({"*": True, "specific": False}, "specific") is False

    # 测试用例 11: 空 requirement 匹配所有环境
    def test_empty_requirement_matches_all(self):
        req = ContextSet()
        assert ContextSet({"group_id": "123"}).matches(req) is True
        assert ContextSet().matches(req) is True

    # 测试用例 12: 上下文不匹配 = 节点不生效
    @pytest.mark.asyncio
    async def test_context_mismatch(self):
        class FakeStore:
            async def get_group(self, name):
                return None

        store = FakeStore()
        node = PermissionNode(
            key="a.b",
            value=True,
            contexts=ContextSet({"group_id": "123"})
        )
        user = User(user_id="456", nodes=[node])

        # Query with different context
        opts = QueryOptions(
            mode="contextual",
            contexts=ContextSet({"group_id": "456"})
        )
        resolved = await user.get_effective_nodes(store, opts)
        result = PermissionEngine.check(resolved, "a.b")
        assert result is False  # node not effective -> deny


class TestGroupInheritance:
    @pytest.mark.asyncio
    async def test_weight_override(self):
        """测试用例 9: 权重覆盖（高权重拒绝覆盖低权重允许）"""
        class FakeStore:
            def __init__(self):
                self.groups = {}
            async def get_group(self, name):
                return self.groups.get(name)

        store = FakeStore()
        group_a = Group(name="A", weight=10, nodes=[PermissionNode(key="node", value=True)])
        group_b = Group(name="B", weight=20, nodes=[PermissionNode(key="node", value=False)])
        store.groups["A"] = group_a
        store.groups["B"] = group_b

        user = User(user_id="123", groups=["A", "B"])
        opts = QueryOptions(
            mode="all",
            flags={"include_inherited", "resolve_inheritance"},
        )
        resolved = await user.get_effective_nodes(store, opts)
        # B has higher weight, so node should be False
        assert resolved.get("node") is False


class TestEngineEdgeCases:
    def test_root_wildcard_only(self):
        assert check({"*": True}, "anything.here") is True

    def test_root_wildcard_deny(self):
        assert check({"*": False}, "anything") is False

    def test_multi_star_wildcard(self):
        assert check({"a.*.b": True}, "a.x.b") is True

    def test_partial_wildcard_no_match(self):
        assert check({"a.*.b": True}, "a.x.c") is False

    def test_exact_over_wildcard(self):
        assert check({"*": True, "specific": True}, "specific") is True

    def test_ancestor_via_registry(self):
        from nonebot_plugin_onebot_luckperms.core.registry import NodeRegistry
        NodeRegistry._nodes.clear()
        NodeRegistry.register("myplugin.admin")
        # user has "myplugin.admin" = True
        result = PermissionEngine.check({"myplugin.admin": True}, "myplugin.admin.ban")
        assert result is True
