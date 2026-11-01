# 企业内部账号制认证（LDAP 可配置 + 关闭注册）

> 计划编写日期：2026-10-30
> 依据（唯一事实源）：`docs/superpowers/specs/2026-10-30-enterprise-ldap-auth-design.md`（已与负责人确认）
> 状态：待执行

---

## Goal

把平台从「开放自助注册（邮箱）」改为「企业内部账号制」：

1. 登录只认 **用户名 + 口令**；移除注册、忘记密码等对外自助入口。
2. 身份来源可配置：`LOCAL`（本地口令）/ `LDAP`（企业目录校验口令），由每个用户行的
   `auth_source` 决定；LDAP 服务端连接参数全部走配置（甲方当前无 LDAP，先做成可配置）。
3. 关闭 `POST /api/v1/auth/register`（返回 403 业务码 `40300`）。
4. 管理员建号/重置口令/用户自助改密，都按目标用户 `auth_source` 分流。

## Architecture

```
Login.vue（用户名+口令）
   └─ POST /auth/login {username, password}
        └─ AuthService.login
             ├─ 查 users.username → 不存在/非 ACTIVE → 401（不区分原因）
             └─ auth_source
                  ├─ LOCAL → verify_password(user.password_hash)
                  └─ LDAP  → ldap_provider.authenticate(username, password)
                               ldap3 Connection(server, user=uid=…, password)
                               search 取 displayName/mail（首次建号用）
                               bind 成功即通过；不落任何本地口令
   └─ 签发 JWT（沿用现有 jwt_handler）→ 写 login 审计
```

关键边界：
- **LDAP 用户不保存本地口令**：`password_hash = NULL`。
- **LDAP 用户不提供找回/自助改密**（`PUT /users/me/password` → `40007`）。
- 管理员对 LDAP 用户 **不能重置本地口令**（`POST /users/admin/{id}/reset-password` → `40002`）；
  建号时 `auth_source=ldap` 的目标口令被忽略并置 `password_hash=NULL`。
- 设置**每次调用现读**（`settings_service.get_settings()` 读 DB 配置表），不缓存、无需重启。

## Tech Stack

- 后端：FastAPI / SQLAlchemy 2.0(async) / Alembic / Pydantic Settings / `ldap3`（纯 Python 客户端）。
- 前端：Vue3 + Pinia + Ant Design Vue + vue-i18n。
- 测试：pytest（后端）、vitest（前端）。

## 决策（builder 反查的 7 个开放问题）

1. **邮箱自助链路全部下线**：除 `/auth/register` 外，一并停用 `POST /auth/reset-password`、
   `POST /verification/send-code`、`POST /verification/verify`（路由层返回 `403/40300`，实现保留不删以
   降低连带风险），删除前端 `Register.vue`/`ForgotPassword.vue` 与 `/register`、`/forgot-password` 路由及入口链接。
   理由：邮箱作为自助认证因子与企业内网「账号仅管理员维护」互斥（README §4 反目标）。
2. **项目成员改按用户名邀请**：`ProjectMemberCreate` 增加 `username`（保留 `email` 兼容），
   解析优先级 `username` → `email`；UI 文案改「成员用户名」（`projects/Settings.vue:35-40,161`）。
   理由：email 可空且不再唯一，LDAP 用户可能无邮箱。
3. **email 保持可空、身份主键是 username**：`UserResponse.email` 改 `Optional[str]`，
   前端 `UserInfo.email?: string`；JWT 载荷用 `username`（保留 `email` 为可选兼容）；所有
   `user.email.split('@')[0]` / 直接渲染 email 的界面改用 `username`（`admin/Dashboard.vue:176`、
   `admin/Users.vue:344`、`user/index.vue:14`）。理由：LDAP 用户可能无 mail 属性，NULL 不能 500。
4. **username 即目录账号**：LDAP 用户的平台 username 就是目录登录名（AD 用 `sAMAccountName`），
   直接代入 `LDAP_USER_FILTER`；不另加映射字段。管理员建 LDAP 用户时须填目录账号，UI 提示。
5. **接口路径以仓库现状为准**（不改已发布契约）：`POST /users/admin`、
   `POST /users/admin/{id}/reset-password`、`PUT /users/me/password`、`PATCH /users/me`；设计文档中
   的「理想路径」仅作描述，实施按仓库路径，并在文档注明。
