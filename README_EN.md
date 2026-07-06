# nonebot-plugin-onebot-luckperms (OBLP)

A LuckPerms-style permission node management system for NoneBot2 + OneBot adapter.

> For Chinese documentation see README.md

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Command Reference](#command-reference)
- [Built-in Context Keys](#built-in-context-keys)
- [Registering Permission Nodes (for Developers)](#registering-permission-nodes-for-developers)
- [ContextProvider (for Developers)](#contextprovider-for-developers)
- [API Reference](#api-reference)

---

## Installation

```bash
pip install nonebot-plugin-onebot-luckperms
```

With SQLite backend (default):

```bash
pip install nonebot-plugin-onebot-luckperms[sqlite]
```

With Redis backend:

```bash
pip install nonebot-plugin-onebot-luckperms[redis]
```

All backends:

```bash
pip install nonebot-plugin-onebot-luckperms[all]
```

---

## Quick Start

Add the plugin in your NoneBot2 `pyproject.toml` or `.env`:

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_onebot_luckperms"]
```

All `/lp` commands require **SUPERUSER** permission (configure `SUPERUSER=123456` in `.env`).

### Grant a permission to a user

```text
/lp user 123456 permission set myplugin.ban true
```

### Create a group and assign permissions

```text
/lp creategroup admin 100
/lp group admin permission set myplugin.kick true
/lp user 123456 parent add admin
```

### Permission scoped to a specific group

```text
/lp user 123456 permission set myplugin.mute true group_id=987654
```

### Temporary permission (auto-expires after 30 minutes)

```text
/lp user 123456 permission settemp myplugin.ban true 30m
```

### Open Web Editor

```text
/lp editor
```

When opened in a group chat, the editor automatically includes all group members in the user list.

---

## Configuration

Set via `.env` or environment variables (prefix `OBLP_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OBLP_STORE_TYPE` | `sqlite` | Storage backend: `memory` / `sqlite` / `redis` |
| `OBLP_SQLITE_PATH` | `./data/oblp/permissions.db` | SQLite file path |
| `OBLP_REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `OBLP_DEFAULT_GROUP_OWNER` | `["*"]` | Nodes auto-granted to group owners |
| `OBLP_DEFAULT_GROUP_ADMIN` | `[]` | Nodes auto-granted to group admins |
| `OBLP_DEFAULT_GROUP_MEMBER` | `[]` | Nodes auto-granted to regular members |
| `OBLP_SUPERUSER_INHERIT` | `["luckperms.*"]` | Nodes auto-granted to SUPERUSER |
| `OBLP_CACHE_TTL` | `300` | Permission cache TTL (seconds), `0` to disable |
| `OBLP_MESSAGE_FILE` | `./data/oblp/messages.yml` | Path to custom message YAML file |
| `OBLP_DEBUG_MODE` | `false` | Log every permission check |

### Example

```ini
SUPERUSER=123456
OBLP_STORE_TYPE=sqlite
OBLP_SQLITE_PATH=./data/oblp/permissions.db
OBLP_DEFAULT_GROUP_ADMIN=["myplugin.mute","myplugin.kick"]
OBLP_DEFAULT_GROUP_MEMBER=[]
```

---

## Command Reference

All commands start with `/lp`. Each command is protected by a corresponding `luckperms.*` permission node.

SUPERUSER has `luckperms.*` by default (all commands). Group owners have `luckperms.help` by default (help only).

### General Commands

| Command | Required Node | Description |
|---------|--------------|-------------|
| `/lp help` | `luckperms.help` | Show help |
| `/lp sync` | `luckperms.sync` | Reload data from storage |
| `/lp info` | `luckperms.info` | Show statistics |
| `/lp editor` | `luckperms.editor` | Open LuckPerms Web Editor |
| `/lp applyedits <code>` | `luckperms.applyedits` | Apply Web Editor edits |

### User Management

| Command | Required Node | Description |
|---------|--------------|-------------|
| `/lp user <id> info` | `luckperms.user.info` | Show user details |
| `/lp user <id> permission ...` | `luckperms.user.permission` | Manage user permissions |
| `/lp user <id> parent ...` | `luckperms.user.parent` | Manage group membership |
| `/lp user <id> promote <track>` | `luckperms.user.promote` | Promote along a track |
| `/lp user <id> demote <track>` | `luckperms.user.demote` | Demote along a track |
| `/lp user <id> clear [ctx...]` | `luckperms.user.clear` | Clear all permission nodes |
| `/lp user <id> clone <target>` | `luckperms.user.clone` | Clone user |
| `/lp user <id> editor` | `luckperms.editor` | Edit this user in the editor |
| `/lp user create <id>` | `luckperms.user.create` | Create a user |
| `/lp user delete <id>` | `luckperms.user.delete` | Delete a user |
| `/lp user list` | `luckperms.user.list` | List all users |

### Group Management

| Command | Required Node | Description |
|---------|--------------|-------------|
| `/lp group <name> info` | `luckperms.group.info` | Show group details |
| `/lp group <name> permission ...` | `luckperms.group.permission` | Manage group permissions |
| `/lp group <name> parent ...` | `luckperms.group.parent` | Inheritance management |
| `/lp group <name> setweight <weight>` | `luckperms.group.setweight` | Set weight |
| `/lp group <name> setdisplayname <name>` | `luckperms.group.setdisplayname` | Set display name |
| `/lp group <name> clear [ctx...]` | `luckperms.group.clear` | Clear permissions |
| `/lp group <name> rename <new>` | `luckperms.group.rename` | Rename group |
| `/lp group <name> clone <new>` | `luckperms.group.clone` | Clone group |
| `/lp group <name> listmembers` | `luckperms.group.listmembers` | List group members |
| `/lp group <name> editor` | `luckperms.editor` | Edit this group in the editor |
| `/lp creategroup <name> [weight]` | `luckperms.group.create` | Create a group |
| `/lp deletegroup <name>` | `luckperms.group.delete` | Delete a group |
| `/lp listgroups` | `luckperms.group.list` | List all groups |

### Track Commands (stub)

| Command | Required Node | Description |
|---------|--------------|-------------|
| `/lp track <name> ...` | `luckperms.*` | Track operations |

### System Commands

| Command | Required Node | Description |
|---------|--------------|-------------|
| `/lp check <user> <node> [ctx...]` | `luckperms.check` | Simulate a permission check |
| `/lp tree [scope]` | `luckperms.tree` | Visualize the permission inheritance tree |

### Temporary Duration Format

| Format | Meaning |
|--------|---------|
| `30s` | 30 seconds |
| `5m` | 5 minutes |
| `2h` | 2 hours |
| `1d` | 1 day |

---

## Built-in Context Keys

Permission nodes can be scoped with `key=value` context constraints. These are injected automatically by the system:

| Context Key | Type | Source          | Example Value |
|-------------|------|-----------------|---------------|
| `platform` | `str` | Adapter type    | `onebot_v11`, `onebot_v12` |
| `user_id` | `str` | Sender's number | `123456` |
| `group_id` | `str` | Group number    | `987654` |
| `role` | `str` | Group role      | `owner`, `admin`, `member`, `superuser` |

Third-party plugins can register custom context keys via ContextProvider (see below).

### Context Usage Examples

Only effective in group 123456:

```text
/lp user 123456 permission set myplugin.ban true group_id=123456
```

Only effective for admins:

```text
/lp user 123456 permission set myplugin.kick true role=admin
```

Only effective for group owner in group 123456:

```text
/lp group admin permission set myplugin.ban true group_id=123456 role=owner
```

---

## Registering Permission Nodes (for Developers)

### Basic Usage

```python
from nonebot import on_command
from nonebot_plugin_onebot_luckperms import register_node, require

# Register at plugin load time
register_node("myplugin.ban", "Ban a user", default=False)

# Bind to a command
ban = on_command("ban", permission=require("myplugin.ban"))

@ban.handle()
async def _():
    await ban.send("Banned")
```

### Registering with Default Context

```python
from nonebot_plugin_onebot_luckperms import register_node, ContextSet

# Only group owners have this by default
register_node("myplugin.admincmd", "Admin command", default=True,
              contexts=ContextSet({"role": "owner"}))

# Only in specific group + admin role
register_node("myplugin.vipcmd", "VIP command", default=True,
              contexts=ContextSet({"group_id": "123456", "role": "admin"}))
```

### require / require_any / require_all

```python
from nonebot_plugin_onebot_luckperms import require, require_any, require_all
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN

# Single node
cmd = on_command("cmd", permission=require("myplugin.cmd"))

# Multi-node OR
cmd = on_command("cmd", permission=require_any("node.a", "node.b"))

# Multi-node AND
cmd = on_command("cmd", permission=require_all("node.a", "node.b"))

# Combine with native permissions
cmd = on_command("cmd", permission=require("myplugin.cmd") | GROUP_ADMIN)
```

### Retrieving Permission Context

```python
from nonebot_plugin_onebot_luckperms import get_context

@cmd.handle()
async def _():
    ctx = get_context()
    if not ctx:
        return
    print(ctx.user.user_id)       # "123456"
    print(ctx.identity.role)      # "admin"
    print(ctx.resolved_nodes)     # {"myplugin.ban": True, ...}
```

---

## ContextProvider (for Developers)

ContextProvider lets third-party plugins inject custom context key-value pairs into the global permission resolution pipeline.

### Define and Register

```python
from nonebot_plugin_onebot_luckperms import register_context_provider

class BindProvider:
    context_keys = {"bind"}  # Declare which keys this provider produces

    async def __call__(self, bot, event, current_ctx):
        # Query from database or API
        return {"bind": "true"}

register_context_provider(BindProvider())
```

After registration, any plugin can leverage this context:

```python
register_node("someplugin.premium", default=True,
              contexts=ContextSet({"bind": "true"}))
```

### Conflict Detection

If two providers declare the same `context_keys`, the second one raises `DuplicateProviderError`:

```python
ProviderA: context_keys = {"bind"}  # Registered OK
ProviderB: context_keys = {"bind"}  # → DuplicateProviderError!
```

---

## API Reference

### User-facing Functions

| Function | Description |
|----------|-------------|
| `require(node_key, contexts=None) -> Permission` | Single-node permission checker |
| `require_any(*node_keys, contexts=None) -> Permission` | OR permission checker |
| `require_all(*node_keys, contexts=None) -> Permission` | AND permission checker |
| `get_context() -> Optional[LPContext]` | Get permission context in handler |
| `get_store() -> Optional[PermissionStore]` | Get current storage backend |

### Developer-facing Functions

| Function | Description |
|----------|-------------|
| `register_node(key, description="", default=False, contexts=None)` | Register a permission node |
| `register_context_provider(provider)` | Register a global ContextProvider |
| `set_resolver(resolver)` | Override the IdentityResolver |
| `ContextSet(data={})` | Context key-value collection |
| `PermissionNode(key, value=True, expiry=None, contexts=ContextSet())` | A single permission node |

### Data Model Classes

```python
@dataclass(frozen=True)
class ContextSet:
    data: Dict[str, str]
    def with_context(self, key, value) -> ContextSet
    def matches(self, requirement) -> bool
    def is_empty(self) -> bool

@dataclass
class PermissionNode:
    key: str
    value: bool
    expiry: Optional[int]
    contexts: ContextSet
    def is_expired(self) -> bool
    def applies_in(self, ctx) -> bool

@dataclass(frozen=True)
class LPContext:
    user: User
    identity: Identity
    query_options: QueryOptions
    resolved_nodes: Dict[str, bool]
    matched_node: Optional[str]
    timestamp: float
```

---

## Test Suite

```bash
pytest tests/ -v
```

91 tests, all passing.

---

## Architecture

```
Layer 4: NoneBot Integration (adapter/) — require(), IdentityResolver, LPContext
Layer 3: Core Engine (core/) — Pure Python, no NoneBot dependency
Layer 2: Storage (storage/) — Memory / SQLite / Redis
Layer 1: Config & Bootstrap (config/) — Pydantic configuration
```

## License

MIT
