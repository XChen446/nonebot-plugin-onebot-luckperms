from __future__ import annotations

from typing import Dict, List, Optional

from .models import User, PermissionNode, QueryOptions, ContextSet
from .registry import NodeRegistry


def _match_segments(pattern: str, target: str) -> bool:
    """Segment-based wildcard matching.

    *   matches zero or more segments (multi-segment wildcard).
    **  alias for *, identical behavior.
    Literals must match exactly.

    Per our spec, * matches "a.b" and also "a.b.c" (not single-segment).
    """
    pat_parts = pattern.split(".")
    tgt_parts = target.split(".")
    return _match_dp(pat_parts, tgt_parts)


def _match_dp(p: list[str], t: list[str]) -> bool:
    n, m = len(p), len(t)
    dp = [[False] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = True
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] if p[i - 1] in ("*", "**") else False
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if p[i - 1] in ("*", "**"):
                dp[i][j] = dp[i - 1][j] or dp[i][j - 1]
            elif p[i - 1] == t[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = False
    return dp[n][m]


class PermissionEngine:
    @staticmethod
    def check(user_nodes: Dict[str, bool], target: str) -> bool:
        # Stage 1: Exact match (highest priority)
        if target in user_nodes:
            return user_nodes[target]

        # Stage 2: Parent deny inheritance (security critical)
        parts = target.split(".")
        for i in range(len(parts) - 1, 0, -1):
            parent = ".".join(parts[:i])
            if parent in user_nodes and not user_nodes[parent]:
                return False

        # Stage 3: Wildcard match (segment-based)
        for pattern, value in user_nodes.items():
            if "*" in pattern and _match_segments(pattern, target):
                return value

        # Stage 4: Prefix inheritance (allow only)
        for node_key, value in user_nodes.items():
            if value and target.startswith(node_key + "."):
                return True

        # Stage 5: Inheritance chain via NodeRegistry
        for ancestor in NodeRegistry.get_ancestors(target):
            if ancestor in user_nodes:
                return user_nodes[ancestor]

        # Stage 6: Default deny
        return False

    @staticmethod
    async def resolve_effective_nodes(
        user: User,
        store,
        options: QueryOptions,
        current_ctx: Optional[ContextSet] = None,
    ) -> Dict[str, bool]:
        candidates: List[tuple[int, PermissionNode]] = []
        # sort_key: user nodes = 0, group nodes = 1 + (10000 - weight)
        # This ensures user's own nodes always beat any group-inherited node.

        for node in user.nodes:
            candidates.append((0, node))

        if "include_inherited" in options.flags:
            for group_name in user.groups:
                group = await store.get_group(group_name)
                if group is None:
                    continue
                try:
                    group_nodes = await group.get_effective_nodes(store)
                except Exception:
                    continue
                for node in group_nodes:
                    sort_key = 1 + (10000 - group.weight)
                    candidates.append((sort_key, node))

        candidates.sort(key=lambda x: x[0])

        ctx_for_match = options.contexts
        grouped: Dict[str, List[tuple[int, PermissionNode]]] = {}
        for sort_key, node in candidates:
            if node.is_expired():
                continue
            if options.mode == "contextual" and not node.applies_in(ctx_for_match):
                continue
            grouped.setdefault(node.key, []).append((sort_key, node))

        seen: Dict[str, bool] = {}

        for key, entries in grouped.items():
            best = None
            best_key = None
            best_match = -1

            for sort_key, node in entries:
                if options.mode == "contextual" and not node.contexts.is_empty():
                    match_cnt = sum(
                        1 for k in node.contexts.data
                        if ctx_for_match.data.get(k) == node.contexts.data[k]
                    )
                else:
                    match_cnt = 0

                if best is None:
                    best = node
                    best_key = sort_key
                    best_match = match_cnt
                elif sort_key < best_key:
                    best = node
                    best_key = sort_key
                    best_match = match_cnt
                elif sort_key == best_key and match_cnt > best_match:
                    best = node
                    best_match = match_cnt

            if best is not None:
                seen[key] = best.value

        # Parent deny inheritance
        for key in list(seen.keys()):
            if not seen[key]:
                continue
            parts = key.split(".")
            for i in range(len(parts) - 1, 0, -1):
                parent = ".".join(parts[:i])
                if parent in seen and not seen[parent]:
                    del seen[key]
                    break

        # NodeRegistry defaults
        ctx_for_defaults = current_ctx or options.contexts
        for info in NodeRegistry.list_all():
            key = info["key"]
            if key in seen:
                continue
            default_ctx: ContextSet = info.get("contexts", ContextSet())
            if ctx_for_defaults.matches(default_ctx):
                seen[key] = info["default"]

        return seen
