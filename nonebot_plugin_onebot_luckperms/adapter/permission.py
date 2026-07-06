from __future__ import annotations

import logging
from typing import Optional, Set

from nonebot.permission import Permission
from nonebot.adapters import Bot, Event

from ..core.models import ContextSet, QueryOptions, User, PermissionNode
from ..core.registry import NodeRegistry
from ..core.engine import PermissionEngine
from ..core.cache import PermissionCache
from ..core.context_provider import get_context_providers
from ..config import oblp_config
from ..storage import get_store
from .identity import get_resolver, Identity
from .context import LPContext, set_context

logger = logging.getLogger("oblp")


def _apply_default_nodes(user: User, identity: Identity) -> list:
    """Apply default permission nodes based on the user's role from config."""
    nodes = []
    role_map = {
        "owner": oblp_config.default_group_owner,
        "admin": oblp_config.default_group_admin,
        "member": oblp_config.default_group_member,
        "superuser": oblp_config.superuser_inherit,
    }
    patterns = role_map.get(identity.role, [])
    for pattern in patterns:
        if pattern == "*":
            nodes.append(PermissionNode(key="*", value=True))
        elif pattern:
            nodes.append(PermissionNode(key=pattern, value=True))
    return nodes


def _checker_factory(
    node_keys: Set[str],
    mode: str,
    base_contexts: Optional[ContextSet] = None,
):
    async def checker(bot: Bot, event: Event) -> bool:
        resolver = get_resolver()
        store = get_store()
        if resolver is None or store is None:
            logger.warning("OBLP not initialized: no resolver or store")
            return False

        try:
            identity: Identity = await resolver.resolve(bot, event)
        except Exception as e:
            logger.error(f"Failed to resolve identity: {e}")
            return False

        ctx = ContextSet.from_dict({
            "platform": identity.platform,
            "user_id": identity.user_id,
            "role": identity.role,
        })
        if identity.group_id:
            ctx = ctx.with_context("group_id", identity.group_id)

        if base_contexts:
            for k, v in base_contexts.data.items():
                ctx = ctx.with_context(k, v)

        # Call all registered third-party context providers
        for provider in get_context_providers():
            try:
                extra = await provider(bot, event, ctx)
                if extra:
                    for k, v in extra.items():
                        ctx = ctx.with_context(k, v)
            except Exception:
                logger.exception(f"ContextProvider {type(provider).__name__} error")

        query_opts = QueryOptions(
            mode="contextual",
            contexts=ctx,
            flags={"include_inherited", "resolve_inheritance"},
        )

        cache_key = PermissionCache.make_key(identity.user_id, ctx)
        cached = PermissionCache.get(cache_key)
        if cached is not None:
            resolved = cached
        else:
            user = await store.get_user(identity.user_id)
            if user is None:
                user = User(user_id=identity.user_id)

            default_nodes = _apply_default_nodes(user, identity)
            resolved = await user.get_effective_nodes(store, query_opts, ctx)

            for dn in default_nodes:
                if dn.key not in resolved:
                    resolved[dn.key] = dn.value

            PermissionCache.set(cache_key, resolved)

        matched_node = None
        if mode == "any":
            result = any(
                PermissionEngine.check(resolved, nk)
                for nk in node_keys
            )
            if result:
                for nk in node_keys:
                    if PermissionEngine.check(resolved, nk):
                        matched_node = nk
                        break
        elif mode == "all":
            result = all(
                PermissionEngine.check(resolved, nk)
                for nk in node_keys
            )
            if result:
                matched_node = ",".join(node_keys)
        else:
            target = next(iter(node_keys))
            result = PermissionEngine.check(resolved, target)
            if result:
                matched_node = target

        lp_ctx = LPContext(
            user=user if 'user' in dir() else User(user_id=identity.user_id),
            identity=identity,
            query_options=query_opts,
            resolved_nodes=resolved,
            matched_node=matched_node,
        )
        set_context(lp_ctx)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"[oblp] User {identity.user_id} check {node_keys} "
                f"in {ctx.to_dict()} -> {result}"
            )

        return result

    return checker


def require(node_key: str, contexts: Optional[ContextSet] = None) -> Permission:
    return Permission(_checker_factory({node_key}, "single", contexts))


def require_any(*node_keys: str, contexts: Optional[ContextSet] = None) -> Permission:
    return Permission(_checker_factory(set(node_keys), "any", contexts))


def require_all(*node_keys: str, contexts: Optional[ContextSet] = None) -> Permission:
    return Permission(_checker_factory(set(node_keys), "all", contexts))
