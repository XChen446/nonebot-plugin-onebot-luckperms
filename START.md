# prompt.md

## 项目概述

**项目名称**: `nonebot-plugin-onebot-luckperms`（简称 `oblp`）

**目标**: 参考原版 LuckPerms（Java Minecraft 插件）的核心权限哲学，从零实现一个专为 NoneBot2 + OneBot 适配器设计的权限节点管理系统。不直接 fork 现有 Python LuckPerms 实现，而是**重新设计**，使其深度适配 NoneBot 的事件驱动架构。

**可参考学习资料**：基于 python 实现的 luckperms：https://github.com/XChen446/LuckPerms-Python 建议clone到本地作为参考资料

**核心约束**:
- 必须作为 NoneBot2 插件加载（`pyproject.toml` 入口）
- 必须兼容 OneBot V11 适配器（可扩展至 V12）
- 必须利用 NoneBot 原生 `Permission` 机制在事件处理最前端拦截
- 调用方（业务插件）代码必须极致简洁：只关心"我要什么节点"，不关心"权限从哪来"

---

## 一、核心设计哲学（必须严格遵守）

### 1.1 上下文驱动（Context-Driven）

原版 LuckPerms 的灵魂是 `ContextSet`。在本项目中，任何权限判定都必须携带当前环境上下文。OneBot 场景下的标准上下文键：

| Context Key | 来源 | 示例值 |
|-------------|------|--------|
| `platform` | 适配器类型 | `onebot_v11`, `onebot_v12` |
| `group_id` | 群号（群聊时） | `123456789` |
| `user_id` | QQ 号 | `987654321` |
| `role` | 群内角色 | `owner`, `admin`, `member` |
| `chat_type` | 聊天类型 | `group`, `private`, `temp` |

**判定规则**: 节点可以绑定特定上下文（如 `myplugin.ban` 仅在 `group_id=123456` 且 `role=admin` 时生效）。查询时，当前环境的 `ContextSet` 必须**包含**节点要求的所有键值对才算匹配。

### 1.2 节点是结构化对象，不是字符串

禁止将权限节点当作纯字符串处理。每个节点必须是一个结构化对象，包含：

```python
@dataclass
class PermissionNode:
    key: str              # 节点名，如 "myplugin.ban"
    value: bool = True    # True=授予, False=显式拒绝
    expiry: Optional[int] = None  # Unix 时间戳，None=永久
    contexts: ContextSet = field(default_factory=ContextSet)  # 生效环境
```

### 1.3 用户-组分离 + 权重继承

必须实现：
- **User**: 持有专属节点 + 所属组列表
- **Group**: 持有组节点 + 父组列表（继承链）+ `weight`（权重，冲突时高权重优先）
- 计算有效权限时，必须递归解析继承链，合并所有来源的节点

### 1.4 查询选项（QueryOptions）

任何权限查询都必须通过 `QueryOptions` 进行，支持：

```python
@dataclass
class QueryOptions:
    mode: Literal["contextual", "all"] = "contextual"
    # contextual: 仅返回匹配当前上下文的节点
    # all: 返回所有节点（用于管理/调试）
    contexts: ContextSet = field(default_factory=ContextSet)
    flags: Set[str] = field(default_factory=lambda: {"include_inherited", "resolve_inheritance"})
```

---

## 二、安全原则（权限系统的核心边界）

### 2.1 默认拒绝（Default Deny）

**未定义的权限节点，默认行为必须是拒绝。**

```
用户查询 "unknown.node"
    → 节点未注册且用户无此节点
    → 返回 False
    → 最终判定: ❌ 拒绝
```

**为什么必须默认拒绝？**

| 场景 | 如果默认允许 | 如果默认拒绝 |
|------|-----------|-----------|
| 新插件上线，未配置权限 | 所有人都能用 ❌ | 只有超级用户能用 ✅ |
| 节点拼写错误 | 意外开放权限 ❌ | 安全降级 ✅ |
| 数据库故障，节点丢失 | 权限失效 ❌ | 安全降级 ✅ |

