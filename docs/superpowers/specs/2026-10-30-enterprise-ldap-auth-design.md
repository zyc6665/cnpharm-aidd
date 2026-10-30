# 企业内部账号制认证（用户名 + 本地/LDAP 双模）设计

- 日期：2026-10-30
- 状态：**已实现**（2026-10-30；实现见 `docs/18` §3.26，计划见 `plans/2026-10-30-enterprise-ldap-auth.md`）
- 关联：`docs/03` §9/§14、`docs/04` §5.0、`docs/05` §2、`docs/03B` D-04 / D-04-01 / Q-04、`docs/18` §6.3 G-8

## 1. 为什么做（intent）

平台是**甲方内网私有化部署的企业系统**，不是面向公众的产品。甲方明确：

- **不使用 email 登录**，登录标识是账号名（username）。
- **不提供自助注册**，账号只能由管理员在后台创建/停用。
- 需要一个**企业目录（LDAP/AD）认证**能力；但甲方 LDAP 目前**尚未提供**，因此该能力必须**可配置、默认关闭**，服务器地址/BaseDN/属性映射等留待 `Q-04` 给出后填入。

当前代码与文档存在冲突（已向负责人报告）：`docs/04 §5.0` 设计的是 `sys_user`（username 登录、`auth_source`、`ldap_dn`、口令可空），但实际 `backend/app/models/users.py` 的 `users` 表是 **email 登录、口令 NOT NULL、无认证源字段**，且 `POST /api/v1/auth/register` 仍开放注册。本设计以“**扩展现有 `users` 表**”落地，不重建为 `sys_user`。

## 2. 目标（goals）

1. 登录改为 **账号名 + 口令**；email 降级为可选联系方式，不参与认证。
2. **关闭自助注册**；账号只能由管理员创建。
3. 支持 **双模认证**：`auth_source = LOCAL`（平台 bcrypt 口令）或 `LDAP`（目录服务 bind 校验，平台不存口令）；默认 `LOCAL`。
4. LDAP 连接参数全部走配置，**未配置时不影响本地登录**。
5. 管理员创建用户时可选认证源、填账号名；LDAP 用户不可被管理员重置本地口令（返回 `40002`），也不强制首次改密。

## 3. 非目标（non-goals）

- 不做 LDAP 组/OU → 平台角色的自动映射（一期由管理员手工指定角色）。
- 不做 OIDC / SAML / SSO 单点登录。
- 不做自助注册、邮箱找回、邮箱验证码登录。
- 不做 refresh token 状态化（`D-04-01` 维持无状态 JWT + Redis 黑名单）。
- 不做 LDAP 用户自动开户（首次登录自动建号）——账号仍由管理员预先创建。

## 4. 反目标（anti-goals，即“技术上能跑也算失败”）

- 任何路径仍然允许 email 作为登录凭证，或注册接口仍可用。
- LDAP 口令被写入 `users` 表或日志。
- 关闭 LDAP 配置时，本地登录出现任何行为变化或报错。
- 认证失败时泄露“账号是否存在”（对外统一错误）。

## 5. 硬约束（constraints）

- 迁移必须**单 head**，不得与未提交分支开叉；SQLite 与 PostgreSQL 都要能 `upgrade/downgrade`。
- 不改动 `docs/04` 既有 `sys_user` 章节的语义；本设计是**代码侧向文档靠拢的最小实现**，差异记录在实现说明。
- 无公网依赖：`ldap3` 必须来自离线可用包（本机已装 2.9.1，需 pin 进 `backend/requirements.txt`）。
- 口令哈希沿用现有 `app.auth.password`（bcrypt/Argon2 现状），不引入新哈希库。
- 错误码沿用 `docs/05`：参数非法 `40002`、未认证 `40101`。

## 6. 已定的实现口径（decisions，负责人已确认）

### 6.1 数据模型（`users` 表扩展）

新增列（Alembic 一版迁移）：

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `username` | varchar(64) | 非空；`UNIQUE (lower(username))` 函数索引 | 登录名，管理员设定 |
| `auth_source` | varchar(16) | 非空，默认 `LOCAL`；CHECK ∈ {`LOCAL`,`LDAP`} | 认证源 |
| `ldap_dn` | text | 可空；`UNIQUE (ldap_dn) WHERE ldap_dn IS NOT NULL` | 登录成功回填 |

修改列：

- `email`：改为**可空**、**去掉 unique 约束**（保留普通索引用于查询/联系）。
- `password_hash`：改为**可空**（`auth_source=LDAP` 时为 NULL）。

回填：存量行 `username` 用其 email 的 `@` 前缀（冲突时追加 `_<id 前 8 位>`），`auth_source='LOCAL'`。迁移需幂等、`downgrade` 对称删列并恢复约束（回填值不可逆，注释说明）。

