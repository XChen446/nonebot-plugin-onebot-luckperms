from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol

from nonebot.adapters import Bot, Event

logger = logging.getLogger("oblp")


@dataclass
class Identity:
    user_id: str
    platform: str
    group_id: Optional[str] = None
    role: str = "member"
    extra: Dict[str, Any] = field(default_factory=dict)


class IdentityResolver(Protocol):
    async def resolve(self, bot: Bot, event: Event) -> Identity:
        ...


_resolver: Optional[IdentityResolver] = None


def set_resolver(resolver: IdentityResolver):
    global _resolver
    _resolver = resolver
    logger.info(f"IdentityResolver set to {type(resolver).__name__}")


def get_resolver() -> Optional[IdentityResolver]:
    return _resolver


class OneBotV11Resolver:
    async def resolve(self, bot: Bot, event: Event) -> Identity:
        from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent

        user_id = event.get_user_id()
        group_id = None
        role = "member"
        platform = "onebot_v11"

        if isinstance(event, GroupMessageEvent):
            group_id = str(event.group_id)
            if event.sender and event.sender.role:
                role = event.sender.role
        elif isinstance(event, PrivateMessageEvent):
            platform = "onebot_v11_private"

        if user_id in getattr(bot.config, "superusers", set()):
            role = "superuser"

        return Identity(
            user_id=user_id,
            platform=platform,
            group_id=group_id,
            role=role,
            extra={"raw_event_name": event.get_event_name()},
        )