### 2.2 拒绝优先（Deny Overrides Allow）

显式拒绝（`value=False`）的优先级**高于**通配符允许。

```
用户节点: {"luckperms.*": True, "luckperms.modify": False}

查询 "luckperms.modify":
    → 精确匹配 "luckperms.modify" → value=False → ❌ 拒绝
    → （即使 "luckperms.*" 匹配，也不继续检查，精确匹配已命中且为拒绝）

查询 "luckperms.user":
    → 精确匹配? 无
    → 通配符匹配 "luckperms.*" → value=True → ✅ 允许
```

### 2.3 父节点拒绝继承（Parent Deny Inheritance）

**父节点的显式拒绝必须继承到所有后代节点。**

```
用户节点: {"luckperms.*": True, "luckperms.modify": False}

查询 "luckperms.modify.create":
    → 精确匹配? 无
    → 检查父链: "luckperms.modify" 存在且 value=False
    → 父拒绝继承到后代 → ❌ 拒绝

查询 "luckperms.user.create":
    → 精确匹配? 无
    → 检查父链: "luckperms.user" 不存在，继续向上
    → "luckperms" 不存在
    → 通配符 "luckperms.*" 匹配 → ✅ 允许
```

**为什么父拒绝必须继承？**
- 安全原则：拒绝优先于允许
- 符合直觉：如果管理员说"你不能修改"，那"修改的创建"也应该被禁止
- 与原版 LuckPerms 行为一致

### 2.4 精确优先于通配（Exact > Wildcard）

精确匹配的优先级永远高于通配符匹配。即使通配符在逻辑上"范围更大"，精确节点拥有最终裁决权。

---

## 三、架构分层（必须按此分层实现）

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: NoneBot Integration (nonebot_adapter)             │
│  - PermissionChecker 工厂 (require/require_any/require_all) │
│  - IdentityResolver 协议与 OneBot V11 默认实现              │
│  - ContextVar 注入与提取 (get_context)                       │
│  - 内置管理命令 (/oblp ...)                                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Core Engine (luckperms_core)                      │
│  - User / Group / PermissionNode 模型                       │
│  - ContextSet / QueryOptions                                │
│  - PermissionEngine (节点解析、继承计算、通配符、前缀匹配)   │
│  - NodeRegistry (节点注册中心)                                │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Storage Abstraction (storage)                   │
│  - PermissionStore 协议                                     │
│  - MemoryStore (开发/测试)                                  │
│  - SQLiteStore (单实例默认)                                 │
│  - RedisStore (分布式可选)                                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Configuration & Plugin Bootstrap (config/plugin)│
│  - Pydantic 配置模型                                        │
│  - NoneBot 插件入口 (load / init)                           │
│  - 生命周期管理 (启动加载、关闭持久化)                       │
└─────────────────────────────────────────────────────────────┘
```

**关键约束**: Layer 3 (Core Engine) 必须**完全不依赖** NoneBot 或 OneBot。它是一个独立的权限引擎，可以被任何 Python 项目使用。只有 Layer 4 负责与 NoneBot 对接。

---

## 四、数据模型详细定义（必须精确实现）

### 4.1 ContextSet

```python
@dataclass(frozen=True)
class ContextSet:
    data: Dict[str, str] = field(default_factory=dict)
    
    def with_context(self, key: str, value: str) -> "ContextSet":
        """返回新的 ContextSet，添加/覆盖一个键值对"""
    
    def matches(self, requirement: "ContextSet") -> bool:
        """
        判定 self 是否满足 requirement。
        规则: requirement 中定义的所有键值对，self 中必须有且相等。
        例如:
            requirement = {group_id: "123"}
            self = {group_id: "123", role: "admin"}
            → True (self 包含了 requirement 的所有条件)
        """
    
    def is_empty(self) -> bool:
        """空 ContextSet 表示适用于所有环境"""
    
    @classmethod
    def from_dict(cls, d: Dict[str, str]) -> "ContextSet":
    
    def to_dict(self) -> Dict[str, str]:
