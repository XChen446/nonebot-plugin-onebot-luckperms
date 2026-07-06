import logging
import time
from typing import Optional

from nonebot import on_command
from nonebot.adapters import Bot, Event
from nonebot.params import CommandArg
from nonebot.matcher import Matcher

from ..core.models import ContextSet, PermissionNode, User, Group, QueryOptions
from ..core.registry import NodeRegistry
from ..core.engine import PermissionEngine
from ..core.cache import PermissionCache
from ..core.context_provider import get_context_providers
from ..storage import get_store
from ..adapter.identity import get_resolver, Identity
from ..adapter.context import LPContext, set_context
from ..config import oblp_config
from ..message import msg

logger = logging.getLogger("oblp")


def _parse_context(args: list) -> ContextSet:
    ctx = {}
    for a in args:
        if "=" in a:
            k, v = a.split("=", 1)
            ctx[k] = v
    return ContextSet.from_dict(ctx)


def _parse_duration(dur_str: str) -> Optional[int]:
    if not dur_str:
        return None
    dur_str = dur_str.lower()
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    suffix = dur_str[-1]
    if suffix in multipliers:
        try:
            return int(dur_str[:-1]) * multipliers[suffix]
        except ValueError:
            return None
    try:
        return int(dur_str)
    except ValueError:
        return None


async def _check_lp(bot: Bot, event: Event, matcher: Matcher, node_key: str) -> bool:
    """Check luckperms node + fallback luckperms.*, send deny message on failure."""
    resolver = get_resolver()
    store = get_store()
    if resolver is None or store is None:
        return False

    try:
        identity = await resolver.resolve(bot, event)
    except Exception:
        return False

    ctx = ContextSet.from_dict({
        "platform": identity.platform,
        "user_id": identity.user_id,
        "role": identity.role,
    })
    if identity.group_id:
        ctx = ctx.with_context("group_id", identity.group_id)

    for provider in get_context_providers():
        try:
            extra = await provider(bot, event, ctx)
            if extra:
                for k, v in extra.items():
                    ctx = ctx.with_context(k, v)
        except Exception:
            logger.exception(f"ContextProvider error")

    opts = QueryOptions(mode="contextual", contexts=ctx, flags={"include_inherited", "resolve_inheritance"})

    user_obj = await store.get_user(identity.user_id)
    if user_obj is None:
        user_obj = User(user_id=identity.user_id)

    resolved = await user_obj.get_effective_nodes(store, opts, ctx)

    if PermissionEngine.check(resolved, node_key):
        return True
    if node_key != "luckperms.*" and PermissionEngine.check(resolved, "luckperms.*"):
        return True

    try:
        await matcher.send(msg("deny"))
        await matcher.send(msg("deny_hint"))
    except Exception:
        pass
    return False


CLP = None


def register_admin_commands():
    global CLP
    CLP = on_command("lp", aliases={"luckperms"}, block=True)
    CLP.handle()(_handler)


