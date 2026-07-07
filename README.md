# nonebot-plugin-onebot-luckperms（OBLP）

LuckPerms 风格的权限节点管理系统，专为 NoneBot2 + OneBot 适配器设计。

> English： [README_EN.md](./README_EN.md)

---

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [配置](#配置)
- [命令列表](#命令列表)
- [内建 Context 键](#内建-context-键)
- [权限节点注册（面向开发者）](#权限节点注册面向开发者)
- [ContextProvider（面向开发者）](#contextprovider面向开发者)
- [API 参考](#api-参考)

---

## 安装

### 通过 NB-CLI（推荐）

```bash
nb plugin install nonebot-plugin-onebot-luckperms
```

### 通过 pip

```bash
pip install nonebot-plugin-onebot-luckperms
```

如需 Redis 后端：

```bash
pip install nonebot-plugin-onebot-luckperms[redis]
```

全部安装：

```bash
pip install nonebot-plugin-onebot-luckperms[all]
```

---

## 快速开始

在 NoneBot2 的 `pyproject.toml` 或 `.env` 中添加插件：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_onebot_luckperms"]
```

插件加载后，所有 `/lp` 命令默认仅 **SUPERUSER**（在 `env` 中配置 `SUPERUSER=123456`）可执行。

### 给用户一个权限

```text
/lp user 123456 permission set myplugin.ban true
```

### 创建一个组并分配权限

```text
/lp creategroup admin 100
/lp group admin permission set myplugin.kick true
/lp user 123456 parent add admin
```

### 设置仅在特定群生效的权限

```text
/lp user 123456 permission set myplugin.mute true group_id=987654
```

### 临时权限（30 分钟后自动过期）

```text
/lp user 123456 permission settemp myplugin.ban true 30m
```

### 打开 Web Editor

```text
/lp editor
```

在群聊中打开时，editor 会自动附带该群所有成员 QQ 到用户列表。

---

## 配置

在 `.env` 或 `pyproject.toml` 中（前缀 `OBLP_`）：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `OBLP_STORE_TYPE` | `sqlite` | 存储后端：`memory` / `sqlite` / `redis` |
| `OBLP_SQLITE_PATH` | `./data/oblp/permissions.db` | SQLite 文件路径 |
| `OBLP_REDIS_URL` | `redis://localhost:6379/0` | Redis 连接 URL |
| `OBLP_DEFAULT_GROUP_OWNER` | `["luckperms.help"]` | 群主自动继承的权限节点 |
| `OBLP_DEFAULT_GROUP_ADMIN` | `[]` | 群管理自动继承的权限节点 |
| `OBLP_DEFAULT_GROUP_MEMBER` | `[]` | 普通成员自动继承的权限节点 |
| `OBLP_SUPERUSER_INHERIT` | `["luckperms.*"]` | SUPERUSER 自动继承的权限节点 |
| `OBLP_CACHE_TTL` | `300` | 权限缓存时间（秒），`0` 禁用缓存 |
| `OBLP_MESSAGE_FILE` | `./data/oblp/messages.yml` | 自定义回复消息的 YAML 文件路径 |
| `OBLP_DEBUG_MODE` | `false` | 开启后打印每次权限判定日志 |

### 配置示例

```ini
SUPERUSER=123456
OBLP_STORE_TYPE=sqlite
OBLP_SQLITE_PATH=./data/oblp/permissions.db
OBLP_DEFAULT_GROUP_ADMIN=["myplugin.mute","myplugin.kick"]
OBLP_DEFAULT_GROUP_MEMBER=[]
```

---

## 命令列表

所有命令均以 `/lp` 开头。每个命令都受对应的 `luckperms.*` 权限节点保护。

SUPERUSER 默认拥有 `luckperms.*`（全部权限）。群主默认拥有 `luckperms.help`（仅能看帮助）。

### 通用命令

| 命令 | 所需权限节点 | 说明 |
|------|-------------|------|
| `/lp help` | `luckperms.help` | 显示帮助 |
| `/lp sync` | `luckperms.sync` | 重新加载数据 |
| `/lp info` | `luckperms.info` | 显示统计信息 |
| `/lp editor` | `luckperms.editor` | 打开 LuckPerms Web Editor |
| `/lp applyedits <code>` | `luckperms.applyedits` | 应用 Web Editor 的 edits |

### 用户管理

| 命令 | 所需权限节点 | 说明 |
|------|-------------|------|
| `/lp user <id> info` | `luckperms.user.info` | 查看用户详情 |
| `/lp user <id> permission ...` | `luckperms.user.permission` | 管理用户权限节点 |
| `/lp user <id> parent ...` | `luckperms.user.parent` | 管理用户组 |
| `/lp user <id> promote <track>` | `luckperms.user.promote` | 晋升 |
| `/lp user <id> demote <track>` | `luckperms.user.demote` | 降级 |
| `/lp user <id> clear [ctx...]` | `luckperms.user.clear` | 清空所有权限节点 |
| `/lp user <id> clone <target>` | `luckperms.user.clone` | 克隆用户 |
| `/lp user <id> editor` | `luckperms.editor` | 在 editor 中编辑此用户 |
| `/lp user create <id>` | `luckperms.user.create` | 创建用户 |
| `/lp user delete <id>` | `luckperms.user.delete` | 删除用户 |
| `/lp user list` | `luckperms.user.list` | 列出所有用户 |

### 组管理

| 命令 | 所需权限节点 | 说明 |
|------|-------------|------|
| `/lp group <name> info` | `luckperms.group.info` | 查看组详情 |
| `/lp group <name> permission ...` | `luckperms.group.permission` | 管理组权限 |
| `/lp group <name> parent ...` | `luckperms.group.parent` | 继承管理 |
| `/lp group <name> setweight <weight>` | `luckperms.group.setweight` | 设置权重 |
| `/lp group <name> setdisplayname <name>` | `luckperms.group.setdisplayname` | 设置显示名 |
| `/lp group <name> clear [ctx...]` | `luckperms.group.clear` | 清空权限 |
| `/lp group <name> rename <new>` | `luckperms.group.rename` | 重命名组 |
| `/lp group <name> clone <new>` | `luckperms.group.clone` | 克隆组 |
| `/lp group <name> listmembers` | `luckperms.group.listmembers` | 列出组成员 |
| `/lp group <name> editor` | `luckperms.editor` | 在 editor 中编辑此组 |
| `/lp creategroup <name> [weight]` | `luckperms.group.create` | 创建组 |
| `/lp deletegroup <name>` | `luckperms.group.delete` | 删除组 |
| `/lp listgroups` | `luckperms.group.list` | 列出所有组 |

### 轨道管理（预留）

| 命令 | 所需权限节点 | 说明 |
|------|-------------|------|
| `/lp track <name> ...` | `luckperms.*` | 轨道操作 |

### 系统命令

| 命令 | 所需权限节点 | 说明 |
|------|-------------|------|
| `/lp check <user> <node> [ctx...]` | `luckperms.check` | 模拟权限检查 |
| `/lp tree [scope]` | `luckperms.tree` | 权限继承树可视化 |

### 命令执行反馈

无权限时（用户没有所需的 `luckperms.xxx` 节点），bot 回复 `deny` 消息。

### 自定义回复消息

所有用户可见的回复文本均存储在 `OBLP_MESSAGE_FILE` 指向的 YAML 文件中（默认 `./data/oblp/messages.yml`）。
插件首次运行时会自动生成此文件。你可以编辑它来自定义所有回复，支持占位符：

```yaml
# data/oblp/messages.yml
deny: "你没有权限执行此命令。"
deny_hint: "请联系管理员开通对应权限节点。"
perm_set: "{entity}: {action} {node}"
perm_temp: "{entity}: 临时{action} {node} ({duration})"
editor_opened: "Web 编辑器已开启: {url}"
```

可用占位符：
| 占位符 | 说明 |
|--------|------|
| `{user_id}` | 用户 ID |
| `{node}` | 权限节点名 |
| `{entity}` | 用户或组 ID |
| `{action}` | grant 或 deny |
| `{duration}` | 持续时间 |
| `{context}` | 上下文键值对 |
| `{url}` | Editor URL |
| `{code}` | Edit code |
| `{error}` | 错误描述 |
| `{name}` | 组名 |
| `{weight}` | 组权重 |

有权限时的执行反馈示例：

```
/lp sync
→ Data reloaded

/lp user 123456 permission set myplugin.ban true
→ 123456: grant myplugin.ban

/lp user 123456 permission settemp myplugin.kick false 30m
→ 123456: temp deny myplugin.kick (30m)

/lp group admin permission set myplugin.mute true group_id=987654
→ admin: grant myplugin.mute (ctx: {'group_id': '987654'})

/lp check 123456 myplugin.ban
→ Check: user=123456, node=myplugin.ban
  Context: (empty)
  Result: ALLOW
  Resolved nodes (2):
    myplugin.ban=grant
    luckperms.*=grant
```

### 默认角色权限

| 角色 | 默认拥有的节点 | 说明 |
|------|--------------|------|
| SUPERUSER | `luckperms.*` | 全部命令 |
| 群主 (owner) | `luckperms.help` | 仅可看帮助（可配置） |
| 管理 (admin) | *(空)* | 无内建命令权限（可配置） |
| 成员 (member) | *(空)* | 无内建命令权限（可配置） |

可通过 `OBLP_DEFAULT_GROUP_OWNER`、`OBLP_DEFAULT_GROUP_ADMIN`、`OBLP_DEFAULT_GROUP_MEMBER` 配置。

### 临时权限 duration 格式

| 写法 | 含义 |
|------|------|
| `30s` | 30 秒 |
| `5m` | 5 分钟 |
| `2h` | 2 小时 |
| `1d` | 1 天 |

---

## 内建 Context 键

权限节点可以通过 `key=value` 附加上下文约束，使节点仅在特定环境中生效。由系统自动注入：

| Context 键 | 类型 | 来源      | 示例值 |
|-----------|------|---------|--------|
| `platform` | `str` | 适配器类型   | `onebot_v11`, `onebot_v12` |
| `user_id` | `str` | 发送者 ID  | `123456` |
| `group_id` | `str` | 群号（群聊时） | `987654` |
| `role` | `str` | 群内角色    | `owner`, `admin`, `member`, `superuser` |

第三方插件可通过 ContextProvider（见下文）注册自定义 Context 键。

### Context 使用示例

仅群 123456 中有效：

```text
/lp user 123456 permission set myplugin.ban true group_id=123456
```

仅群管理时有效：

```text
/lp user 123456 permission set myplugin.kick true role=admin
```

仅群 123456 且为群主时有效：

```text
/lp group admin permission set myplugin.ban true group_id=123456 role=owner
```

---

## 权限节点注册（面向开发者）

### 基本用法

```python
from nonebot import on_command
from nonebot_plugin_onebot_luckperms import register_node, require

# 在插件加载时注册节点
register_node("myplugin.ban", "禁言用户", default=False)

# 绑定到命令
ban = on_command("ban", permission=require("myplugin.ban"))

@ban.handle()
async def _():
    await ban.send("已执行")
```

### 带默认上下文的注册

```python
from nonebot_plugin_onebot_luckperms import register_node, ContextSet

# 仅群主默认拥有此权限
register_node("myplugin.admincmd", "管理命令", default=True,
              contexts=ContextSet({"role": "owner"}))

# 仅在特定群 + admin 时默认拥有
register_node("myplugin.vipcmd", "VIP 命令", default=True,
              contexts=ContextSet({"group_id": "123456", "role": "admin"}))
```

### require / require_any / require_all

```python
from nonebot_plugin_onebot_luckperms import require, require_any, require_all
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN

# 单节点
cmd = on_command("cmd", permission=require("myplugin.cmd"))

# 多节点 OR
cmd = on_command("cmd", permission=require_any("node.a", "node.b"))

# 多节点 AND
cmd = on_command("cmd", permission=require_all("node.a", "node.b"))

# 与原生权限组合
cmd = on_command("cmd", permission=require("myplugin.cmd") | GROUP_ADMIN)
```

### 获取权限上下文

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

## ContextProvider（面向开发者）

ContextProvider 允许第三方插件向全局权限判定环境注入自定义 Context 键值对。

### 定义并注册

```python
from nonebot_plugin_onebot_luckperms import register_context_provider

class BindProvider:
    context_keys = {"bind"}  # 声明此 provider 会注入的键

    async def __call__(self, bot, event, current_ctx):
        # 从数据库或 API 查询用户的绑定状态
        return {"bind": "true"}  # 键值对会合并到判定上下文中

register_context_provider(BindProvider())
```

注册后，其他所有插件都可以利用这个 Context 来控制权限生效范围：

```python
register_node("someplugin.premium", default=True,
              contexts=ContextSet({"bind": "true"}))
```

### 冲突检测

如果两个不同的 Provider 声明了相同的 `context_keys`，后者注册时会抛出 `DuplicateProviderError`：

```python
ProviderA: context_keys = {"bind"}  # 注册成功
ProviderB: context_keys = {"bind"}  # → DuplicateProviderError!
```

---

## API 参考

### 用户端函数

| 函数 | 说明 |
|------|------|
| `require(node_key, contexts=None) -> Permission` | 单节点权限检查器 |
| `require_any(*node_keys, contexts=None) -> Permission` | OR 权限检查器 |
| `require_all(*node_keys, contexts=None) -> Permission` | AND 权限检查器 |
| `get_context() -> Optional[LPContext]` | 在 Handler 中获取权限上下文 |
| `get_store() -> Optional[PermissionStore]` | 获取当前存储后端 |

### 开发者端函数

| 函数 | 说明 |
|------|------|
| `register_node(key, description="", default=False, contexts=None)` | 注册权限节点 |
| `register_context_provider(provider)` | 注册全局 ContextProvider |
| `set_resolver(resolver)` | 覆盖 IdentityResolver |
| `ContextSet(data={})` | 上下文集合 |
| `PermissionNode(key, value=True, expiry=None, contexts=ContextSet())` | 权限节点 |

### 模型类

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

## 测试

```bash
pytest tests/ -v
```

当前 91 项测试全部通过。

---

## 架构

```
Layer 4: NoneBot Integration (adapter/) — require(), IdentityResolver, LPContext
Layer 3: Core Engine (core/) — 纯 Python，不依赖 NoneBot
Layer 2: Storage (storage/) — Memory / SQLite / Redis
Layer 1: Config & Bootstrap (config/) — Pydantic 配置
```

## License

MIT