```

### 4.2 PermissionNode

```python
@dataclass
class PermissionNode:
    key: str
    value: bool = True           # True=授予, False=显式拒绝
    expiry: Optional[int] = None # Unix 时间戳，None=永久
    contexts: ContextSet = field(default_factory=ContextSet)
    
    def is_expired(self) -> bool:
    
    def applies_in(self, ctx: ContextSet) -> bool:
        """判定该节点是否在给定上下文中生效"""
```

**重要**: `value=False` 是**显式拒绝**，不是"未定义"。未定义节点在引擎层面直接返回 `False`（默认拒绝）。

### 4.3 Group

```python
@dataclass
class Group:
    name: str                    # 唯一标识，如 "admin"
    display_name: Optional[str] = None
    weight: int = 0              # 权重，越高越优先
    nodes: List[PermissionNode] = field(default_factory=list)
    parents: List[str] = field(default_factory=list)  # 父组名列表
    
    async def get_effective_nodes(
        self, 
        store: "PermissionStore", 
        visited: Optional[Set[str]] = None
    ) -> List[PermissionNode]:
        """
        递归获取所有生效节点（自身 + 父组继承）。
        必须检测循环继承（A→B→A），遇到循环立即终止并抛出 CircularInheritanceError。
        """
```

### 4.4 User

```python
@dataclass
class User:
    user_id: str
    username: Optional[str] = None
    primary_group: Optional[str] = None
    groups: List[str] = field(default_factory=list)
    nodes: List[PermissionNode] = field(default_factory=list)
    
    async def get_effective_nodes(
        self,
        store: PermissionStore,
        options: QueryOptions,
    ) -> Set[str]:
        """
        核心算法:
        1. 收集自身 nodes
        2. 收集所有 groups 的 effective_nodes（递归继承）
        3. 按 weight 排序，高权重覆盖低权重冲突
        4. 按 QueryOptions.contexts 过滤
        5. 处理显式拒绝 (value=False): 如果高权重节点 value=False，则移除该 key
        6. 返回最终生效的 key 集合
        """
    
    async def has_permission(
        self,
        node_key: str,
        store: PermissionStore,
        options: QueryOptions,
    ) -> bool:
        """
        检查用户是否有特定节点。
        委托 PermissionEngine.check() 进行判定。
        """
```

---

## 五、权限解析引擎（PermissionEngine）

必须实现为一个无状态的工具类。核心方法必须体现完整的安全优先级：

```python
class PermissionEngine:
    @staticmethod
    def check(user_nodes: Dict[str, bool], target: str) -> bool:
        """
        权限判定算法（按严格优先级顺序）:
        
        1. 【精确匹配】target 在 user_nodes 中
           → 返回对应 value（True=允许, False=拒绝）
        
        2. 【父节点拒绝继承】从 target 向上追溯父节点
           例如 target="a.b.c"，检查 "a.b" → "a"
           如果某个父节点存在且 value=False，立即返回 False
           （安全原则：拒绝优先于允许，父拒绝继承到所有后代）
        
        3. 【通配符匹配】检查 user_nodes 中的通配符模式
           例如 "a.*" 匹配 "a.b", "a.b.c"
           返回对应 value
           注意: 如果通配符模式本身 value=False，同样拒绝
        
        4. 【前缀继承】检查 user_nodes 中的前缀
           例如用户拥有 "a.b"，查询 "a.b.c"
           如果 "a.b" value=True，返回 True
           如果 "a.b" value=False，已在步骤 2 拦截
        
        5. 【继承链】NodeRegistry 中 target 的 parent 链
           例如 target="myplugin.ban"，parent="myplugin.admin"
           如果用户拥有 "myplugin.admin"，返回其 value
        
        6. 【默认拒绝】无任何匹配 → 返回 False
        """
        
        # 阶段 1: 精确匹配（最高优先级）
        if target in user_nodes:
            return user_nodes[target]
        
        # 阶段 2: 父节点拒绝继承（安全关键）
        parts = target.split(".")
        for i in range(len(parts) - 1, 0, -1):
            parent = ".".join(parts[:i])
            if parent in user_nodes and not user_nodes[parent]:
                return False
        
        # 阶段 3: 通配符匹配
        import fnmatch
        for pattern, value in user_nodes.items():
            if "*" in pattern and fnmatch.fnmatch(target, pattern):
                return value
        
        # 阶段 4: 前缀继承（仅允许，拒绝已在阶段 2 处理）
        for node_key, value in user_nodes.items():
            if value and target.startswith(node_key + "."):
                return True
        
        # 阶段 5: 继承链
        for ancestor in NodeRegistry.get_ancestors(target):
            if ancestor in user_nodes:
                return user_nodes[ancestor]
        
        # 阶段 6: 默认拒绝
        return False