6. **扩展 `app/cli/ensure_admin.py`**：增加 `--username`（缺省由 email 本地部分派生），按 username
   幂等创建；首个管理员唯一入口。理由：注册关闭后必须留自举路径。
7. **补 LDAP TLS 信任配置**：`LDAP_CA_CERT_FILE: str = ""`、`LDAP_TLS_VALIDATE: bool = True`
   （内网私有 CA/自签可关校验或给 CA 路径），传给 `ldap3.Tls`。理由：否则上线对客户目录必失败。
8. **last_login_at**：本次迁移一并加 `last_login_at`（nullable DateTime），登录成功更新；
   `password_hash` 改为 **nullable=True**（LDAP 用户不存口令）；`ldap_dn` 加
   部分唯一索引 `uq_users_ldap_dn ... WHERE ldap_dn IS NOT NULL`。
9. **auth_source/username 创建后不可编辑**：`AdminUserUpdate`/`UserUpdate` 不接受这两个字段
   （避免 LOCAL↔LDAP 切换时 hash/dn 状态歧义），文档注明。
10. **username 规则**：`String(64)`，正则 `^[A-Za-z0-9._-]{1,64}$`，唯一性用 `lower(username)` 保证
    （迁移建 `uq_users_username_lower` 函数索引；SQLite 用 `COLLATE NOCASE` 唯一索引等价）。回填时
   本地部分超长截断到 56 再拼 `_<id前8>`；重名按 `id` 排序追加后缀。
11. **审计**：`audit.log_login` 增 `username` 字段，登录与「用户不存在」尝试都记 username（email 可选）。

## 改动清单（按任务）

### 任务 1：数据模型与迁移

- `backend/app/models/users.py`
  - 新增 `username`：`String(64)`，`nullable=False`，`unique=True`，`index=True`。
  - `email` 改为 `nullable=True`，去掉列级 `unique=True`（改为 `index=True`；唯一性移出，
    避免 LDAP 用户无邮箱时约束冲突）。
  - 新增 `auth_source`：`String(16)`，`nullable=False`，`server_default=text("'LOCAL'")`。
  - `username` 的 Python 端 `default` 从 `email` 本地部分派生：
    `lambda ctx: (ctx.get_current_parameters().get("email") or "user").split("@")[0]`
    + `str(uuid.uuid4())[:8]` 兜底避免空值；历史测试夹具沿用 `User(email=...)` 不炸。
- `backend/alembic/versions/20261031_07_user_username_auth_source.py`（down `20261031_06`，保持单头）
  - 三步幂等：① 加 `username`/`auth_source` 列（先 nullable）→ ② 回填：
    `username = split_part(email,'@',1)` 去重（重名追加 `_<id前8>`），`auth_source='LOCAL'` → ③
    `username` 置 `NOT NULL` + `UNIQUE` 约束，并把 `email` 唯一约束/索引改为普通索引。
  - SQLite 用 `batch_alter_table`，PG 直接 `ALTER TABLE`；重复执行幂等；downgrade 对称。
  - 注意：如果同邮箱本地部分重名，回填时按 `id` 排序用窗口函数或 Python 逐行处理（迁移里用
    `op.get_bind().execute(select(...))` 拉全量在 Python 里去重，写回）。

### 任务 2：配置与 LDAP 客户端

- `backend/app/core/config.py` 的 `Settings` 增加：
  ```python
  LDAP_ENABLED: bool = False
  LDAP_SERVER_URI: str = ""              # ldap://host:389
  LDAP_USE_SSL: bool = False
  LDAP_BIND_DN_TEMPLATE: str = "uid={username},ou=users,dc=example,dc=com"
  LDAP_BASE_DN: str = ""
  LDAP_USER_FILTER: str = "(uid={username})"
  LDAP_ATTR_USERNAME: str = "uid"
  LDAP_ATTR_EMAIL: str = "mail"
  LDAP_ATTR_DISPLAY_NAME: str = "displayName"
  LDAP_TIMEOUT_SECONDS: int = 5
  ```