async def _handler(bot: Bot, event: Event, matcher: Matcher, arg=CommandArg()):
    store = get_store()
    if store is None:
        return

    raw = arg.extract_plain_text().strip()
    parts = raw.split()
    if not parts:
        if await _check_lp(bot, event, matcher, "luckperms.help"):
            await matcher.send(
                "LuckPerms commands:\n"
                "  sync / info / editor / applyedits <code>\n"
                "  creategroup / deletegroup / listgroups\n"
                "  createtrack / deletetrack / listtracks\n"
                "  check <user> <node> [ctx...]\n"
                "  tree [scope] [player]\n"
                "  user <user> <action> ...\n"
                "  group <group> <action> ...\n"
                "  track <track> <action> ..."
            )
        return

    cmd = parts[0].lower()

    try:
        # ── General commands ────────────────────────────────

        if cmd in ("help", "?"):
            if await _check_lp(bot, event, matcher, "luckperms.help"):
                await matcher.send(
                    "LuckPerms commands:\n"
                    "  sync / info / editor / applyedits <code>\n"
                    "  creategroup / deletegroup / listgroups\n"
                    "  createtrack / deletetrack / listtracks\n"
                    "  check <user> <node> [ctx...]\n"
                    "  tree [scope] [player]\n"
                    "  user <user> <action> ...\n"
                    "  group <group> <action> ...\n"
                    "  track <track> <action> ..."
                )

        elif cmd == "sync":
            if not await _check_lp(bot, event, matcher, "luckperms.sync"):
                return
            await store.load_all()
            PermissionCache.invalidate_all()
            await matcher.send(msg("data_reloaded"))

        elif cmd == "info":
            if not await _check_lp(bot, event, matcher, "luckperms.info"):
                return
            groups = await store.list_groups()
            users = await store.list_users()
            await matcher.send(f"OBLP v0.1.0\nUsers: {len(users)}\nGroups: {len(groups)}\nStore: {type(store).__name__}")

        elif cmd == "editor":
            if not await _check_lp(bot, event, matcher, "luckperms.editor"):
                return
            await _cmd_editor(bot, event, matcher, store, parts[1:])

        elif cmd == "applyedits":
            if not await _check_lp(bot, event, matcher, "luckperms.applyedits"):
                return
            if len(parts) < 2:
                await matcher.finish("Usage: /lp applyedits <code>")
            await _apply_edits(matcher, parts[1])

        elif cmd == "creategroup":
            if not await _check_lp(bot, event, matcher, "luckperms.group.create"):
                return
            name = parts[1] if len(parts) > 1 else None
            if not name:
                await matcher.finish("Usage: /lp creategroup <name> [weight]")
            weight = int(parts[2]) if len(parts) > 2 else 0
            existing = await store.get_group(name)
            if existing:
                await matcher.finish(f"Group {name} already exists")
            await store.save_group(Group(name=name, weight=weight))
            await matcher.send(f"Group {name} created (weight={weight})")

        elif cmd == "deletegroup":
            if not await _check_lp(bot, event, matcher, "luckperms.group.delete"):
                return
            if len(parts) < 2:
                await matcher.finish("Usage: /lp deletegroup <name>")
            await store.delete_group(parts[1])
            await matcher.send(f"Group {parts[1]} deleted")

        elif cmd == "listgroups":
            if not await _check_lp(bot, event, matcher, "luckperms.group.list"):
                return
            groups = await store.list_groups()
            if not groups:
                await matcher.send("No groups")
            else:
                lines = ["Groups:"]
                for gname in groups:
                    g = await store.get_group(gname)
                    if g:
                        lines.append(f"  {g.name} (weight={g.weight}, parents={g.parents})")
                await matcher.send("\n".join(lines))

        elif cmd == "check":
            if not await _check_lp(bot, event, matcher, "luckperms.check"):
                return
            if len(parts) < 3:
                await matcher.finish("Usage: /lp check <user> <node> [ctx...]")
            await _cmd_check(matcher, store, parts[1], parts[2], parts[3:])

        elif cmd == "tree":
            if not await _check_lp(bot, event, matcher, "luckperms.tree"):
                return
            await _cmd_tree(matcher, store, parts[1:])

        elif cmd == "user":
            if len(parts) < 2:
                await matcher.finish("Usage: /lp user <user> info|permission|parent|meta|editor|promote|demote|showtracks|clear|clone")
            await _cmd_user(bot, event, matcher, store, parts[1], parts[2:])

        elif cmd == "group":
            if len(parts) < 2:
                await matcher.finish("Usage: /lp group <group> info|permission|parent|meta|editor|setweight|setdisplayname|showtracks|clear|rename|clone|listmembers")
            await _cmd_group(bot, event, matcher, store, parts[1], parts[2:])

        elif cmd == "track":
            if len(parts) < 2:
                await matcher.finish("Usage: /lp track <track> info|editor|append|insert|remove|clear|rename|clone")
            await _cmd_track(matcher, store, parts[1], parts[2:])

        else:
            if await _check_lp(bot, event, matcher, "luckperms.help"):
                await matcher.send(f"Unknown command: {cmd}. Use /lp help")

    except Exception as e:
        logger.exception("Command error")
        await matcher.finish(f"Error: {e}")


# ── User ──────────────────────────────────────────────────────────