```

### 5.1 有效节点计算算法

```python
@staticmethod
async def resolve_effective_nodes(
    user: User,
    store: PermissionStore,
    options: QueryOptions,
) -> Dict[str, bool]:
    """
    计算用户在特定上下文下的有效权限字典 {key: value}。
    
    算法步骤:
    1. 收集候选节点: 用户自身节点 + 所有组的继承节点
    2. 按 (group.weight, 来源顺序) 排序，高权重优先
    3. 遍历候选节点:
       a. 过期检查: 跳过过期节点
       b. 上下文过滤: 如果 mode=contextual, 检查节点上下文是否匹配
       c. 冲突解决: 同一 key 只保留第一次遇到的（高权重优先）
       d. 显式拒绝处理: value=False 的节点标记为拒绝
    4. 在最终返回前，应用父节点拒绝继承规则
       遍历所有已允许的 key，如果其某个父 key 被显式拒绝，则移除
    5. 返回 {key: True} 的字典（只保留允许的，拒绝的不出现或显式标记）
    """
```

---

## 六、存储层协议（必须实现三种后端）

```python
from typing import Protocol, Optional, List

class PermissionStore(Protocol):
    # ---- User ----
    async def get_user(self, user_id: str) -> Optional[User]: ...
    async def save_user(self, user: User) -> None: ...
    async def delete_user(self, user_id: str) -> None: ...
    
    # ---- Group ----
    async def get_group(self, name: str) -> Optional[Group]: ...
    async def save_group(self, group: Group) -> None: ...
    async def delete_group(self, name: str) -> None: ...
    async def list_groups(self) -> List[str]: ...
    
    # ---- Node Registry (可选持久化) ----
    async def get_registered_nodes(self) -> List[PermissionNode]: ...
    async def save_registered_node(self, node: PermissionNode) -> None: ...
    
    # ---- 批量操作 ----
    async def load_all(self) -> None: ...      # 启动时加载
    async def save_all(self) -> None: ...      # 关闭时持久化 / 定时保存
```

### 6.1 MemoryStore

- 纯内存字典存储
- 启动时为空，关闭时丢失
- 适用于开发和测试

### 6.2 SQLiteStore（默认生产环境）

- 使用 `aiosqlite` 异步操作
- 表结构建议：
  - `users` (user_id, username, primary_group, groups_json, nodes_json)
  - `groups` (name, display_name, weight, parents_json, nodes_json)
  - `meta` (key, value) 用于存储注册节点等元数据
- 启动时自动建表
- 支持 `save_all()` 批量写入

### 6.3 RedisStore（分布式）

- 使用 `redis-py` 异步模式
- Key 设计：
  - `oblp:user:{user_id}` → Hash
  - `oblp:group:{name}` → Hash
  - `oblp:registry` → Set / Hash
- 支持 TTL（与 PermissionNode.expiry 联动）

---

## 七、NoneBot 集成层（Layer 4）

### 7.1 IdentityResolver 协议

```python
from typing import Protocol
from nonebot.adapters import Bot, Event

