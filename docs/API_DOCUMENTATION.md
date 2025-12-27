# SciTool 平台 API 文档

**版本**: v1.0
**生成日期**: 2025-12-25
**基础URL**: `http://localhost:8000/api/v1`

---

## 📋 目录

1. [概述](#概述)
2. [认证方式](#认证方式)
3. [通用响应格式](#通用响应格式)
4. [错误码说明](#错误码说明)
5. [API接口](#api接口)
   - [认证模块 (Auth)](#认证模块-auth)
   - [验证码模块 (Verification)](#验证码模块-verification)
   - [用户管理模块 (Users)](#用户管理模块-users)
   - [工具管理模块 (Tools)](#工具管理模块-tools)
   - [任务管理模块 (Tasks)](#任务管理模块-tasks)
   - [文件管理模块 (Files)](#文件管理模块-files)
   - [系统管理模块 (System)](#系统管理模块-system)
   - [WebSocket接口](#websocket接口)

---

## 概述

SciTool 是一个科学工具平台，提供工具管理、任务执行、文件处理等功能。本文档描述了平台的所有API接口。

### 技术栈

- **框架**: FastAPI
- **认证**: JWT (Bearer Token)
- **数据格式**: JSON
- **文件上传**: multipart/form-data

---

## 认证方式

### Bearer Token 认证

大部分API需要在请求头中携带JWT令牌：

```http
Authorization: Bearer <access_token>
```

### 获取令牌

通过登录接口获取：`POST /api/v1/auth/login`

### 令牌刷新

通过刷新接口更新：`POST /api/v1/auth/refresh`

---

## 通用响应格式

### 成功响应

```json
{
  "code": 200,
  "message": "操作成功",
  "data": { ... }
}
```

### 错误响应

```json
{
  "code": 400,
  "message": "错误描述",
  "data": null
}
```

---

## 错误码说明

| 错误码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未认证或令牌无效 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 500 | 服务器内部错误 |

---

## API接口


### 认证模块 (Auth)

基础路径：`/api/v1/auth`

#### 1. 用户注册

**接口**: `POST 


`

**描述**: 注册新用户账号

**权限**: 无需认证

**请求参数**:
```json
{
  "email": "user@example.com",
  "password": "password123",
  "display_name": "用户名",
  "verification_code": "123456"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | 是 | 邮箱地址 |
| password | string | 是 | 密码（6-100位） |
| display_name | string | 否 | 显示名称 |
| verification_code | string | 是 | 邮箱验证码（6位） |

**响应示例**:
```json
{
  "code": 200,
  "message": "注册成功",
  "data": {
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "display_name": "用户名",
      "role": "user",
      "status": "active"
    },
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "token_type": "bearer"
  }
}
```

---

#### 2. 用户登录

**接口**: `POST /auth/login`

**描述**: 用户登录获取令牌

**权限**: 无需认证

**请求参数**:
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | 是 | 邮箱地址 |
| password | string | 是 | 密码 |

**响应示例**:
```json
{
  "code": 200,
  "message": "登录成功",
  "data": {
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "display_name": "用户名",
      "role": "user",
      "status": "active"
    },
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "token_type": "bearer"
  }
}
```

---

#### 3. 重置密码

**接口**: `POST /auth/reset-password`

**描述**: 通过验证码重置密码

**权限**: 无需认证

**请求参数**:
```json
{
  "email": "user@example.com",
  "code": "123456",
  "new_password": "newpassword123"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | 是 | 邮箱地址 |
| code | string | 是 | 验证码 |
| new_password | string | 是 | 新密码 |

**响应示例**:
```json
{
  "code": 200,
  "message": "密码重置成功",
  "data": null
}
```

---

#### 4. 刷新令牌

**接口**: `POST /auth/refresh`

**描述**: 使用refresh_token刷新access_token

**权限**: 无需认证

**请求参数**:
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| refresh_token | string | 是 | 刷新令牌 |

**响应示例**:
```json
{
  "code": 200,
  "message": "令牌刷新成功",
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "token_type": "bearer"
  }
}
```

---

#### 5. 获取当前用户信息

**接口**: `GET /auth/me`

**描述**: 获取当前登录用户的详细信息

**权限**: 需要认证

**请求头**:
```http
Authorization: Bearer <access_token>
```

**响应示例**:
```json
{
  "code": 200,
  "message": "成功",
  "data": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "用户名",
    "avatar_url": null,
    "role": "user",
    "status": "active",
    "created_at": "2025-12-25T00:00:00Z",
    "updated_at": "2025-12-25T00:00:00Z"
  }
}
```

---

#### 6. 更新当前用户信息

**接口**: `PUT /auth/me`

**描述**: 更新当前登录用户的信息

**权限**: 需要认证

**请求头**:
```http
Authorization: Bearer <access_token>
```

**请求参数**:
```json
{
  "display_name": "新用户名",
  "avatar_url": "https://example.com/avatar.jpg"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| display_name | string | 否 | 显示名称 |
| avatar_url | string | 否 | 头像URL |

**响应示例**:
```json
{
  "code": 200,
  "message": "更新成功",
  "data": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "新用户名",
    "avatar_url": "https://example.com/avatar.jpg",
    "role": "user",
    "status": "active"
  }
}
```

---

#### 7. 修改密码

**接口**: `POST /auth/change-password`

**描述**: 修改当前用户的密码（需要提供旧密码）

**权限**: 需要认证

**请求头**:
```http
Authorization: Bearer <access_token>
```

**请求参数**:
```json
{
  "old_password": "oldpassword123",
  "new_password": "newpassword123"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| old_password | string | 是 | 旧密码 |
| new_password | string | 是 | 新密码（6-50位） |

**响应示例**:
```json
{
  "code": 200,
  "message": "密码修改成功",
  "data": null
}
```

---

#### 8. 登出

**接口**: `POST /auth/logout`

**描述**: 用户登出（客户端清除令牌即可）

**权限**: 需要认证

**请求头**:
```http
Authorization: Bearer <access_token>
```

**响应示例**:
```json
{
  "code": 200,
  "message": "登出成功",
  "data": null
}
```

---


### 验证码模块 (Verification)

基础路径：`/api/v1/verification`

| 接口 | 方法 | 描述 | 权限 | 关键参数 |
|------|------|------|------|----------|
| `/send-code` | POST | 发送验证码 | 无需认证 | email, purpose (register/reset_password) |
| `/verify` | POST | 验证验证码 | 无需认证 | email, code, purpose |

**发送验证码示例**:
```json
POST /verification/send-code
{
  "email": "user@example.com",
  "purpose": "register"
}
```

**验证验证码示例**:
```json
POST /verification/verify
{
  "email": "user@example.com",
  "code": "123456",
  "purpose": "register"
}
```

---


### 用户管理模块 (Users)

基础路径：`/api/v1/users`

#### 当前用户操作

| 接口 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/me` | GET | 获取当前用户信息 | 需要认证 |
| `/me` | PATCH | 更新当前用户信息 | 需要认证 |
| `/me/change-password` | POST | 修改密码 | 需要认证 |

#### 管理员操作

| 接口 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/admin/users` | GET | 获取用户列表 | 管理员 |
| `/admin/users/{user_id}` | GET | 获取用户详情 | 管理员 |
| `/admin/users/{user_id}` | PATCH | 更新用户信息 | 管理员 |
| `/admin/users/{user_id}` | DELETE | 删除用户 | 管理员 |
| `/admin/stats` | GET | 获取用户统计 | 管理员 |

---

### 工具管理模块 (Tools)

基础路径：`/api/v1/tools`

#### 工具基础操作

| 接口 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/` | GET | 获取工具列表 | 可选认证 |
| `/my` | GET | 获取我的工具 | 需要认证 |
| `/{tool_id}` | GET | 获取工具详情 | 可选认证 |
| `/` | POST | 创建工具 | 需要认证 |
| `/{tool_id}` | PUT | 更新工具 | 需要认证 |
| `/{tool_id}` | DELETE | 删除工具 | 需要认证 |

**查询参数**（GET /）:
- `page`, `page_size`: 分页
- `category`: 分类筛选
- `tag`: 标签筛选
- `search`: 关键词搜索
- `provider_type`: 工具来源（platform/user）
- `view`: 视图类型（public/my/favorites）

#### 工具发布和审核

| 接口 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/{tool_id}/publish` | POST | 发布工具 | 需要认证 |
| `/{tool_id}/submit-review` | POST | 提交审核 | 需要认证 |

#### 工具收藏

| 接口 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/{tool_id}/favorite` | POST | 收藏工具 | 需要认证 |
| `/{tool_id}/favorite` | DELETE | 取消收藏 | 需要认证 |

#### 版本管理

| 接口 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/{tool_id}/versions` | GET | 获取版本列表 | 无需认证 |
| `/{tool_id}/versions` | POST | 创建版本 | 需要认证 |

#### 标签和分类

| 接口 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/categories` | GET | 获取分类列表 | 无需认证 |
| `/tags` | GET | 获取标签列表 | 无需认证 |
| `/tags` | POST | 创建标签 | 管理员 |

#### 管理员操作

| 接口 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/admin/{tool_id}/review` | POST | 审核工具 | 管理员 |
| `/admin/{tool_id}/set-platform` | POST | 设置为平台工具 | 管理员 |
| `/admin/pending-reviews` | GET | 获取待审核列表 | 管理员 |

---


### 任务管理模块 (Tasks)

基础路径：`/api/v1/tasks`

| 接口 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/` | GET | 获取任务列表 | 需要认证 |
| `/{task_id}` | GET | 获取任务详情 | 需要认证 |
| `/` | POST | 创建任务 | 需要认证 |
| `/{task_id}/cancel` | POST | 取消任务 | 需要认证 |
| `/{task_id}/retry` | POST | 重试任务 | 需要认证 |
| `/{task_id}/logs` | GET | 获取任务日志 | 需要认证 |
| `/{task_id}` | DELETE | 删除任务 | 管理员 |

**创建任务参数**:
```json
{
  "tool_id": "uuid",
  "tool_version_id": "uuid",
  "params": {},
  "file_ids": [],
  "priority": "normal"
}
```

**查询参数**（GET /）:
- `page`, `page_size`: 分页
- `status`: 状态筛选（pending/running/success/failure/canceled）
- `tool_id`: 工具筛选

---

### 文件管理模块 (Files)

基础路径：`/api/v1/files`

| 接口 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/upload` | POST | 上传文件 | 需要认证 |
| `/` | GET | 获取文件列表 | 需要认证 |
| `/{file_id}` | GET | 获取文件信息 | 需要认证 |
| `/{file_id}/download` | GET | 下载文件 | 需要认证 |
| `/{file_id}/download-url` | GET | 获取下载URL | 需要认证 |
| `/{file_id}` | DELETE | 删除文件 | 需要认证 |
| `/batch-delete` | POST | 批量删除文件 | 需要认证 |

**上传文件**:
```http
POST /files/upload
Content-Type: multipart/form-data

file: <binary>
is_public: false
expires_hours: 24
```

**查询参数**（GET /）:
- `page`, `page_size`: 分页
- `source_type`: 来源类型筛选

---


### 系统管理模块 (System)

基础路径：`/api/v1/system`

| 接口 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/health` | GET | 系统健康检查 | 无需认证 |
| `/stats` | GET | 系统统计信息 | 管理员 |
| `/queue-status` | GET | 队列状态 | 管理员 |
| `/config` | GET | 获取系统配置 | 管理员 |

**健康检查响应**:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "celery": "running"
}
```

---

## 附录

### 数据模型

#### 用户角色
- `user`: 普通用户
- `vip`: VIP用户
- `admin`: 管理员

#### 用户状态
- `active`: 活跃
- `inactive`: 未激活
- `banned`: 已封禁

#### 工具状态
- `draft`: 草稿
- `published`: 已发布
- `disabled`: 已禁用

#### 工具审核状态
- `not_required`: 无需审核（平台工具）
- `pending`: 待审核
- `approved`: 已通过
- `rejected`: 已拒绝

#### 任务状态
- `pending`: 等待中
- `running`: 运行中
- `success`: 成功
- `failure`: 失败
- `canceled`: 已取消

### 分页响应格式

所有列表接口统一使用以下分页格式：

```json
{
  "code": 200,
  "message": "成功",
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20,
    "total_pages": 5
  }
}
```

### 前端开发建议

1. **认证流程**：
   - 登录后保存 `access_token` 和 `refresh_token`
   - 在所有需要认证的请求中携带 `Authorization: Bearer <access_token>`
   - Token过期时使用 `refresh_token` 刷新

2. **错误处理**：
   - 统一处理 401 错误（跳转登录）
   - 统一处理 403 错误（权限不足提示）
   - 统一处理 500 错误（服务器错误提示）

3. **文件上传**：
   - 使用 `multipart/form-data` 格式
   - 注意文件大小限制
   - 显示上传进度

4. **任务执行**：
   - 创建任务后轮询任务状态
   - 或使用 WebSocket 接收实时更新
   - 显示任务进度和日志

5. **工具管理**：
   - 创建工具时可以同时提供 `initial_version`
   - 注意工具的审核状态和发布状态
   - 区分平台工具和用户工具

---

## 更新日志

### v1.0 (2025-12-25)
- 初始版本
- 包含所有核心模块的API文档
- 修复了核心功能的4个问题

---

**文档生成时间**: 2025-12-25  
**维护者**: SciTool 开发团队  
**联系方式**: support@scitool.com