async def _cmd_user(bot: Bot, event: Event, matcher: Matcher, store, user_id: str, args):
    if not args:
        await matcher.finish("Usage: /lp user <user> info|permission|parent|meta|editor|promote|demote|showtracks|clear|clone")

    action = args[0].lower()

    if action == "info":
        if not await _check_lp(bot, event, matcher, "luckperms.user.info"):
            return
        user = await store.get_user(user_id)
        if user is None:
            await matcher.finish(f"User {user_id} not found")
        lines = [
            f"User: {user.user_id}",
            f"Username: {user.username or 'N/A'}",
            f"Primary Group: {user.primary_group or 'N/A'}",
            f"Groups: {', '.join(user.groups) if user.groups else 'None'}",
            f"Nodes ({len(user.nodes)}):",
        ]
        for n in user.nodes:
            ctx_str = n.contexts.to_dict()
            ctx_info = f" ctx={ctx_str}" if ctx_str else ""
            expiry_info = f" expires={n.expiry}" if n.expiry else ""
            lines.append(f"  {n.key}={'grant' if n.value else 'deny'}{ctx_info}{expiry_info}")
        await matcher.send("\n".join(lines))

    elif action == "permission":
        if not await _check_lp(bot, event, matcher, "luckperms.user.permission"):
            return
        await _cmd_permission(matcher, store, user_id, is_user=True, args=args[1:])

    elif action == "parent":
        if not await _check_lp(bot, event, matcher, "luckperms.user.parent"):
            return
        await _cmd_parent(matcher, store, user_id, is_user=True, args=args[1:])

    elif action == "meta":
        if not await _check_lp(bot, event, matcher, "luckperms.user.permission"):
            return
        await _cmd_meta(matcher, store, user_id, is_user=True, args=args[1:])

    elif action == "editor":
        if not await _check_lp(bot, event, matcher, "luckperms.editor"):
            return
        await _cmd_editor(bot, event, matcher, store, [])

    elif action == "promote":
        if not await _check_lp(bot, event, matcher, "luckperms.user.promote"):
            return
        if len(args) < 2:
            await matcher.finish("Usage: /lp user <user> promote <track> [ctx...]")
        track_name = args[1]
        user = await store.get_user(user_id)
        if user is None:
            user = User(user_id=user_id)
        if track_name not in user.groups:
            user.groups.append(track_name)
        await store.save_user(user)
        await matcher.send(f"User {user_id} promoted to {track_name}")

    elif action == "demote":
        if not await _check_lp(bot, event, matcher, "luckperms.user.demote"):
            return
        if len(args) < 2:
            await matcher.finish("Usage: /lp user <user> demote <track> [ctx...]")
        track_name = args[1]
        user = await store.get_user(user_id)
        if user is None:
            await matcher.finish(f"User {user_id} not found")
        user.groups = [g for g in user.groups if g != track_name]
        await store.save_user(user)
        await matcher.send(f"User {user_id} demoted from {track_name}")

    elif action == "showtracks":
        if not await _check_lp(bot, event, matcher, "luckperms.user.info"):
            return
        user = await store.get_user(user_id)
        if user is None:
            await matcher.finish(f"User {user_id} not found")
        await matcher.send(f"Groups for {user_id}: {', '.join(user.groups) if user.groups else 'None'}")

    elif action == "clear":
        if not await _check_lp(bot, event, matcher, "luckperms.user.clear"):
            return
        ctx = _parse_context(args[1:])
        user = await store.get_user(user_id)
        if user:
            if ctx.is_empty():
                user.nodes = []
            else:
                user.nodes = [n for n in user.nodes if not n.applies_in(ctx)]
            await store.save_user(user)
        await matcher.send(f"User {user_id} permissions cleared")

    elif action == "clone":
        if not await _check_lp(bot, event, matcher, "luckperms.user.clone"):
            return
        if len(args) < 2:
            await matcher.finish("Usage: /lp user <user> clone <target_user>")
        target = args[1]
        src = await store.get_user(user_id)
        if src is None:
            await matcher.finish(f"User {user_id} not found")
        dst = User(user_id=target, username=src.username, primary_group=src.primary_group,
                    groups=list(src.groups), nodes=[PermissionNode(**n.__dict__) for n in src.nodes])
        await store.save_user(dst)
        await matcher.send(f"User {user_id} cloned to {target}")

    else:
        await matcher.finish(f"Unknown user action: {action}")


# ── Group ─────────────────────────────────────────────────────────