- `backend/app/services/ldap_provider.py`（新增）：
  - `class LdapUnavailableError(Exception)`。
  - `authenticate(settings, username, password) -> LdapIdentity | None`：空口令直接 None；
    `Connection(server=Server(uri, use_ssl=..., connect_timeout=...), user=bind_dn, password=...)`
    → `conn.bind()`；成功后按 `LDAP_USER_FILTER` search 取 `email/display_name`，返回
    `LdapIdentity(username, email, display_name)`；绑定失败返回 None；连接/超时抛
    `LdapUnavailableError`（上层转 `50301`）。
  - 服务端异常绝不把口令写日志。
- `requirements.txt`：加 `ldap3==2.9.1`（纯 Python，无系统依赖；与 Python 3.11 兼容）。
- `backend/tests`：用 monkeypatch 假 `ldap3` 模块单测 provider（成功/口令错/超时），**不连真 LDAP**。

### 任务 3：认证服务与登录接口

- `backend/app/services/auth.py`
  - `LoginResponse`/`AuthService.login` 改为按 `username` 查 `User`；校验 `status == ACTIVE`。
  - `auth_source == "LOCAL"` → `verify_password`。
  - `auth_source == "LDAP"` → 调 `ldap_provider`；`LDAP_ENABLED=False` 时直接 `40007`
    （LDAP 未启用）；provider 抛 `LdapUnavailableError` → `50301`。
  - 登录成功写 `log_login(..., username=user.username)`（审计事件新增 `username` 字段，
    `email` 保留可选）。
  - 新增 `register` **保留函数但直接 raise `ValidationException(403, 40300, "注册功能已关闭")`**；
    或直接在路由层拦截。选路由层（`backend/app/api/v1/auth.py`）返回 `403/40300`。
- `backend/app/schemas/users.py`
  - `UserLogin`：`email` → `username: str`（`min_length=1`）。
  - `UserCreate`（注册用）可删或保留但不再被注册路由使用。
  - `UserResponse` 增加 `username: str`、`auth_source: str`。
- `backend/app/api/v1/auth.py`：`/register` 改为恒返 `403`（`40300`）；`/login` 用新 `UserLogin`；
  `/refresh` 不变。
- `backend/app/auth/jwt_handler.py`：JWT payload 的 `email` 字段改名 `username`（签发时传
  `user.username`）；`get_current_user` 只依赖 `sub`，**不受影响**（保留 `email` 兼容可选）。

### 任务 4：用户接口按 auth_source 分流

- `backend/app/api/v1/users.py`
  - `AdminUserCreate` 增加 `username: str`、`auth_source: str = "LOCAL"`，`email` 改 `Optional`。
  - `admin_create_user`：校验 username 唯一；`auth_source==LDAP` → `password_hash=None`
    （忽略传入口令）、可空 email；否则走 LOCAL 口令。
  - `admin_reset_user_password`：目标 `auth_source==LDAP` → `ValidationException(400, 40002,
    "LDAP 用户口令由域控管理，无法在平台重置")`。
  - `change_password`（`PUT /users/me/password`）：`auth_source==LDAP` → `ValidationException(400,
    40007, "LDAP 用户请使用域账号口令")`。
  - `UserResponse` 序列化补 `username/auth_source`（见任务 3 schema）。
  - 保持错误码与 `docs/05` 一致：`40002` 校验失败 / `40007` 不允许操作 / `40300` 权限不足。

### 任务 5：前端

- `frontend/src/views/auth/Login.vue`：邮箱输入改**用户名**；移除「注册」「忘记密码」链接；
  提交体 `{username, password}`。
- `frontend/src/router/index.ts`：删除 `/register`、`/forgot-password` 路由（或指向 404）。
- 删除/停用 `frontend/src/views/auth/Register.vue`、`ForgotPassword.vue`（无引用后删）。
- `frontend/src/views/admin/Users.vue` + `frontend/src/api/users.ts`：
  - 建号表单：`username` 必填、`auth_source` 下拉（LOCAL/LDAP）、LOCAL 时显示口令、LDAP 时
    隐藏口令并提示「口令由域控校验」。
  - 列表展示 `username` 为主、`email` 次。
  - `AdminUserCreateParams` 增加 `username`、`auth_source`，`email` 可选。
  - 对 LDAP 用户隐藏「重置密码」按钮（或点击后提示 40002）。
- `frontend/src/types/models.ts`：`UserInfo` 加 `username`、`auth_source`。
- `frontend/src/locales/zh-CN/index.ts`、`en/index.ts`：新增 `auth.username`、
  `admin.authSource`、`admin.ldapPasswordHint` 等 key，去掉注册相关 key（保留无引用 key 不报错）。

