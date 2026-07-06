from __future__ import annotations

import time
import uuid
import logging
from typing import Any, Dict, List, Optional

from ..core.models import User, Group, PermissionNode, ContextSet
from ..storage import get_store, PermissionStore

log = logging.getLogger("oblp.webeditor")


def node_to_webeditor(node: PermissionNode) -> dict[str, Any]:
    d: dict[str, Any] = {
        "type": "permission",
        "key": node.key,
        "value": node.value,
    }
    ctx = node.contexts.to_dict()
    if ctx:
        d["context"] = {k: [v] for k, v in ctx.items()}
    if node.expiry is not None:
        d["expiry"] = int(node.expiry)
    return d


def node_from_webeditor(data: dict[str, Any]) -> PermissionNode:
    expiry = data.get("expiry")
    raw_ctx = data.get("context", {})
    flat_ctx: dict[str, str] = {}
    for k, vlist in raw_ctx.items():
        if isinstance(vlist, list) and vlist:
            flat_ctx[k] = str(vlist[0])
        elif isinstance(vlist, str):
            flat_ctx[k] = vlist

    raw_value = data.get("value", True)
    if isinstance(raw_value, bool):
        value = raw_value
    elif isinstance(raw_value, str):
        value = raw_value.lower() in ("true", "t", "1", "yes", "on")
    else:
        value = bool(raw_value)

    return PermissionNode(
        key=data["key"],
        value=value,
        expiry=expiry,
        contexts=ContextSet.from_dict(flat_ctx),
    )


async def to_webeditor_payload(extra_user_ids: list[str] | None = None) -> dict[str, Any]:
    store = get_store()
    if store is None:
        raise RuntimeError("OBLP not initialized")

    permission_holders: list[dict[str, Any]] = []
    seen_users: set[str] = set()

    known_perms: set[str] = set()
    potential_ctxs: dict[str, set[str]] = {}

    def collect_node_meta(nodes: list[PermissionNode]):
        for n in nodes:
            known_perms.add(n.key)
            for k, v in n.contexts.data.items():
                potential_ctxs.setdefault(k, set()).add(v)

    # 1) Groups (always included)
    groups = await store.list_groups()
    for gname in groups:
        g = await store.get_group(gname)
        if g is None:
            continue
        collect_node_meta(g.nodes)
        holder: dict[str, Any] = {
            "type": "group",
            "id": g.name,
            "displayName": g.display_name or g.name,
            "nodes": [node_to_webeditor(n) for n in g.nodes if not n.is_expired()],
            "parents": list(g.parents),
        }
        permission_holders.append(holder)

    # 2) Users with custom permissions (already defined)
    user_ids = await store.list_users()
    for uid in user_ids:
        u = await store.get_user(uid)
        if u is None:
            continue
        seen_users.add(uid)
        collect_node_meta(u.nodes)
        holder: dict[str, Any] = {
            "type": "user",
            "id": u.user_id,
            "displayName": u.username or u.user_id,
            "nodes": [node_to_webeditor(n) for n in u.nodes if not n.is_expired()],
            "parents": list(u.groups),
        }
        permission_holders.append(holder)

    # 3) Extra users from session context (even if default), deduplicated
    if extra_user_ids:
        for uid in extra_user_ids:
            if uid in seen_users:
                continue
            seen_users.add(uid)
            u = await store.get_user(uid)
            if u is not None:
                holder: dict[str, Any] = {
                    "type": "user",
                    "id": u.user_id,
                    "displayName": u.username or u.user_id,
                    "nodes": [node_to_webeditor(n) for n in u.nodes if not n.is_expired()],
                    "parents": list(u.groups),
                }
            else:
                holder: dict[str, Any] = {
                    "type": "user",
                    "id": uid,
                    "displayName": uid,
                    "nodes": [],
                    "parents": [],
                }
            permission_holders.append(holder)

    payload: dict[str, Any] = {
        "metadata": {
            "commandAlias": "oblp",
            "uploader": {
                "name": "Console",
                "uuid": str(uuid.uuid4()),
            },
            "time": int(time.time() * 1000),
            "pluginVersion": "0.1.0",
            "platform": "NoneBot2",
        },
        "permissionHolders": permission_holders,
        "tracks": [],
        "knownPermissions": sorted(known_perms),
        "potentialContexts": {k: sorted(v) for k, v in potential_ctxs.items()},
    }
    return payload


async def apply_webeditor_changes(payload: dict[str, Any]):
    store = get_store()
    if store is None:
        raise RuntimeError("OBLP not initialized")

    if "changes" in payload:
        await _apply_delta_changes(store, payload)
    else:
        await _apply_full_changes(store, payload)


async def _apply_delta_changes(store: PermissionStore, payload: dict[str, Any]):
    changes = payload.get("changes", [])
    group_deletions = payload.get("groupDeletions", [])
    user_deletions = payload.get("userDeletions", [])

    for gid in group_deletions:
        await store.delete_group(gid)
        log.info("[delta] deleted group: %s", gid)
    for uid in user_deletions:
        await store.delete_user(uid)
        log.info("[delta] deleted user: %s", uid)

    for change in changes:
        ctype = change.get("type")
        cid = change.get("id")
        if not ctype or not cid:
            continue

        nodes = [node_from_webeditor(n) for n in change.get("nodes", [])]

        if ctype == "group":
            g = Group(
                name=cid,
                display_name=change.get("displayName", cid),
                weight=change.get("weight", 0),
                nodes=nodes,
                parents=change.get("parents", []),
            )
            await store.save_group(g)
            log.debug("[delta] upserted group: %s", cid)

        elif ctype == "user":
            u = User(
                user_id=cid,
                username=change.get("displayName", cid),
                groups=change.get("parents", []),
                nodes=nodes,
            )
            await store.save_user(u)
            log.debug("[delta] upserted user: %s", cid)

    log.info("[delta] applied changes")


async def _apply_full_changes(store: PermissionStore, payload: dict[str, Any]):
    holders = payload.get("permissionHolders", [])

    for h in holders:
        nodes = [node_from_webeditor(n) for n in h.get("nodes", [])]

        if h.get("type") == "group":
            g = Group(
                name=h["id"],
                display_name=h.get("displayName", h["id"]),
                weight=h.get("weight", 0),
                nodes=nodes,
                parents=h.get("parents", []),
            )
            await store.save_group(g)

        elif h.get("type") == "user":
            u = User(
                user_id=h["id"],
                username=h.get("displayName", h["id"]),
                groups=h.get("parents", []),
                nodes=nodes,
            )
            await store.save_user(u)

    log.info("[full] applied changes: %d holders", len(holders))