async def _cmd_group(bot: Bot, event: Event, matcher: Matcher, store, name: str, args):
    if not args:
        await matcher.finish("Usage: /lp group <group> info|permission|parent|meta|editor|setweight|setdisplayname|showtracks|clear|rename|clone|listmembers")

    action = args[0].lower()

    if action == "info":
        if not await _check_lp(bot, event, matcher, "luckperms.group.info"):
            return
        group = await store.get_group(name)
        if group is None:
            await matcher.finish(f"Group {name} not found")
        lines = [
            f"Group: {group.name}",
            f"Display Name: {group.display_name or 'N/A'}",
            f"Weight: {group.weight}",
            f"Parents: {', '.join(group.parents) if group.parents else 'None'}",
            f"Nodes ({len(group.nodes)}):",
        ]
        for n in group.nodes:
            ctx_str = n.contexts.to_dict()
            ctx_info = f" ctx={ctx_str}" if ctx_str else ""
            lines.append(f"  {n.key}={'grant' if n.value else 'deny'}{ctx_info}")
        await matcher.send("\n".join(lines))

    elif action == "permission":
        if not await _check_lp(bot, event, matcher, "luckperms.group.permission"):
            return
        await _cmd_permission(matcher, store, name, is_user=False, args=args[1:])

    elif action == "parent":
        if not await _check_lp(bot, event, matcher, "luckperms.group.parent"):
            return
        await _cmd_parent(matcher, store, name, is_user=False, args=args[1:])

    elif action == "meta":
        if not await _check_lp(bot, event, matcher, "luckperms.group.permission"):
            return
        await _cmd_meta(matcher, store, name, is_user=False, args=args[1:])

    elif action == "editor":
        if not await _check_lp(bot, event, matcher, "luckperms.editor"):
            return
        await _cmd_editor(bot, event, matcher, store, [])

    elif action == "setweight":
        if not await _check_lp(bot, event, matcher, "luckperms.group.setweight"):
            return
        if len(args) < 2:
            await matcher.finish("Usage: /lp group <group> setweight <weight>")
        group = await store.get_group(name)
        if group is None:
            await matcher.finish(f"Group {name} not found")
        group.weight = int(args[1])
        await store.save_group(group)
        await matcher.send(f"Group {name} weight set to {args[1]}")

    elif action == "setdisplayname":
        if not await _check_lp(bot, event, matcher, "luckperms.group.setdisplayname"):
            return
        if len(args) < 2:
            await matcher.finish("Usage: /lp group <group> setdisplayname <name>")
        group = await store.get_group(name)
        if group is None:
            await matcher.finish(f"Group {name} not found")
        group.display_name = args[1]
        await store.save_group(group)
        await matcher.send(f"Group {name} display name set to {args[1]}")

    elif action == "showtracks":
        if not await _check_lp(bot, event, matcher, "luckperms.group.info"):
            return
        group = await store.get_group(name)
        if group is None:
            await matcher.finish(f"Group {name} not found")
        await matcher.send(f"Parents of {name}: {', '.join(group.parents) if group.parents else 'None'}")

    elif action == "clear":
        if not await _check_lp(bot, event, matcher, "luckperms.group.clear"):
            return
        ctx = _parse_context(args[1:])
        group = await store.get_group(name)
        if group:
            if ctx.is_empty():
                group.nodes = []
            else:
                group.nodes = [n for n in group.nodes if not n.applies_in(ctx)]
            await store.save_group(group)
        await matcher.send(f"Group {name} permissions cleared")

    elif action == "rename":
        if not await _check_lp(bot, event, matcher, "luckperms.group.rename"):
            return
        if len(args) < 2:
            await matcher.finish("Usage: /lp group <group> rename <new_name>")
        group = await store.get_group(name)
        if group is None:
            await matcher.finish(f"Group {name} not found")
        await store.delete_group(name)
        group.name = args[1]
        await store.save_group(group)
        await matcher.send(f"Group {name} renamed to {args[1]}")

    elif action == "clone":
        if not await _check_lp(bot, event, matcher, "luckperms.group.clone"):
            return
        if len(args) < 2:
            await matcher.finish("Usage: /lp group <group> clone <new_name>")
        group = await store.get_group(name)
        if group is None:
            await matcher.finish(f"Group {name} not found")
        new_name = args[1]
        new_group = Group(name=new_name, display_name=group.display_name, weight=group.weight,
                          nodes=[PermissionNode(**n.__dict__) for n in group.nodes],
                          parents=list(group.parents))
        await store.save_group(new_group)
        await matcher.send(f"Group {name} cloned to {new_name}")

    elif action == "listmembers":
        if not await _check_lp(bot, event, matcher, "luckperms.group.listmembers"):
            return
        users = await store.list_users()
        members = []
        for uid in users:
            u = await store.get_user(uid)
            if u and name in u.groups:
                members.append(uid)
        if not members:
            await matcher.send(f"No members in group {name}")
        else:
            await matcher.send(f"Members of {name}:\n" + "\n".join(f"  {m}" for m in members))

    else:
        await matcher.finish(f"Unknown group action: {action}")