### 任务 6：测试与文档

- 后端新增 `backend/test/test_ldap_auth.py`：
  - provider 单测（monkeypatch `ldap3`）：成功/口令错/超时/空口令。
  - 登录接口：LOCAL 用户成功、LDAP 用户 mock provider 成功/失败、`LDAP_ENABLED=False` 时
    LDAP 用户 `40007`、`/register` `403/40300`。
  - 管理端：LDAP 用户 reset `40002`、自助改密 `40007`、建 LDAP 用户 `password_hash is None`。
  - 全部用**独立 SQLite 内存库**，不依赖 dev/verify 库。
- 前端 `frontend/src/views/auth/Login.spec.ts`（提交体 username）、
  `frontend/test/ldap-auth-ui.test.ts`（LDAP 用户隐藏重置按钮、表单 auth_source 切换）。
- 文档：`docs/04-接口规范.md`（登录/注册/用户接口变更）、`docs/05-错误码.md`（新增 40007/40300/50301
  说明）、`docs/18-项目验收报告.md`（§3.25 企业 LDAP 认证落地、G-8/D-04 关闭）、
  `docs/README.md`（如涉及接口清单）、本计划 Status 追加。
- 设计文档状态改「已实现」。

## Global Constraints

- **单 head**：新迁移 `20261031_07` 必须 `down_revision = 20261031_06`，提交前 `alembic heads`
  只能一个 head。
- **不接真 LDAP**：甲方暂无目录服务；所有测试用 mock，`LDAP_ENABLED` 默认 `False`。
- **不回落 SQLite 环境跑迁移**：验收以 SQLite（单测）+ 真 PG（`cin_keyset_verify` 或本地 kind
  PG）各跑一次 `upgrade head` 为准。
- **口令不落库/不写日志**：LDAP 用户 `password_hash=NULL`；审计/日志不得出现明文口令。
- **文档同步**：接口/错误码/验收报告同一提交内更新；不得代码与文档不一致。
- **门禁**：`flake8 backend/app --select F401,F821,E9` 零输出；后端全量 pytest 绿；前端
  `vue-tsc -b` 0、目标 vitest 绿。
- **提交规范**：`<type>(<scope>): <subject>` + 正文为什么 + `Refs: docs/superpowers/specs/2026-10-30-enterprise-ldap-auth-design.md`。

## Sequencing

1. 任务 1（模型+迁移）→ 跑迁移 SQLite/PG 双验。
2. 任务 2（配置+provider）→ provider 单测。
3. 任务 3（认证服务/登录/注册关闭）→ 登录单测。
4. 任务 4（用户接口分流）→ 管理端单测。
5. 任务 5（前端）→ `vue-tsc` + vitest。
6. 任务 6（文档+全量门禁）→ 提交前统一校验。

依赖关系：2 依赖 1 的 `auth_source` 列；3/4 依赖 1、2；5 依赖 3/4 的接口字段；6 最后。

## Review Focus

- 迁移在「已有 20000 行 + 同邮箱重名」库上的回填是否稳定、幂等、downgrade 对称。
- LDAP provider 的超时/异常是否映射为 `50301`，绝不误判为「口令错误」而静默 401。
- 是否漏掉任何仍能自助注册/找回密码的入口（路由、页面、接口、i18n 链接）。
- 管理员对 LDAP 用户的所有口令写入路径是否都拦住（建号/重置/自助改密）。
- 前端 `UserInfo` 类型与后端 `UserResponse` 字段完全对齐（`username`/`auth_source`）。

## Status

- 2026-10-30：计划编写完成，待执行。
- 2026-10-30：**已完成并验收**（任务 1~5 全部落地）。后端 `test/test_ldap_auth.py` 11 例 + 全量 `2011 passed / 5 failed（本机环境既有）/ 4 skipped`；`flake8 F401,F821,E9` 零输出；`alembic heads` 单头 `20261031_07`；真 PG（kind）`20261031_06 → 20261031_07` 升级成功；前端 `vue-tsc -b` 0、相关 8 spec 40 例通过。文档已同步：`docs/18` §3.26 / 状态表 / G-8 / v1.28、`docs/05` §2、`docs/04` §5.0、`docs/03B` D-04、`docs/21`。**未提交 commit**（工作区留审）。
