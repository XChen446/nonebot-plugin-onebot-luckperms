from __future__ import annotations

import contextvars
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

from ..core.models import User, QueryOptions, ContextSet


@dataclass(frozen=True)
class LPContext:
    user: User
    identity: "Identity"
    query_options: QueryOptions
    resolved_nodes: Dict[str, bool]
    matched_node: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


_lp_context: contextvars.ContextVar[Optional[LPContext]] = contextvars.ContextVar(
    "oblp_context", default=None
)


def get_context() -> Optional[LPContext]:
    return _lp_context.get()


def set_context(ctx: Optional[LPContext]):
    _lp_context.set(ctx)
