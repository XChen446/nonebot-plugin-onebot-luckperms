from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Literal

from .exceptions import CircularInheritanceError


@dataclass(frozen=True)
class ContextSet:
    data: Dict[str, str] = field(default_factory=dict)

    def with_context(self, key: str, value: str) -> ContextSet:
        return ContextSet(data={**self.data, key: value})

    def matches(self, requirement: ContextSet) -> bool:
        if requirement.is_empty():
            return True
        for k, v in requirement.data.items():
            if self.data.get(k) != v:
                return False
        return True

    def is_empty(self) -> bool:
        return len(self.data) == 0

    @classmethod
    def from_dict(cls, d: Dict[str, str]) -> ContextSet:
        return cls(data=dict(d))

    def to_dict(self) -> Dict[str, str]:
        return dict(self.data)


@dataclass
class PermissionNode:
    key: str
    value: bool = True
    expiry: Optional[int] = None
    contexts: ContextSet = field(default_factory=ContextSet)

    def is_expired(self) -> bool:
        if self.expiry is None:
            return False
        return time.time() >= self.expiry

    def applies_in(self, ctx: ContextSet) -> bool:
        return ctx.matches(self.contexts)


@dataclass
class QueryOptions:
    mode: Literal["contextual", "all"] = "contextual"
    contexts: ContextSet = field(default_factory=ContextSet)
    flags: Set[str] = field(default_factory=lambda: {"include_inherited", "resolve_inheritance"})


@dataclass
class Group:
    name: str
    display_name: Optional[str] = None
    weight: int = 0
    nodes: List[PermissionNode] = field(default_factory=list)
    parents: List[str] = field(default_factory=list)

    async def get_effective_nodes(
        self,
        store,
        visited: Optional[Set[str]] = None,
    ) -> List[PermissionNode]:
        if visited is None:
            visited = set()
        if self.name in visited:
            raise CircularInheritanceError(
                f"Circular inheritance detected: group '{self.name}' already visited"
            )
        visited.add(self.name)

        result = list(self.nodes)

        for parent_name in self.parents:
            parent = await store.get_group(parent_name)
            if parent is None:
                continue
            if parent.name in visited:
                raise CircularInheritanceError(
                    f"Circular inheritance detected: group '{parent.name}' already visited"
                )
            parent_nodes = await parent.get_effective_nodes(store, visited)
            result.extend(parent_nodes)

        return result


@dataclass
class User:
    user_id: str
    username: Optional[str] = None
    primary_group: Optional[str] = None
    groups: List[str] = field(default_factory=list)
    nodes: List[PermissionNode] = field(default_factory=list)

    async def get_effective_nodes(
        self,
        store,
        options: QueryOptions,
        current_ctx: Optional["ContextSet"] = None,
    ) -> Dict[str, bool]:
        from .engine import PermissionEngine
        return await PermissionEngine.resolve_effective_nodes(self, store, options, current_ctx)

    async def has_permission(
        self,
        node_key: str,
        store,
        options: QueryOptions,
    ) -> bool:
        from .engine import PermissionEngine
        return PermissionEngine.check(
            await self.get_effective_nodes(store, options),
            node_key,
        )