@dataclass
class Identity:
    user_id: str
    platform: str           # "onebot_v11", "onebot_v12", "console"...
    group_id: Optional[str]
    role: str               # "member", "admin", "owner", "superuser"
    extra: Dict[str, Any] = field(default_factory=dict)

class IdentityResolver(Protocol):
    async def resolve(self, bot: Bot, event: Event) -> Identity:
        ...
```

**默认实现: OneBotV11Resolver**

```python
class OneBotV11Resolver:
    async def resolve(self, bot, event):
        from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
        
        user_id = event.get_user_id()
        group_id = None
        role = "member"
        platform = "onebot_v11"
        
        if isinstance(event, GroupMessageEvent):
            group_id = str(event.group_id)
            if event.sender.role == "owner":
                role = "owner"
            elif event.sender.role == "admin":
                role = "admin"
        elif isinstance(event, PrivateMessageEvent):
            platform = "onebot_v11_private"
        
        # 超级用户判定（跨适配器通用）
        if user_id in getattr(bot.config, "superusers", set()):
            role = "superuser"
        
        return Identity(
            user_id=user_id,
            platform=platform,
            group_id=group_id,
            role=role,
            extra={"raw_event_name": event.get_event_name()}
        )
```

**注册方式**:
```python
# 在插件初始化时自动设置默认 Resolver
set_resolver(OneBotV11Resolver())
# 调用方可以覆盖: set_resolver(MyCustomResolver())
```

### 7.2 ContextVar 上下文注入

```python
import contextvars

# 协程级上下文槽，必须在 PermissionChecker 中 set，在 Handler 中 get
_lp_context: contextvars.ContextVar[Optional["LPContext"]] = contextvars.ContextVar(
    "oblp_context", default=None
)

def get_context() -> Optional["LPContext"]:
    """供 Handler 调用，获取 Permission 阶段注入的上下文"""
    return _lp_context.get()
```

### 7.3 LPContext 定义

```python
@dataclass(frozen=True)
class LPContext:
    user: User                      # 完整的用户对象
    identity: Identity              # 解析出的身份信息
    query_options: QueryOptions     # 本次查询使用的选项
    resolved_nodes: Dict[str, bool] # 本次解析出的有效权限字典
    matched_node: Optional[str]     # 本次通过检查的具体节点（用于审计）
    timestamp: float                # 解析时间戳
```

### 7.4 Permission 工厂函数（核心 API）

```python
from nonebot.permission import Permission

def require(node_key: str, contexts: Optional[ContextSet] = None) -> Permission:
    """
    生成 NoneBot Permission 对象。
    内部逻辑:
    1. 创建 PermissionChecker 异步函数
    2. Checker 接收 (bot, event)，调用 IdentityResolver 解析身份
    3. 构建 QueryOptions（合并 Checker 传入的 contexts 和 event 自动解析的 contexts）
    4. 从 Store 获取 User，调用 PermissionEngine.check()
    5. 如果通过，构建 LPContext 并注入 ContextVar
    6. 返回 True/False
    """
    
def require_any(*node_keys: str, contexts: Optional[ContextSet] = None) -> Permission:
    """逻辑或：拥有任意一个节点即通过"""
    
def require_all(*node_keys: str, contexts: Optional[ContextSet] = None) -> Permission:
    """逻辑与：必须拥有所有节点才通过"""
