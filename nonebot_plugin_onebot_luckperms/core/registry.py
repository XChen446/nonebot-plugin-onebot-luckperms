from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .models import PermissionNode, ContextSet

logger = logging.getLogger("oblp")


class NodeRegistry:
    _nodes: Dict[str, dict] = {}

    @classmethod
    def register(
        cls,
        key: str,
        description: str = "",
        default: bool = False,
        contexts: Optional[ContextSet] = None,
    ):
        if key in cls._nodes:
            existing = cls._nodes[key]
            if existing.get("description") != description or existing.get("contexts") != (contexts or ContextSet()):
                logger.warning(
                    f"Node '{key}' already registered with different parameters, "
                    f"keeping first registration"
                )
            return
        cls._nodes[key] = {
            "key": key,
            "description": description,
            "default": default,
            "contexts": contexts or ContextSet(),
        }

    @classmethod
    def get(cls, key: str) -> Optional[dict]:
        return cls._nodes.get(key)

    @classmethod
    def list_all(cls) -> List[dict]:
        return list(cls._nodes.values())

    @classmethod
    def get_ancestors(cls, key: str) -> List[str]:
        parts = key.split(".")
        ancestors = []
        for i in range(len(parts) - 1, 0, -1):
            ancestors.append(".".join(parts[:i]))
        return ancestors

    @classmethod
    def get_default(cls, key: str) -> bool:
        info = cls._nodes.get(key)
        if info is None:
            for pattern, val in cls._nodes.items():
                if "*" in pattern:
                    import fnmatch
                    if fnmatch.fnmatch(key, pattern):
                        return val.get("default", False)
            return False
        return info.get("default", False)


def register_node(
    key: str,
    description: str = "",
    default: bool = False,
    contexts: Optional[ContextSet] = None,
):
    NodeRegistry.register(key, description, default, contexts)
