from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional
import yaml

logger = logging.getLogger("oblp")

_DEFAULT_MESSAGES: Dict[str, str] = {
    "deny": "Permission denied. You do not have the required permission node.",
    "deny_hint": "You can ask the bot administrator to grant you the required permission.",
    "data_reloaded": "Data reloaded.",
    "unknown_command": "Unknown command: {cmd}. Use /lp help",
    "not_initialized": "OBLP not initialized.",
    "user_not_found": "User {user_id} not found.",
    "user_created": "User {user_id} created.",
    "user_deleted": "User {user_id} deleted.",
    "user_cloned": "User {user_id} cloned to {target}.",
    "user_cleared": "User {user_id} permissions cleared.",
    "user_promoted": "User {user_id} promoted to {track}.",
    "user_demoted": "User {user_id} demoted from {track}.",
    "perm_set": "{entity}: {action} {node}",
    "perm_set_context": "{entity}: {action} {node} (ctx: {context})",
    "perm_temp": "{entity}: temp {action} {node} ({duration})",
    "perm_removed": "{entity}: removed {node}",
    "perm_cleared": "{entity}: permissions cleared",
    "perm_no_nodes": "No permission nodes.",
    "perm_check_result": "{entity} check {node}: {result}",
    "perm_check_allow": "ALLOW",
    "perm_check_deny": "DENY",
    "group_not_found": "Group {name} not found.",
    "group_created": "Group {name} created (weight={weight}).",
    "group_deleted": "Group {name} deleted.",
    "group_already_exists": "Group {name} already exists.",
    "group_renamed": "Group {name} renamed to {new_name}.",
    "group_cloned": "Group {name} cloned to {new_name}.",
    "group_weight_set": "Group {name} weight set to {weight}.",
    "group_displayname_set": "Group {name} display name set to {display_name}.",
    "group_cleared": "Group {name} permissions cleared.",
    "group_no_members": "No members in group {name}.",
    "parent_added": "Added parent {parent} to {entity}.",
    "parent_removed": "Removed parent {parent} from {entity}.",
    "parent_cleared": "{entity}: parents cleared",
    "parent_no_parents": "{entity} has no parents.",
    "primary_group_set": "User {entity} primary group set to {group}.",
    "editor_opened": "Web Editor opened: {url}",
    "editor_failed": "Editor failed: {error}",
    "editor_apply_ok": "Applied edits for code: {code}",
    "editor_apply_failed": "Apply failed: {error}",
}

_messages: Dict[str, str] = {}
_loaded_path: Optional[Path] = None


def load_messages(path: Optional[str] = None):
    global _messages, _loaded_path
    _messages = dict(_DEFAULT_MESSAGES)

    if not path:
        return

    p = Path(path)

    # If file doesn't exist, try to export defaults
    if not p.exists():
        try:
            _export_defaults(str(p))
            logger.info(f"Default message file created at {path}")
        except Exception as e:
            logger.warning(f"Could not create message file at {path}: {e}")
        return

    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = f.read()
        if not raw.strip():
            logger.warning(f"Message file {path} is empty, using defaults")
            return
        custom = yaml.safe_load(raw) or {}
        if not isinstance(custom, dict):
            logger.warning(f"Message file {path} is not a valid YAML mapping, using defaults")
            return
        for k, v in custom.items():
            if k in _messages and isinstance(v, str):
                _messages[k] = v
        _loaded_path = p
        logger.info(f"Messages loaded from {path} ({len(custom)} overrides)")
    except yaml.YAMLError as e:
        logger.error(f"YAML parse error in {path}: {e}")
    except Exception as e:
        logger.error(f"Failed to load message file {path}: {e}")


def msg(key: str, **kwargs) -> str:
    template = _messages.get(key, _DEFAULT_MESSAGES.get(key, key))
    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing placeholder {e} in message '{key}'")
            return template
    return template


def _export_defaults(path: str):
    """Write default messages to a YAML file as a template for users."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        yaml.dump(
            {k: v for k, v in _DEFAULT_MESSAGES.items()},
            f, allow_unicode=True, default_flow_style=False, sort_keys=False,
        )
    logger.info(f"Default message template exported to {path}")