```

**关键约束**:
- `require()` 返回的 `Permission` 对象必须可以直接传给 `on_command(permission=...)` 或 `on_message(permission=...)`
- Checker 内部必须处理 `event` 不是 OneBot 事件的情况（优雅降级，返回 False 或根据配置决定）

---

## 八、节点注册中心（NodeRegistry）

```python
class NodeRegistry:
    _nodes: Dict[str, PermissionNode] = {}
    
    @classmethod
    def register(
        cls,
        key: str,
        description: str = "",
        default: bool = False,
        contexts: Optional[ContextSet] = None,
    ):
        """
        注册一个权限节点。
        - 幂等：重复注册相同 key 不报错（不同插件可能声明相同节点）
        - 如果 key 已存在但参数不同，打印 warning 并保留第一次注册
        """
    
    @classmethod
    def get(cls, key: str) -> Optional[PermissionNode]: ...
    
    @classmethod
    def list_all(cls) -> List[PermissionNode]: ...
    
    @classmethod
    def get_ancestors(cls, key: str) -> List[str]:
        """返回节点的 parent 继承链（基于注册时的层级关系，通过 key 的层级推断）"""
        # 例如 "myplugin.admin.ban" 的祖先: ["myplugin.admin", "myplugin"]
```

**对外暴露的便捷函数**:
```python
def register_node(
    key: str,
    description: str = "",
    default: bool = False,
    contexts: Optional[ContextSet] = None,
):
    """供业务插件在加载时调用"""
    NodeRegistry.register(key, description, default, contexts)
```

---

## 九、管理命令（内置）

使用 `on_command("oblp", aliases={"luckperms"}, permission=SUPERUSER)` 注册。

### 9.1 用户管理

```
/oblp user <user_id> info
  → 显示用户基本信息、所属组、有效节点列表

/oblp user <user_id> node <node_key> [true|false] [context_key=context_value ...]
  → 给用户添加/移除特定节点
  → 示例: /oblp user 123456 node myplugin.ban true group_id=123456

/oblp user <user_id> group add <group_name>
/oblp user <user_id> group remove <group_name>
/oblp user <user_id> group setprimary <group_name>
```

### 9.2 组管理

```
/oblp group create <name> [weight]
/oblp group delete <name>
/oblp group info <name>
/oblp group parent <name> add <parent_name>
/oblp group parent <name> remove <parent_name>
/oblp group <name> node <node_key> [true|false] [contexts...]
```

### 9.3 节点管理

```
/oblp node list
  → 列出所有已注册的节点

/oblp node info <node_key>
  → 显示节点描述、默认值、上下文约束

/oblp reload
  → 热重载配置和缓存
```

### 9.4 查询与调试

```
/oblp check <user_id> <node_key> [context_key=value ...]
  → 模拟查询某用户在特定上下文下是否有某节点
  → 输出详细的判定过程（用于调试继承和上下文匹配）
```

---

## 十、配置系统（Pydantic）

```python
from pydantic import BaseSettings, Field

class OBLPConfig(BaseSettings):
    class Config:
        env_prefix = "OBLP_"
        extra = "ignore"
    
    # 存储配置
    store_type: Literal["memory", "sqlite", "redis"] = "sqlite"
    sqlite_path: str = "./data/oblp/permissions.db"
    redis_url: str = "redis://localhost:6379/0"
    
    # 默认权限映射（群角色自动继承的节点）
    default_group_owner: List[str] = Field(default_factory=lambda: ["*"])
    default_group_admin: List[str] = Field(default_factory=list)
    default_group_member: List[str] = Field(default_factory=list)
    
    # 超级用户设置
    superuser_inherit: List[str] = Field(default_factory=lambda: ["*"])
    
    # 缓存设置
    cache_ttl: int = 300  # 秒，0 表示不缓存
    
    # 调试
    debug_mode: bool = False  # 开启后打印每次权限判定详情

# NoneBot 配置加载方式
oblp_config = OBLPConfig()
```

---

## 十一、与业务插件的集成示例（必须保证调用方极简）

### 11.1 极简用法（只拦人，不看上下文）

```python
# plugins/my_plugin/__init__.py
from nonebot import on_command
from nonebot_plugin_onebot_luckperms import register_node, require

