from typing import Optional, List, Dict

from ..core.models import User, Group, PermissionNode


class MemoryStore:
    def __init__(self):
        self._users: Dict[str, User] = {}
        self._groups: Dict[str, Group] = {}
        self._registered_nodes: Dict[str, PermissionNode] = {}

    async def get_user(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    async def save_user(self, user: User) -> None:
        self._users[user.user_id] = user

    async def delete_user(self, user_id: str) -> None:
        self._users.pop(user_id, None)

    async def list_users(self) -> List[str]:
        return list(self._users.keys())

    async def get_group(self, name: str) -> Optional[Group]:
        return self._groups.get(name)

    async def save_group(self, group: Group) -> None:
        self._groups[group.name] = group

    async def delete_group(self, name: str) -> None:
        self._groups.pop(name, None)

    async def list_groups(self) -> List[str]:
        return list(self._groups.keys())

    async def get_registered_nodes(self) -> List[PermissionNode]:
        return list(self._registered_nodes.values())

    async def save_registered_node(self, node: PermissionNode) -> None:
        self._registered_nodes[node.key] = node

    async def load_all(self) -> None:
        pass

    async def save_all(self) -> None:
        pass