### 6.2 API

- `POST /api/v1/auth/login`：请求体 `{username, password}`（替换 `email`）。逻辑：
  1. 按 `lower(username)` 查用户；不存在/状态非 ACTIVE → 统一 `40101`（不暴露存在性）。
  2. `auth_source=LOCAL`：`verify_password(password, password_hash)`。
  3. `auth_source=LDAP`：调用 `LdapAuthenticator.authenticate(username, password)`；成功则回填 `ldap_dn`、更新 `last_login_at`；失败统一 `40101`；LDAP 未启用时该用户登录失败并记审计原因“LDAP 未启用”。
  4. 成功后签发 access/refresh（复用现有 `jwt_handler`），写审计。
- `POST /api/v1/auth/register`：**移除**（路由删除，返回 404/405；前端同步移除入口）。
- `POST /api/v1/users`（管理员创建用户）：入参改为 `{username, display_name?, email?, role, auth_source, password?}`；`auth_source=LOCAL` 时 `password` 必填，`LDAP` 时忽略口令。
- `POST /api/v1/users/{id}:reset-password`：`auth_source=LDAP` 用户返回 `40002`。
- `POST /api/v1/auth/change-password`、`PUT /api/v1/users/me`：LDAP 用户改密返回 `40002`；email 改为可空。

### 6.3 配置（`Settings`）

新增，均有默认值且 `LDAP_ENABLED=False` 时完全不触发：

```
LDAP_ENABLED: bool = False
LDAP_SERVER_URI: str = ""          # ldap://host:389 或 ldaps://host:636
LDAP_START_TLS: bool = False
LDAP_BASE_DN: str = ""
LDAP_USER_FILTER: str = "(uid={username})"   # 可配属性
LDAP_ATTR_UID: str = "uid"
LDAP_ATTR_MAIL: str = "mail"
LDAP_ATTR_DISPLAY_NAME: str = "cn"
LDAP_BIND_DN: str = ""             # 服务账号（可空=匿名/直连用户 DN）
LDAP_BIND_PASSWORD: str = ""
LDAP_TIMEOUT_SECONDS: float = 5.0
```

### 6.4 适配器接口

`backend/app/auth/ldap_provider.py`：

```python
class LdapAuthResult(BaseModel):
    dn: str
    username: str
    email: str | None = None
    display_name: str | None = None

class LdapAuthenticator(Protocol):
    def authenticate(self, username: str, password: str) -> LdapAuthResult | None: ...

class Ldap3Authenticator:
    def __init__(self, settings: Settings) -> None: ...
    def authenticate(self, username: str, password: str) -> LdapAuthResult | None: ...

def get_ldap_authenticator() -> LdapAuthenticator | None:
    """LDAP_ENABLED=False 时返回 None。测试可 override。"""
```

行为：先用服务账号（若配置）在 `BASE_DN` 下按 `LDAP_USER_FILTER` 搜到唯一条目，再用该条目的 DN + 用户口令做第二次 bind 验证；空口令直接拒绝；连接/超时/无条目一律返回 `None` 并记 WARNING（不记口令）。

### 6.5 前端

- 登录页 `frontend/src/views/auth/Login.vue`（或等价）：字段 `email` → `username`，文案“账号 / 口令”，移除“注册”链接。
- 若有注册页/路由：移除。
- 用户管理页创建用户表单：加“账号名”“认证源（本地/LDAP）”选择；选 LDAP 时隐藏口令输入。
- i18n `zh-CN`/`en` 同步。

## 7. 测试策略

- **不依赖真实 LDAP**：`get_ldap_authenticator` 用依赖覆盖注入 `FakeAuthenticator`（内存字典）。
- 覆盖：①本地登录成功/失败；②LDAP 登录成功回填 `ldap_dn`；③LDAP 禁用时 LDAP 用户登录失败且本地用户不受影响；④注册接口已不可用；⑤账号名大小写不敏感唯一；⑥LDAP 用户重置/改密返回 `40002`；⑦管理员创建 LDAP 用户不存口令。
- 迁移：SQLite 与（可用时）真 PG 的 `upgrade/downgrade` + 存量回填断言。

## 8. 交给实现者自由决定的

- 具体 LDAP 搜索过滤器的转义实现、连接重试细节。
- 前端表单的具体组件拆分与样式，只要满足 6.5 的字段与行为。
- 审计日志的具体 reason 文案（中文），只要区分“用户不存在/口令错误/LDAP 未启用/LDAP 校验失败”。

## 9. 开放项

- 甲方 LDAP 服务器地址、BaseDN、属性映射（`Q-04`）——到位后只改配置，不改代码。
- `D-04` 是否强制 LDAP 单点——若最终强制，只需把 `auth_source` 默认与登录分支策略改为拒绝 LOCAL（配置开关即可）。