# 插件加载时注册节点（幂等）
register_node("myplugin.ban", "禁言成员", default=False)

# 注册命令，绑定权限
ban = on_command("ban", permission=require("myplugin.ban"))

@ban.handle()
async def _():
    # 能走到这里 = 权限已通过
    await ban.send("已执行禁言")
```

### 11.2 进阶用法（在 Handler 中读取权限上下文）

```python
from nonebot_plugin_onebot_luckperms import get_context

@ban.handle()
async def _():
    ctx = get_context()
    if not ctx:
        return  # 理论上不会发生
    
    # 读取完整的 LuckPerms 风格上下文
    print(ctx.user.user_id)           # "123456"
    print(ctx.user.primary_group)     # "admin"
    print(ctx.identity.role)          # "admin"
    print(ctx.identity.group_id)      # "987654"
    print(ctx.resolved_nodes)         # {"myplugin.ban": True, "admin.*": True}
    
    if ctx.identity.role == "owner":
        await ban.send("群主执行禁言")
    else:
        await ban.send("管理员执行禁言")
```

### 11.3 组合权限

```python
from nonebot_plugin_onebot_luckperms import require, require_any, require_all
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN

# 节点权限 OR 原生权限
cmd = on_command("cmd", permission=require("myplugin.cmd") | GROUP_ADMIN)

# 多节点 OR
cmd2 = on_command("cmd2", permission=require_any("node.a", "node.b"))

# 多节点 AND
cmd3 = on_command("cmd3", permission=require_all("node.a", "node.b"))
```

---

## 十二、实现步骤与里程碑

### Phase 1: 核心引擎（不依赖 NoneBot）

1. 实现 `ContextSet`、`PermissionNode`、`Group`、`User` 数据模型
2. 实现 `PermissionEngine`（节点解析、继承计算、通配符匹配、父拒绝继承）
3. 实现 `NodeRegistry`
4. 实现 `MemoryStore` 和 `SQLiteStore`
5. 编写核心引擎的单元测试（覆盖率 > 80%）

### Phase 2: NoneBot 集成层

6. 实现 `IdentityResolver` 协议和 `OneBotV11Resolver`
7. 实现 `require` / `require_any` / `require_all` 工厂函数
8. 实现 `ContextVar` 注入与 `get_context()` 提取
9. 实现内置管理命令（`/oblp ...`）
10. 实现 Pydantic 配置系统

### Phase 3: 高级功能

11. 实现 `RedisStore`
12. 实现缓存层（基于 TTL 的节点解析缓存）
13. 实现节点过期自动清理
14. 支持 OneBot V12 适配器（新增 Resolver）

### Phase 4: 文档与发布

15. 编写 README（含安装、配置、API 文档）
16. 编写示例插件
17. 发布到 PyPI

---

## 十三、代码规范与约束

### 13.1 依赖管理

**必须依赖**:
- `nonebot2>=2.0.0`
- `pydantic>=1.10` (或 v2，统一即可)
- `typing-extensions`

**按存储后端可选依赖**:
- `aiosqlite` (sqlite)
- `redis` (redis)

**禁止依赖**:
- 不要在核心引擎层依赖 `nonebot` 或 `nonebot-adapter-onebot`。核心引擎必须是纯 Python，可被独立测试。

### 13.2 异步约束

- 所有 Store 操作必须是 `async`
- `PermissionEngine` 可以是同步的（纯计算），但 `User.get_effective_nodes()` 必须是 `async`（因为涉及 Store 查询）
- `IdentityResolver.resolve()` 必须是 `async`

### 13.3 错误处理

- 循环继承检测：发现时抛出 `CircularInheritanceError`，管理命令中捕获并提示
- 存储查询失败：打印 error log，降级为 `MemoryStore` 或返回空结果（根据配置）
- 节点解析异常：返回 `False`（拒绝访问），并记录 debug log

### 13.4 日志规范

使用 `nonebot.logger` 或标准 `logging`：

```
[oblp] INFO: User 123456 resolved 15 effective nodes in context {group_id: 789, role: admin}
[oblp] DEBUG: Checking node "myplugin.ban" for user 123456 -> True (matched via direct key)
[oblp] WARNING: Circular inheritance detected in group "admin" -> "mod" -> "admin"
```

---

## 十四、测试要求

### 14.1 单元测试（核心引擎）

必须覆盖：
- `ContextSet.matches()` 的各种边界情况
- `PermissionEngine.check()` 的完整优先级链（精确匹配、父拒绝继承、通配符、前缀继承、继承链、默认拒绝）
- `User.get_effective_nodes()` 的组继承、权重覆盖、显式拒绝
- `Group.get_effective_nodes()` 的递归继承与循环检测

### 14.2 边界测试用例（必须全部通过）

```python
# 测试用例 1: 未定义节点 = 拒绝
assert check({}, "any.node") == False

