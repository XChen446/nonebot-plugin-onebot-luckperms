from __future__ import annotations

import fnmatch
from typing import Dict, List, Optional

from .models import User, PermissionNode, QueryOptions, ContextSet
from .registry import NodeRegistry


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

        # Stage 3: Wildcard match
        for pattern, value in user_nodes.items():
            if "*" in pattern and fnmatch.fnmatch(target, pattern):
                return value

        # Stage 4: Prefix inheritance (allow only; deny already handled in stage 2)
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

        # Collect user's own nodes
        for node in user.nodes:
            candidates.append((0, node))

        # Group inheritance
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
                    candidates.append((group.weight, node))

        # Sort by weight descending (higher weight = higher priority)
        candidates.sort(key=lambda x: (-x[0], 0))

        # Context-aware conflict resolution.
        # For each unique key among candidates, we collect all nodes with that key,
        # then pick the one whose context is the BEST match for the current environment.
        # "Best match" = the node whose context has the most matching key-value pairs.
        # A node with no context is the least specific fallback.

        ctx_for_match = options.contexts
        grouped: Dict[str, List[tuple[int, PermissionNode]]] = {}
        for weight, node in candidates:
            if node.is_expired():
                continue
            if options.mode == "contextual" and not node.applies_in(ctx_for_match):
                continue
            grouped.setdefault(node.key, []).append((weight, node))

        seen: Dict[str, bool] = {}

        for key, entries in grouped.items():
            # Among all entries for this key, pick the best one:
            # 1. Higher weight wins
            # 2. If same weight, more context keys matched wins
            best = None
            best_weight = None
            best_match_count = -1

            for weight, node in entries:
                # Count how many of this node's context keys match the current environment
                if options.mode == "contextual" and not node.contexts.is_empty():
                    match_count = sum(
                        1 for k in node.contexts.data
                        if ctx_for_match.data.get(k) == node.contexts.data[k]
                    )
                else:
                    match_count = 0  # no context = lowest specificity

                if best is None:
                    best = node
                    best_weight = weight
                    best_match_count = match_count
                elif weight > best_weight:
                    best = node
                    best_weight = weight
                    best_match_count = match_count
                elif weight == best_weight and match_count > best_match_count:
                    best = node
                    best_match_count = match_count

            if best is not None:
                seen[key] = best.value

        # Apply parent deny inheritance
        keys = list(seen.keys())
        for key in keys:
            if not seen[key]:
                continue
            parts = key.split(".")
            for i in range(len(parts) - 1, 0, -1):
                parent = ".".join(parts[:i])
                if parent in seen and not seen[parent]:
                    del seen[key]
                    break

        # Apply NodeRegistry defaults for unset nodes
        ctx_for_defaults = current_ctx or options.contexts
        for info in NodeRegistry.list_all():
            key = info["key"]
            if key in seen:
                continue
            default_ctx: ContextSet = info.get("contexts", ContextSet())
            if ctx_for_defaults.matches(default_ctx):
                seen[key] = info["default"]

        return seen