# ── Track ─────────────────────────────────────────────────────────

async def _cmd_track(matcher: Matcher, store, track_name: str, args):
    if not args:
        await matcher.finish("Usage: /lp track <track> info|editor|append|insert|remove|clear|rename|clone")
    action = args[0].lower()
    await matcher.send(f"Track commands not yet implemented (stub)")


# ── Permission subcommand ─────────────────────────────────────────

async def _cmd_permission(matcher: Matcher, store, entity_id: str, is_user: bool, args):
    if not args:
        await matcher.finish("Usage: permission info|set|unset|settemp|unsettemp|check|clear")

    sub = args[0].lower()
    entity = await (store.get_user(entity_id) if is_user else store.get_group(entity_id))
    if entity is None:
        entity = User(user_id=entity_id) if is_user else Group(name=entity_id)

    async def _save():
        if is_user:
            await store.save_user(entity)
        else:
            await store.save_group(entity)

    if sub == "info":
        if not entity.nodes:
            await matcher.send("No permission nodes")
        else:
            lines = [f"Permissions for {entity_id}:"]
            for n in entity.nodes:
                ctx_str = n.contexts.to_dict()
                ctx_info = f" ctx={ctx_str}" if ctx_str else ""
                expiry_info = f" expires={n.expiry}" if n.expiry else ""
                lines.append(f"  {n.key}={'grant' if n.value else 'deny'}{ctx_info}{expiry_info}")
            await matcher.send("\n".join(lines))
        return

    elif sub == "set":
        if len(args) < 2:
            await matcher.finish("Usage: permission set <node> <true|false> [ctx...]")
        node_key = args[1]
        value = True
        idx = 2
        if len(args) > 2 and args[2].lower() in ("true", "false", "grant", "deny"):
            value = args[2].lower() in ("true", "grant")
            idx = 3
        ctx = _parse_context(args[idx:])
        node = PermissionNode(key=node_key, value=value, contexts=ctx)
        entity.nodes = [n for n in entity.nodes if not (n.key == node.key and n.contexts == node.contexts)]
        entity.nodes.append(node)
        await _save()
        info = f"{'grant' if value else 'deny'} {node_key}"
        if not ctx.is_empty():
            info += f" (ctx: {ctx.to_dict()})"
        await matcher.send(f"{entity_id}: {info}")

    elif sub == "unset":
        if len(args) < 2:
            await matcher.finish("Usage: permission unset <node> [ctx...]")
        node_key = args[1]
        ctx = _parse_context(args[2:])
        if ctx.is_empty():
            entity.nodes = [n for n in entity.nodes if n.key != node_key]
        else:
            entity.nodes = [n for n in entity.nodes if not (n.key == node_key and n.contexts == ctx)]
        await _save()
        await matcher.send(f"{entity_id}: removed {node_key}")

    elif sub == "settemp":
        if len(args) < 4:
            await matcher.finish("Usage: permission settemp <node> <true|false> <duration> [ctx...]")
        node_key = args[1]
        value = args[2].lower() in ("true", "grant")
        duration = _parse_duration(args[3])
        if duration is None:
            await matcher.finish("Invalid duration. Use e.g. 30s, 5m, 2h, 1d")
        ctx = _parse_context(args[4:])
        expiry = int(time.time()) + duration
        node = PermissionNode(key=node_key, value=value, expiry=expiry, contexts=ctx)
        entity.nodes = [n for n in entity.nodes if not (n.key == node.key and n.contexts == node.contexts)]
        entity.nodes.append(node)
        await _save()
        await matcher.send(f"{entity_id}: temp {'grant' if value else 'deny'} {node_key} ({args[3]})")

    elif sub == "unsettemp":
        if len(args) < 2:
            await matcher.finish("Usage: permission unsettemp <node> [duration] [ctx...]")
        node_key = args[1]
        entity.nodes = [n for n in entity.nodes if n.key != node_key]
        await _save()
        await matcher.send(f"{entity_id}: removed temp {node_key}")

    elif sub == "check":
        if len(args) < 2:
            await matcher.finish("Usage: permission check <node>")
        node_key = args[1]
        ctx = _parse_context(args[2:])
        if is_user:
            opts = type("Opts", (), {
                "mode": "contextual",
                "contexts": ctx,
                "flags": {"include_inherited", "resolve_inheritance"},
            })()
            resolved = await entity.get_effective_nodes(store, opts) if isinstance(entity, User) else {}
        else:
            resolved = {}
            for n in entity.nodes:
                if not n.is_expired() and n.applies_in(ctx):
                    resolved[n.key] = n.value
        result = PermissionEngine.check(resolved, node_key)
        await matcher.send(f"{entity_id} check {node_key}: {'ALLOW' if result else 'DENY'}")

    elif sub == "clear":
        ctx = _parse_context(args[1:])
        if ctx.is_empty():
            entity.nodes = []
        else:
            entity.nodes = [n for n in entity.nodes if not n.applies_in(ctx)]
        await _save()
        await matcher.send(f"{entity_id}: permissions cleared")

    else:
        await matcher.finish(f"Unknown permission action: {sub}")