# 测试用例 2: 精确允许
assert check({"a.b": True}, "a.b") == True

# 测试用例 3: 精确拒绝
assert check({"a.b": False}, "a.b") == False

# 测试用例 4: 父拒绝继承到子节点（关键安全测试）
assert check({"a.*": True, "a.b": False}, "a.b.c") == False

# 测试用例 5: 通配符允许，但精确拒绝覆盖
assert check({"a.*": True, "a.b": False}, "a.b") == False

# 测试用例 6: 通配符允许子节点（父未拒绝）
assert check({"a.*": True}, "a.b.c") == True

# 测试用例 7: 前缀继承
assert check({"a.b": True}, "a.b.c") == True

# 测试用例 8: 前缀拒绝（父拒绝继承）
assert check({"a.b": False}, "a.b.c") == False

# 测试用例 9: 权重覆盖（Group 高权重拒绝覆盖低权重允许）
# 用户组 A(weight=10): {"node": True}
# 用户组 B(weight=20): {"node": False}
# 结果: False（高权重优先）

# 测试用例 10: 显式拒绝优先于通配允许
assert check({"*": True, "specific": False}, "specific") == False

# 测试用例 11: 空 ContextSet 匹配所有环境
ctx = ContextSet()
assert ctx.matches(ContextSet({"group_id": "123"})) == True

# 测试用例 12: 上下文不匹配 = 节点不生效
# 节点绑定 contexts={group_id: "123"}，当前环境 {group_id: "456"}
# 结果: 节点不生效，视为未定义 -> 拒绝
```

### 14.3 集成测试（NoneBot 层）

使用 `nonebug` 或 `pytest-asyncio` 模拟 NoneBot 事件：
- 模拟群消息事件，测试 `require()` 是否正确拦截/放行
- 测试 `get_context()` 在 Handler 中能否正确读取
- 测试管理命令的交互

### 14.4 性能测试

- 模拟 1000 个用户、100 个组、每个组 5 层继承，测试单次权限判定耗时
- 目标：单次判定 < 5ms（含缓存时 < 1ms）

---

## 十五、交付物清单

下游 Agent 完成项目后，必须包含：

1. `pyproject.toml`（NoneBot 插件入口、依赖、元数据）
2. `nonebot_plugin_onebot_luckperms/` 完整源码（按 Layer 1-4 分层）
3. `tests/` 单元测试 + 集成测试
4. `README.md`（安装、配置、API 使用文档）
5. `examples/` 示例插件（展示如何集成）
6. `.env.example` 配置文件示例

---

## 十六、最终提醒

本项目的设计核心是让业务插件开发者**只写一行 `permission=require("node.key")`**，其余全部内部消化。任何让调用方需要手动传 Event、手动查数据库、手动写权限判断逻辑的设计，都是失败的。

**务必保证**:
- 接口极简性
- 上下文系统的完备性
- 安全边界的严格性（默认拒绝、拒绝优先、父拒绝继承）
- 核心引擎的独立性（不依赖 NoneBot）