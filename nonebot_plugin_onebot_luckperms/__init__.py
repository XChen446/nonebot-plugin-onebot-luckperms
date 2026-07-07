import logging

from nonebot.plugin import PluginMetadata

from .core.registry import register_node
from .core.models import ContextSet, PermissionNode
from .core.context_provider import register_context_provider, ContextProvider
from .storage import get_store
from .adapter import set_resolver, require, require_any, require_all, get_context
from .adapter.context import LPContext
from .config import OBLPConfig, oblp_config

logger = logging.getLogger("oblp")

__version__ = "0.1.0"

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-onebot-luckperms",
    description="LuckPerms-style permission system for NoneBot2 + OneBot",
    usage="Register nodes with register_node(), use require() in command matchers",
    type="library",
    homepage="https://github.com/XChen446/nonebot-plugin-onebot-luckperms",
    config=OBLPConfig,
    supported_adapters={"~onebot.v11"},
)

__all__ = [
    "register_node",
    "require",
    "require_any",
    "require_all",
    "get_context",
    "set_resolver",
    "ContextSet",
    "PermissionNode",
    "oblp_config",
    "get_store",
    "LPContext",
    "register_context_provider",
    "ContextProvider",
]

_store_initialized = False


def _register_builtin_nodes():
    register_node("luckperms.*", "Access to all LuckPerms commands", default=True)
    register_node("luckperms.help", "View LuckPerms help", default=False)
    register_node("luckperms.info", "View LuckPerms info", default=False)
    register_node("luckperms.sync", "Reload LuckPerms data", default=False)
    register_node("luckperms.editor", "Open LuckPerms Web Editor", default=False)
    register_node("luckperms.applyedits", "Apply Web Editor edits", default=False)
    register_node("luckperms.check", "Check user permissions", default=False)
    register_node("luckperms.tree", "View permission inheritance tree", default=False)
    register_node("luckperms.user.info", "View user details", default=False)
    register_node("luckperms.user.permission", "Manage user permissions", default=False)
    register_node("luckperms.user.parent", "Manage user group membership", default=False)
    register_node("luckperms.user.promote", "Promote user", default=False)
    register_node("luckperms.user.demote", "Demote user", default=False)
    register_node("luckperms.user.clear", "Clear user permissions", default=False)
    register_node("luckperms.user.clone", "Clone user", default=False)
    register_node("luckperms.user.create", "Create user", default=False)
    register_node("luckperms.user.delete", "Delete user", default=False)
    register_node("luckperms.user.list", "List all users", default=False)
    register_node("luckperms.group.info", "View group details", default=False)
    register_node("luckperms.group.permission", "Manage group permissions", default=False)
    register_node("luckperms.group.parent", "Manage group inheritance", default=False)
    register_node("luckperms.group.setweight", "Set group weight", default=False)
    register_node("luckperms.group.setdisplayname", "Set group display name", default=False)
    register_node("luckperms.group.clear", "Clear group permissions", default=False)
    register_node("luckperms.group.rename", "Rename group", default=False)
    register_node("luckperms.group.clone", "Clone group", default=False)
    register_node("luckperms.group.listmembers", "List group members", default=False)
    register_node("luckperms.group.create", "Create group", default=False)
    register_node("luckperms.group.delete", "Delete group", default=False)
    register_node("luckperms.group.list", "List all groups", default=False)


_register_builtin_nodes()


async def _init():
    global _store_initialized

    if _store_initialized:
        return

    from nonebot import get_plugin_config
    from .config import OBLPConfig
    from .storage import init_store
    from .adapter.identity import set_resolver as _set_resolver, OneBotV11Resolver
    from .commands import register_admin_commands
    from .message import load_messages, _export_defaults

    raw_cfg = get_plugin_config(OBLPConfig)

    for field in raw_cfg.model_fields:
        setattr(oblp_config, field, getattr(raw_cfg, field))

    store_type = oblp_config.store_type
    kwargs = {}
    if store_type == "sqlite":
        kwargs["db_path"] = oblp_config.sqlite_path
    elif store_type == "redis":
        kwargs["redis_url"] = oblp_config.redis_url

    store = init_store(store_type, **kwargs)
    await store.load_all()
    _set_resolver(OneBotV11Resolver())
    register_admin_commands()

    await load_messages(oblp_config.message_file)
    try:
        await _export_defaults(oblp_config.message_file)
    except Exception:
        pass

    _store_initialized = True
    logger.info(f"OBLP initialized (store: {store_type})")


try:
    from nonebot import get_driver
    driver = get_driver()
    driver.on_startup(_init)
except (ValueError, RuntimeError, ImportError):
    logger.debug("NoneBot not initialized, OBLP will init on first use")