# ── Parent subcommand ─────────────────────────────────────────────

async def _cmd_parent(matcher: Matcher, store, entity_id: str, is_user: bool, args):
    if not args:
        await matcher.finish("Usage: parent info|set|add|remove|settrack|addtemp|removetemp|clear|cleartrack|switchprimarygroup")

    sub = args[0].lower()
    entity = await (store.get_user(entity_id) if is_user else store.get_group(entity_id))
    if entity is None:
        entity = User(user_id=entity_id) if is_user else Group(name=entity_id)

    def _get_parents():
        return entity.groups if is_user else entity.parents

    async def _save():
        if is_user:
            await store.save_user(entity)
        else:
            await store.save_group(entity)

    async def _add_parent(gname: str):
        current = _get_parents()
        if gname not in current:
            if is_user:
                entity.groups.append(gname)
            else:
                entity.parents.append(gname)
        await _save()

    async def _remove_parent(gname: str):
        if is_user:
            entity.groups = [g for g in entity.groups if g != gname]
        else:
            entity.parents = [p for p in entity.parents if p != gname]
        await _save()

    if sub == "info":
        parents = _get_parents()
        if not parents:
            await matcher.send(f"{entity_id} has no parents")
        else:
            await matcher.send(f"Parents of {entity_id}:\n" + "\n".join(f"  {p}" for p in parents))

    elif sub == "set":
        if len(args) < 2:
            await matcher.finish("Usage: parent set <group> [ctx...]")
        ctx = _parse_context(args[2:])
        if is_user:
            entity.groups = []
        else:
            entity.parents = []
        await _add_parent(args[1])

    elif sub == "add":
        if len(args) < 2:
            await matcher.finish("Usage: parent add <group> [ctx...]")
        await _add_parent(args[1])
        await matcher.send(f"Added parent {args[1]} to {entity_id}")

    elif sub == "remove":
        if len(args) < 2:
            await matcher.finish("Usage: parent remove <group> [ctx...]")
        await _remove_parent(args[1])
        await matcher.send(f"Removed parent {args[1]} from {entity_id}")

    elif sub in ("settrack", "addtemp", "removetemp", "cleartrack"):
        await matcher.send(f"'{sub}' not yet implemented")

    elif sub == "clear":
        ctx = _parse_context(args[1:])
        if is_user:
            entity.groups = []
        else:
            entity.parents = []
        await _save()
        await matcher.send(f"{entity_id}: parents cleared")

    elif sub == "switchprimarygroup":
        if len(args) < 2:
            await matcher.finish("Usage: parent switchprimarygroup <group>")
        if is_user:
            entity.primary_group = args[1]
            await _save()
            await matcher.send(f"User {entity_id} primary group set to {args[1]}")
        else:
            await matcher.finish("switchprimarygroup only applies to users")

    else:
        await matcher.finish(f"Unknown parent action: {sub}")


# ── Meta subcommand (stub) ────────────────────────────────────────

async def _cmd_meta(matcher: Matcher, store, entity_id: str, is_user: bool, args):
    if not args:
        await matcher.finish("Usage: meta info|set|unset|settemp|unsettemp|addprefix|addsuffix|setprefix|setsuffix|removeprefix|removesuffix|clear")
    await matcher.send("Meta commands not yet implemented")


# ── Check ─────────────────────────────────────────────────────────

