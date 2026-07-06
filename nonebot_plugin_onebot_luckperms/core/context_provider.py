from __future__ import annotations

import logging
from typing import Dict, List, Protocol

from nonebot.adapters import Bot, Event

from .models import ContextSet

logger = logging.getLogger("oblp")


class DuplicateProviderError(Exception):
    """Raised when a ContextProvider registers a key already claimed by another provider."""


class ContextProvider(Protocol):
    async def __call__(
        self, bot: Bot, event: Event, current_ctx: ContextSet
    ) -> Dict[str, str]:
        ...


_context_providers: List[ContextProvider] = []
_claimed_keys: Dict[str, str] = {}  # key → provider_identity


def _provider_identity(provider: ContextProvider) -> str:
    return f"{type(provider).__module__}.{type(provider).__qualname__}"


def register_context_provider(provider: ContextProvider):
    identity = _provider_identity(provider)

    # Probe which keys this provider returns by running it with an empty context
    # (We can't call it here since it needs bot/event. Instead, require provider
    #  to declare its keys statically via a `context_keys` class attribute.)

    if hasattr(provider, "context_keys"):
        keys: set[str] = provider.context_keys
    else:
        keys = set()

    if not keys:
        logger.warning(
            f"ContextProvider '{identity}' does not declare `context_keys`. "
            f"Add a class-level `context_keys = {{\"your_key\"}}` to prevent conflicts."
        )

    conflicts = []
    for k in keys:
        if k in _claimed_keys:
            conflicts.append((k, _claimed_keys[k]))

    if conflicts:
        detail = "; ".join(f"key='{k}' already claimed by {owner}" for k, owner in conflicts)
        raise DuplicateProviderError(
            f"ContextProvider '{identity}' conflicts: {detail}"
        )

    for k in keys:
        _claimed_keys[k] = identity

    _context_providers.append(provider)
    logger.info(f"ContextProvider registered: {identity} keys={keys}")


def get_context_providers() -> List[ContextProvider]:
    return list(_context_providers)


def clear_providers():
    _context_providers.clear()
    _claimed_keys.clear()