async def _cmd_check(matcher: Matcher, store, user_id: str, node_key: str, ctx_args):
    ctx = _parse_context(ctx_args)
    opts = type("Opts", (), {
        "mode": "contextual",
        "contexts": ctx,
        "flags": {"include_inherited", "resolve_inheritance"},
    })()
    user = await store.get_user(user_id)
    if user is None:
        user = User(user_id=user_id)
    resolved = await user.get_effective_nodes(store, opts)
    result = PermissionEngine.check(resolved, node_key)
    lines = [
        f"Check: user={user_id}, node={node_key}",
        f"Context: {ctx.to_dict() or '(empty)'}",
        f"Result: {'ALLOW' if result else 'DENY'}",
        f"Resolved nodes ({len(resolved)}):",
    ]
    for k, v in sorted(resolved.items()):
        lines.append(f"  {k}={'grant' if v else 'deny'}")
    await matcher.send("\n".join(lines))


# ── Tree ──────────────────────────────────────────────────────────

async def _cmd_tree(matcher: Matcher, store, args):
    scope = args[0] if args else None
    user = await store.get_user(scope) if scope else None
    group = await store.get_group(scope) if scope else None

    if user:
        lines = [f"User: {user.user_id}"]
        for gname in user.groups:
            g = await store.get_group(gname)
            if g:
                lines.append(f"  └── Group: {g.name} (weight={g.weight})")
                for n in g.nodes:
                    lines.append(f"        ├── {n.key}={'grant' if n.value else 'deny'}")
        await matcher.send("\n".join(lines))
    elif group:
        lines = [f"Group: {group.name} (weight={group.weight})"]
        for n in group.nodes:
            lines.append(f"  ├── {n.key}={'grant' if n.value else 'deny'}")
        await matcher.send("\n".join(lines))
    else:
        groups = await store.list_groups()
        if not groups:
            await matcher.send("No groups")
        else:
            lines = ["Groups:"]
            for gname in groups:
                g = await store.get_group(gname)
                if g:
                    lines.append(f"  {g.name} (weight={g.weight})")
                    for n in g.nodes:
                        lines.append(f"    ├── {n.key}={'grant' if n.value else 'deny'}")
            await matcher.send("\n".join(lines))


# ── Editor ────────────────────────────────────────────────────────

async def _cmd_editor(bot: Bot, event: Event, matcher: Matcher, store, args):
    from ..webeditor.manager import to_webeditor_payload, apply_webeditor_changes
    from ..webeditor.session import WebEditorSession
    from ..adapter.identity import get_resolver

    resolver = get_resolver()
    group_members: list[str] | None = None
    extra_users: list[str] = []
    chat_type = "unknown"

    try:
        identity = await resolver.resolve(bot, event) if resolver else None
    except Exception:
        identity = None

    if identity:
        chat_type = identity.platform
        if identity.group_id:
            try:
                from nonebot.adapters.onebot.v11 import Bot as V11Bot
                if isinstance(bot, V11Bot):
                    member_list = await bot.get_group_member_list(group_id=int(identity.group_id))
                    group_members = [str(m["user_id"]) for m in member_list]
                    extra_users = group_members
            except Exception:
                pass
            chat_type = f"group({identity.group_id})"
        else:
            extra_users = [identity.user_id]

    try:
        payload = await to_webeditor_payload(extra_user_ids=extra_users)
    except RuntimeError as e:
        await matcher.finish(f"Editor error: {e}")

    payload["metadata"]["context"] = {
        "chat_type": chat_type,
        "group_members": len(group_members) if group_members else 0,
    }

    session = WebEditorSession(
        get_payload=lambda: payload,
        apply_changes=lambda p: None,
    )

    async def _apply(p):
        await apply_webeditor_changes(p)
    session.apply_changes = _apply

    try:
        url = await session.open()
        await matcher.send(msg("editor_opened", url=url))
    except Exception as e:
        await matcher.finish(msg("editor_failed", error=str(e)))


async def _apply_edits(matcher: Matcher, code: str):
    from ..webeditor.manager import apply_webeditor_changes
    from ..webeditor.bytebin import BytebinClient

    try:
        client = BytebinClient()
        payload = await client.download(code)
        await apply_webeditor_changes(payload)
        store = get_store()
        if store:
            await store.save_all()
        await matcher.send(msg("editor_apply_ok", code=code))
    except Exception as e:
        await matcher.finish(f"Apply failed: {e}")
