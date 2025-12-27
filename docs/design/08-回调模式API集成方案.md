# 回调模式API集成方案

## 1. 概述

### 1.1 背景

当前平台支持标准的RESTful API模式，工具API直接返回结果。但部分工具（如旧版SciMiner工具）使用回调模式：
- 工具API立即返回 `code: 20001`，表示任务已接收
- 工具在后台执行完成后，通过HTTP POST回调平台接口更新任务状态

### 1.2 目标

设计并实现回调模式API支持，使平台能够兼容两种模式：
1. **标准模式**：工具API直接返回结果（当前已支持）
2. **回调模式**：工具API返回20001，后台完成后回调平台（待实现）

### 1.3 设计原则

- **向后兼容**：不影响现有标准模式工具
- **最小侵入**：尽量复用现有代码结构
- **安全可靠**：回调接口需要认证和防重放
- **易于配置**：通过工具配置指定使用哪种模式
- **幂等性**：回调接口支持重复调用，防止重复处理

### 1.4 与现有架构的集成点

本方案与以下现有组件集成：

| 组件 | 文件位置 | 集成方式 |
|------|----------|----------|
| 任务执行器 | `backend/app/tasks/executor.py` | 扩展 `RemoteAPIExecutor` |
| 状态机 | `backend/app/tasks/state_machine.py` | 复用 `TaskStateMachine` |
| Worker | `backend/app/worker/tasks.py` | 添加回调超时检查任务 |
| 任务API | `backend/app/api/v1/tasks.py` | 添加回调接口 |
| WebSocket | `backend/app/websocket/manager.py` | 复用现有通知机制 |

---

## 2. 架构设计

### 2.1 整体流程

```
┌─────────────┐
│   用户请求   │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  平台API接口    │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│  Celery Worker  │
└──────┬──────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  RemoteAPIExecutor                  │
│  - 注入回调URL和任务ID到请求头      │
│  - 调用工具API                      │
└──────┬──────────────────────────────┘
       │
       ├─────────────┬─────────────────┐
       │             │                 │
       ▼             ▼                 ▼
  ┌─────────┐  ┌──────────┐    ┌──────────┐
  │标准模式 │  │回调模式  │    │错误处理  │
  │直接返回 │  │返回20001 │    │          │
  └────┬────┘  └────┬─────┘    └────┬─────┘
       │            │               │
       │            │               │
       ▼            ▼               ▼
  ┌─────────────────────────────────┐
  │  更新任务状态到数据库            │
  └─────────────────────────────────┘
       │
       │ (回调模式)
       ▼
  ┌─────────────────────────────────┐
  │  工具后台执行                    │
  │  - 处理任务                      │
  │  - 完成后调用回调接口            │
  └──────┬──────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────┐
  │  平台回调接口                    │
  │  POST /api/v1/tasks/callback    │
  │  - 验证签名                      │
  │  - 更新任务状态                  │
  │  - 保存结果                      │
  └─────────────────────────────────┘
```

### 2.2 核心组件

#### 2.2.1 回调接口（新增）
- **路径**: `POST /api/v1/tasks/{task_id}/callback`
- **功能**: 接收工具的回调请求，更新任务状态和结果
- **认证**: 基于签名的认证机制

#### 2.2.2 RemoteAPIExecutor（改造）
- 检测工具配置中的 `callback_mode` 标志
- 注入回调相关的请求头
- 处理 `code: 20001` 响应

#### 2.2.3 工具配置（扩展）
- 添加 `callback_mode` 字段
- 添加 `callback_timeout` 字段

---

## 3. 详细设计

### 3.1 数据模型变更

#### 3.1.1 工具配置扩展

在 `tool_versions.config` JSON字段中添加（与现有 `ToolVersion.config` 结构兼容）：

```json
{
  "type": "remote_api",
  "endpoint": "http://tool-service:8000/api/process",
  "method": "POST",
  "timeout_sec": 600,
  "headers": {},

  // 新增回调模式字段
  "callback_mode": true,              // 是否使用回调模式，默认 false
  "callback_timeout_sec": 3600,       // 回调超时时间（秒），默认 3600
  "callback_secret": "auto-generated" // 回调签名密钥（创建工具时自动生成）
}
```

**callback_secret 自动生成逻辑**：

```python
# backend/app/services/tool_service.py
import secrets

def generate_callback_secret() -> str:
    """生成32字节的安全随机密钥"""
    return secrets.token_hex(32)

def ensure_callback_secret(config: dict) -> dict:
    """确保回调模式工具有密钥"""
    if config.get("callback_mode") and not config.get("callback_secret"):
        config["callback_secret"] = generate_callback_secret()
    return config
```

#### 3.1.2 任务状态扩展

**方案A（推荐）**：使用现有 `extra_data` JSON 字段存储回调元数据，无需修改数据库结构：

```python
# 在 Task.extra_data JSON 字段中存储
{
  "callback_mode": true,
  "callback_url": "http://platform:8000/api/v1/tasks/{task_id}/callback",
  "callback_sent_at": "2025-12-24T09:00:00Z",      # 发送回调请求的时间
  "callback_received_at": "2025-12-24T10:00:00Z", # 收到回调的时间
  "callback_attempts": 0                           # 回调重试次数（工具端）
}
```

**任务状态流转**（复用现有 `TaskStatus` 枚举，无需新增状态）：

```
标准模式：PENDING -> RUNNING -> SUCCESS/FAILURE
回调模式：PENDING -> RUNNING (等待回调) -> SUCCESS/FAILURE (回调更新)
```

> 注意：回调模式下，任务在 `RUNNING` 状态等待回调，通过 `extra_data.callback_mode` 区分是否为回调等待状态。


### 3.2 回调接口设计

#### 3.2.1 接口定义

**端点**: `POST /api/v1/tasks/{task_id}/callback`

**请求头**:
```
Content-Type: application/json
X-Callback-Signature: <HMAC-SHA256签名>
X-Callback-Timestamp: <Unix时间戳>
X-Callback-Nonce: <随机字符串，用于防重放>
```

**请求体**:
```json
{
  "task_id": "uuid",
  "status": "SUCCESS|FAILURE",
  "result": {
    "data": "任务结果数据（任意JSON结构）",
    "output_files": [
      {
        "name": "result.txt",
        "url": "http://tool-service/files/result.txt",
        "size": 1024,
        "content_type": "text/plain"
      }
    ]
  },
  "error": {
    "code": 1001,
    "message": "错误信息"
  },
  "metadata": {
    "execution_time_sec": 120,
    "custom_field": "value"
  }
}
```

**响应**:
```json
// 成功
{
  "code": 0,
  "message": "Callback received",
  "data": {
    "task_id": "uuid",
    "status": "SUCCESS",
    "received_at": "2025-12-24T10:00:00Z"
  }
}

// 重复回调（幂等处理）
{
  "code": 0,
  "message": "Callback already processed",
  "data": {
    "task_id": "uuid",
    "status": "SUCCESS",
    "first_received_at": "2025-12-24T10:00:00Z"
  }
}

// 错误
{
  "code": 40001,
  "message": "Invalid signature",
  "data": null
}
```

#### 3.2.2 签名机制

**签名生成**（工具端）:
```python
import hmac
import hashlib
import time
import secrets

def generate_callback_signature(
    task_id: str,
    body: str,
    secret: str,
    nonce: str = None
) -> tuple[str, str, str]:
    """
    生成回调签名

    Args:
        task_id: 任务ID
        body: 请求体JSON字符串
        secret: 回调密钥
        nonce: 随机字符串（可选，自动生成）

    Returns:
        (signature, timestamp, nonce)
    """
    timestamp = str(int(time.time()))
    nonce = nonce or secrets.token_hex(16)

    # 签名消息格式：task_id:timestamp:nonce:body
    message = f"{task_id}:{timestamp}:{nonce}:{body}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    return signature, timestamp, nonce
```

**签名验证**（平台端）:
```python
# backend/app/utils/callback_signature.py

import hmac
import hashlib
import time
from typing import Optional
from app.cache import cache_manager

# 签名有效期（秒）
SIGNATURE_VALIDITY_SECONDS = 300  # 5分钟

# Nonce缓存过期时间（秒）
NONCE_CACHE_TTL = 600  # 10分钟

async def verify_callback_signature(
    task_id: str,
    body: str,
    signature: str,
    timestamp: str,
    nonce: str,
    secret: str
) -> tuple[bool, Optional[str]]:
    """
    验证回调签名

    Args:
        task_id: 任务ID
        body: 请求体原始字符串
        signature: 签名
        timestamp: 时间戳
        nonce: 随机字符串
        secret: 回调密钥

    Returns:
        (is_valid, error_message)
    """
    # 1. 检查时间戳（防重放攻击）
    try:
        request_time = int(timestamp)
        current_time = int(time.time())
        if abs(current_time - request_time) > SIGNATURE_VALIDITY_SECONDS:
            return False, "Signature expired"
    except ValueError:
        return False, "Invalid timestamp format"

    # 2. 检查 nonce 是否已使用（防重放攻击）
    nonce_key = f"callback_nonce:{task_id}:{nonce}"
    if await cache_manager.exists(nonce_key):
        return False, "Nonce already used (replay attack detected)"

    # 3. 验证签名
    message = f"{task_id}:{timestamp}:{nonce}:{body}"
    expected_signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return False, "Invalid signature"

    # 4. 记录 nonce（防止重放）
    await cache_manager.set(nonce_key, "1", ttl=NONCE_CACHE_TTL)

    return True, None
```


### 3.3 RemoteAPIExecutor 改造

基于现有 `backend/app/tasks/executor.py` 中的 `RemoteAPIExecutor` 类进行扩展。

#### 3.3.1 扩展执行器类

```python
# backend/app/tasks/executor.py（扩展现有 RemoteAPIExecutor）

import os
from datetime import datetime
from typing import Dict, Any, Optional

class RemoteAPIExecutor(BaseExecutor):
    """远程API执行器（支持回调模式）"""

    def __init__(self, task: "Task", tool_version: "ToolVersion"):
        super().__init__(task, tool_version)
        # 回调模式配置
        self.callback_mode = self.config.get("callback_mode", False)
        self.callback_timeout_sec = self.config.get("callback_timeout_sec", 3600)
        self.callback_secret = self.config.get("callback_secret")

    async def execute(self) -> Dict[str, Any]:
        """执行远程API调用"""
        endpoint = self.config.get("endpoint")
        if not endpoint:
            raise TaskExecutionError("Missing endpoint in tool config")

        method = self.config.get("method", "POST").upper()
        timeout = self.config.get("timeout_sec", 600)

        # 准备请求数据和头部
        request_data = await self._prepare_request_data()
        headers = await self._prepare_headers()

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                logger.info(f"Executing remote API: {method} {endpoint}")
                logger.debug(f"Callback mode: {self.callback_mode}")

                if method == "POST":
                    response = await client.post(
                        endpoint,
                        json=request_data,
                        headers=headers
                    )
                elif method == "GET":
                    response = await client.get(
                        endpoint,
                        params=self._flatten_params(request_data),
                        headers=headers
                    )
                else:
                    raise TaskExecutionError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                result = response.json()

                # 检查是否为回调模式响应
                if self.callback_mode and result.get("code") == 20001:
                    return await self._handle_callback_response(result)

                # 标准模式：直接处理结果
                return await self._handle_standard_response(result)

            except httpx.HTTPStatusError as e:
                raise TaskExecutionError(
                    f"API returned error: {e.response.status_code}",
                    details={"response_text": e.response.text[:500]}
                )
            except httpx.TimeoutException:
                raise TaskExecutionError("API request timeout")
            except httpx.ConnectError as e:
                raise TaskExecutionError(f"Failed to connect to API: {str(e)}")

    async def _prepare_headers(self) -> Dict[str, str]:
        """准备请求头（包含回调信息）"""
        headers = self.config.get("headers", {}).copy()

        if self.callback_mode:
            # 构建回调URL
            platform_url = os.getenv("PLATFORM_BASE_URL", "http://localhost:8000")
            callback_url = f"{platform_url}/api/v1/tasks/{self.task.id}/callback"

            # 注入回调相关头部（与旧版 SciMiner 兼容）
            headers.update({
                "X-SCIMINER-CONSOLE-API-URL": platform_url,
                "X-SCIMINER-TASK-ID": str(self.task.id),
                "X-SCIMINER-TASK-TYPE": self.tool_version.tool.slug if self.tool_version.tool else "",
                "X-SCIMINER-CALLBACK-URL": callback_url,
                "X-SCIMINER-CALLBACK-SECRET": self.callback_secret or ""
            })

            logger.info(f"Injected callback headers for task {self.task.id}")

        return headers

    async def _handle_callback_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """处理回调模式响应（code: 20001）"""
        logger.info(f"Task {self.task.id} accepted by tool, waiting for callback")

        # 更新任务元数据
        platform_url = os.getenv("PLATFORM_BASE_URL", "http://localhost:8000")
        callback_url = f"{platform_url}/api/v1/tasks/{self.task.id}/callback"

        # 返回回调等待状态（由 Worker 层更新 extra_data）
        return {
            "status": "callback_pending",
            "message": result.get("message", "Task accepted, waiting for callback"),
            "callback_mode": True,
            "callback_url": callback_url,
            "callback_timeout_sec": self.callback_timeout_sec,
            "callback_sent_at": datetime.utcnow().isoformat()
        }

    async def _handle_standard_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """处理标准模式响应"""
        # 处理输出文件
        if "output_files" in result:
            uploaded_files = await self._process_output_files(result["output_files"])
            result["output_file_ids"] = uploaded_files

        return {
            "success": True,
            "result": result
        }
```

#### 3.3.2 Worker 层回调状态处理

```python
# backend/app/worker/tasks.py（扩展 _execute_tool_task_impl）

async def _execute_tool_task_impl(task_id: str, tool_version_id: str) -> Dict[str, Any]:
    """任务执行实现（支持回调模式）"""
    # ... 现有代码 ...

    try:
        # 执行任务
        output_result = await executor.execute()

        # ========== 新增：检查是否为回调模式 ==========
        if output_result.get("status") == "callback_pending":
            # 回调模式：更新任务元数据，保持 RUNNING 状态
            task.extra_data = task.extra_data or {}
            task.extra_data.update({
                "callback_mode": True,
                "callback_url": output_result.get("callback_url"),
                "callback_timeout_sec": output_result.get("callback_timeout_sec"),
                "callback_sent_at": output_result.get("callback_sent_at")
            })
            task.progress_message = "任务已提交，等待工具回调"

            # 添加日志
            log = TaskLog(
                task_id=task_id,
                level="INFO",
                message="任务已提交到工具服务，等待回调"
            )
            db.add(log)
            await db.commit()

            # WebSocket 通知
            await notify_task_progress(task_id, 10, "任务已提交，等待工具回调")
            await notify_task_log(task_id, "INFO", "任务已提交到工具服务，等待回调")

            logger.info(f"Task {task_id} is waiting for callback")

            # 返回回调等待状态（不创建 TaskOutput）
            return output_result

        # 标准模式：继续现有逻辑
        # ... 现有代码 ...
```


### 3.4 回调接口实现

#### 3.4.1 Schema 定义

```python
# backend/app/schemas/tasks.py（新增）

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CallbackOutputFile(BaseModel):
    """回调输出文件"""
    name: str = Field(..., description="文件名")
    url: str = Field(..., description="文件下载URL")
    size: Optional[int] = Field(None, description="文件大小（字节）")
    content_type: Optional[str] = Field(None, description="MIME类型")


class CallbackResult(BaseModel):
    """回调结果数据"""
    data: Optional[Any] = Field(None, description="结果数据（任意JSON结构）")
    output_files: Optional[List[CallbackOutputFile]] = Field(
        default_factory=list,
        description="输出文件列表"
    )


class CallbackError(BaseModel):
    """回调错误信息"""
    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误信息")


class TaskCallbackRequest(BaseModel):
    """任务回调请求"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., pattern="^(SUCCESS|FAILURE)$", description="任务状态")
    result: Optional[CallbackResult] = Field(None, description="任务结果（成功时）")
    error: Optional[CallbackError] = Field(None, description="错误信息（失败时）")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "SUCCESS",
                "result": {
                    "data": {"processed": True, "count": 100},
                    "output_files": [
                        {
                            "name": "result.csv",
                            "url": "http://tool-service/files/result.csv",
                            "size": 1024,
                            "content_type": "text/csv"
                        }
                    ]
                },
                "metadata": {
                    "execution_time_sec": 120
                }
            }
        }


class TaskCallbackResponse(BaseModel):
    """任务回调响应"""
    task_id: str
    status: str
    received_at: str
    first_received_at: Optional[str] = None  # 幂等处理时返回
```

#### 3.4.2 API路由定义

```python
# backend/app/api/v1/tasks.py（新增回调接口）

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime
import logging

from app.database.session import get_db
from app.models.tasks import Task, TaskStatus, TaskOutput, TaskLog
from app.models.tools import ToolVersion
from app.schemas.tasks import TaskCallbackRequest, TaskCallbackResponse
from app.common.responses import success_response, error_response
from app.common.exceptions import NotFoundException, ValidationException
from app.utils.callback_signature import verify_callback_signature
from app.worker.tasks import notify_task_status, notify_task_complete, notify_task_error, notify_task_log

logger = logging.getLogger(__name__)


@router.post("/{task_id}/callback", response_model=dict)
async def task_callback(
    task_id: str,
    request: Request,
    callback_data: TaskCallbackRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    接收工具的回调请求

    此接口无需用户认证，使用签名机制验证请求合法性。

    Args:
        task_id: 任务ID
        callback_data: 回调数据
        db: 数据库会话

    Returns:
        回调处理结果
    """
    # 1. 获取请求头
    signature = request.headers.get("X-Callback-Signature")
    timestamp = request.headers.get("X-Callback-Timestamp")
    nonce = request.headers.get("X-Callback-Nonce")

    if not all([signature, timestamp, nonce]):
        logger.warning(f"Callback missing headers for task {task_id}")
        return error_response(
            code=40001,
            message="Missing required headers: X-Callback-Signature, X-Callback-Timestamp, X-Callback-Nonce"
        )

    # 2. 验证 task_id 一致性
    if callback_data.task_id != task_id:
        logger.warning(f"Callback task_id mismatch: URL={task_id}, body={callback_data.task_id}")
        return error_response(code=40002, message="Task ID mismatch")

    # 3. 查询任务
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.tool_version))
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        logger.warning(f"Callback for non-existent task: {task_id}")
        raise NotFoundException(f"Task {task_id} not found")

    # 4. 检查是否为回调模式任务
    if not task.extra_data or not task.extra_data.get("callback_mode"):
        logger.warning(f"Callback for non-callback-mode task: {task_id}")
        return error_response(code=40003, message="Task is not in callback mode")

    # 5. 幂等性检查：如果任务已完成，返回之前的结果
    if task.status in [TaskStatus.SUCCESS.value, TaskStatus.FAILURE.value]:
        first_received_at = task.extra_data.get("callback_received_at")
        logger.info(f"Callback already processed for task {task_id}")
        return success_response(
            message="Callback already processed",
            data=TaskCallbackResponse(
                task_id=task_id,
                status=task.status,
                received_at=datetime.utcnow().isoformat(),
                first_received_at=first_received_at
            ).model_dump()
        )

    # 6. 获取回调密钥
    tool_version = task.tool_version
    if not tool_version:
        result = await db.execute(
            select(ToolVersion).where(ToolVersion.id == task.tool_version_id)
        )
        tool_version = result.scalar_one()

    callback_secret = tool_version.config.get("callback_secret")
    if not callback_secret:
        logger.error(f"Callback secret not configured for tool version {tool_version.id}")
        return error_response(code=50001, message="Callback secret not configured")

    # 7. 验证签名
    body = await request.body()
    is_valid, error_msg = await verify_callback_signature(
        task_id=task_id,
        body=body.decode(),
        signature=signature,
        timestamp=timestamp,
        nonce=nonce,
        secret=callback_secret
    )

    if not is_valid:
        logger.warning(f"Callback signature verification failed for task {task_id}: {error_msg}")
        return error_response(code=40101, message=f"Signature verification failed: {error_msg}")

    # 8. 处理回调数据
    try:
        await _process_callback(task, callback_data, db)
        logger.info(f"Callback processed successfully for task {task_id}")

        return success_response(
            message="Callback received",
            data=TaskCallbackResponse(
                task_id=task_id,
                status=task.status,
                received_at=datetime.utcnow().isoformat()
            ).model_dump()
        )

    except Exception as e:
        logger.exception(f"Failed to process callback for task {task_id}: {e}")
        return error_response(code=50002, message=f"Failed to process callback: {str(e)}")


async def _process_callback(
    task: Task,
    callback_data: TaskCallbackRequest,
    db: AsyncSession
):
    """
    处理回调数据，更新任务状态

    Args:
        task: 任务对象
        callback_data: 回调数据
        db: 数据库会话
    """
    from app.tasks.state_machine import TaskStateMachine

    now = datetime.utcnow()

    # 记录回调接收时间
    task.extra_data = task.extra_data or {}
    task.extra_data["callback_received_at"] = now.isoformat()

    # 处理执行时间
    if callback_data.metadata and callback_data.metadata.get("execution_time_sec"):
        task.execution_time_sec = callback_data.metadata["execution_time_sec"]

    if callback_data.status == "SUCCESS":
        # 成功：更新状态并保存结果
        TaskStateMachine.complete(task, success=True, progress_message="任务执行成功（回调）")

        # 创建输出记录
        output_data = {}
        output_file_ids = []

        if callback_data.result:
            output_data = callback_data.result.data or {}

            # 处理输出文件
            if callback_data.result.output_files:
                output_file_ids = await _download_callback_output_files(
                    task=task,
                    output_files=callback_data.result.output_files,
                    db=db
                )

        task_output = TaskOutput(
            task_id=task.id,
            result=output_data,
            file_ids=output_file_ids,
            output_type="json"
        )
        db.add(task_output)

        # 添加日志
        log = TaskLog(
            task_id=task.id,
            level="INFO",
            message="任务执行成功（通过回调）"
        )
        db.add(log)

        # WebSocket 通知
        await notify_task_log(task.id, "INFO", "任务执行成功（通过回调）")
        await notify_task_complete(task.id, output_data)

    elif callback_data.status == "FAILURE":
        # 失败：更新状态和错误信息
        error_msg = "Unknown error"
        if callback_data.error:
            error_msg = f"[{callback_data.error.code}] {callback_data.error.message}"

        TaskStateMachine.complete(
            task,
            success=False,
            error_message=error_msg,
            progress_message="任务执行失败（回调）"
        )

        # 添加日志
        log = TaskLog(
            task_id=task.id,
            level="ERROR",
            message=f"任务执行失败（通过回调）: {error_msg}"
        )
        db.add(log)

        # WebSocket 通知
        await notify_task_log(task.id, "ERROR", f"任务执行失败: {error_msg}")
        await notify_task_error(task.id, error_msg)

    await db.commit()


async def _download_callback_output_files(
    task: Task,
    output_files: List,
    db: AsyncSession
) -> List[str]:
    """
    下载回调中的输出文件

    复用现有 RemoteAPIExecutor._process_output_files 的逻辑

    Args:
        task: 任务对象
        output_files: 输出文件列表
        db: 数据库会话

    Returns:
        上传后的文件ID列表
    """
    from app.models.files import File as FileModel, FileSourceType
    from app.api.v1.files import get_file_path
    import httpx
    import hashlib
    import uuid

    uploaded_ids = []

    for file_info in output_files:
        url = file_info.url
        filename = file_info.name or f"output_{uuid.uuid4()}.dat"

        if not url:
            logger.warning(f"Output file {filename} missing URL, skipping")
            continue

        try:
            # 从远程URL下载文件
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content

            # 计算文件信息
            sha256_hash = hashlib.sha256(content).hexdigest()
            file_size = len(content)
            content_type = file_info.content_type or response.headers.get(
                "content-type", "application/octet-stream"
            )

            # 创建文件记录
            file_record = FileModel(
                filename=filename,
                content_type=content_type,
                size_bytes=file_size,
                sha256=sha256_hash,
                source_type=FileSourceType.TOOL_OUTPUT.value,
                owner_id=task.user_id,
                is_public=False,
                is_permanent=False
            )

            db.add(file_record)
            await db.flush()

            # 保存到存储
            storage_path = get_file_path(file_record.id, filename)
            storage_path.parent.mkdir(parents=True, exist_ok=True)

            with open(storage_path, "wb") as f:
                f.write(content)

            file_record.storage_path = str(storage_path)
            await db.flush()

            uploaded_ids.append(file_record.id)
            logger.info(f"Downloaded callback output file: {filename} -> {file_record.id}")

        except httpx.HTTPError as e:
            logger.error(f"Failed to download output file from {url}: {e}")
            continue
        except Exception as e:
            logger.error(f"Failed to process output file {filename}: {e}")
            continue

    return uploaded_ids
```


### 3.5 超时处理机制

#### 3.5.1 Celery 定时任务

```python
# backend/app/worker/tasks.py（新增）

from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import datetime, timedelta
import asyncio

logger = get_task_logger(__name__)


@shared_task(name="app.worker.tasks.check_callback_timeout")
def check_callback_timeout():
    """
    检查回调超时的任务

    定时执行（建议每5分钟），将超时的回调任务标记为失败。
    """
    logger.info("Starting callback timeout check")

    loop = asyncio.get_event_loop()
    count = loop.run_until_complete(_check_callback_timeout_impl())

    logger.info(f"Callback timeout check completed, {count} tasks marked as timeout")
    return {"timeout_count": count}


async def _check_callback_timeout_impl() -> int:
    """检查回调超时任务的实现"""
    from sqlalchemy import select, and_
    from sqlalchemy.dialects.sqlite import JSON
    from app.database.session import async_session_factory
    from app.models.tasks import Task, TaskStatus, TaskLog
    from app.tasks.state_machine import TaskStateMachine

    timeout_count = 0

    async with async_session_factory() as db:
        # 查询等待回调的任务
        # 条件：状态为 RUNNING 且 extra_data.callback_mode = true
        result = await db.execute(
            select(Task).where(
                and_(
                    Task.status == TaskStatus.RUNNING.value,
                    Task.started_at.isnot(None)
                )
            )
        )
        running_tasks = result.scalars().all()

        now = datetime.utcnow()

        for task in running_tasks:
            # 检查是否为回调模式任务
            if not task.extra_data or not task.extra_data.get("callback_mode"):
                continue

            # 获取超时时间（默认1小时）
            callback_timeout_sec = task.extra_data.get("callback_timeout_sec", 3600)
            callback_sent_at_str = task.extra_data.get("callback_sent_at")

            if not callback_sent_at_str:
                # 如果没有记录发送时间，使用 started_at
                callback_sent_at = task.started_at
            else:
                callback_sent_at = datetime.fromisoformat(callback_sent_at_str)

            # 检查是否超时
            timeout_threshold = callback_sent_at + timedelta(seconds=callback_timeout_sec)

            if now > timeout_threshold:
                logger.warning(
                    f"Task {task.id} callback timeout "
                    f"(sent_at={callback_sent_at}, timeout={callback_timeout_sec}s)"
                )

                # 标记任务为失败
                try:
                    TaskStateMachine.complete(
                        task,
                        success=False,
                        error_message=f"Callback timeout: No response from tool within {callback_timeout_sec} seconds",
                        progress_message="任务超时（未收到回调）"
                    )

                    # 记录超时信息
                    task.extra_data["callback_timeout_at"] = now.isoformat()

                    # 添加日志
                    log = TaskLog(
                        task_id=task.id,
                        level="ERROR",
                        message=f"任务回调超时，等待时间超过 {callback_timeout_sec} 秒"
                    )
                    db.add(log)

                    # WebSocket 通知
                    await notify_task_error(
                        task.id,
                        f"任务超时：工具未在 {callback_timeout_sec} 秒内返回结果"
                    )

                    timeout_count += 1

                except Exception as e:
                    logger.error(f"Failed to mark task {task.id} as timeout: {e}")

        await db.commit()

    return timeout_count
```

#### 3.5.2 Celery Beat 配置

```python
# backend/app/config.py（扩展现有配置）

# Celery Beat 定时任务配置
CELERY_BEAT_SCHEDULE = {
    # 现有任务...

    # 回调超时检查（每5分钟执行一次）
    'check-callback-timeout': {
        'task': 'app.worker.tasks.check_callback_timeout',
        'schedule': 300.0,  # 5分钟
        'options': {
            'queue': 'default',
            'expires': 290,  # 任务过期时间略小于调度间隔
        }
    },

    # 清理过期文件（每小时执行一次）
    'cleanup-expired-files': {
        'task': 'app.worker.tasks.cleanup_expired_files',
        'schedule': 3600.0,  # 1小时
    },
}
```

#### 3.5.3 超时告警（可选）

```python
# backend/app/monitoring/alert_rules.py（扩展）

from app.monitoring.base import AlertRule, AlertSeverity

class CallbackTimeoutAlertRule(AlertRule):
    """回调超时告警规则"""

    name = "callback_timeout"
    description = "检测回调超时任务数量"
    severity = AlertSeverity.WARNING

    # 阈值：5分钟内超过10个任务超时则告警
    threshold = 10
    window_minutes = 5

    async def check(self) -> bool:
        """检查是否触发告警"""
        from app.database.session import async_session_factory
        from sqlalchemy import select, func
        from app.models.tasks import Task, TaskStatus
        from datetime import datetime, timedelta

        async with async_session_factory() as db:
            # 统计最近5分钟内因回调超时而失败的任务
            window_start = datetime.utcnow() - timedelta(minutes=self.window_minutes)

            result = await db.execute(
                select(func.count(Task.id)).where(
                    Task.status == TaskStatus.FAILURE.value,
                    Task.finished_at >= window_start,
                    Task.error_message.like("%Callback timeout%")
                )
            )
            timeout_count = result.scalar()

            return timeout_count >= self.threshold

    def get_alert_message(self) -> str:
        return f"回调超时任务数量超过阈值（{self.threshold}个/{self.window_minutes}分钟）"
```

---

## 4. 数据模型

### 4.1 Schema 定义汇总

所有新增 Schema 定义位于 `backend/app/schemas/tasks.py`：

```python
# backend/app/schemas/tasks.py（完整新增内容）

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ==================== 回调相关 Schema ====================

class CallbackOutputFile(BaseModel):
    """回调输出文件"""
    name: str = Field(..., description="文件名")
    url: str = Field(..., description="文件下载URL")
    size: Optional[int] = Field(None, description="文件大小（字节）")
    content_type: Optional[str] = Field(None, description="MIME类型")


class CallbackResult(BaseModel):
    """回调结果数据"""
    data: Optional[Any] = Field(None, description="结果数据（任意JSON结构）")
    output_files: Optional[List[CallbackOutputFile]] = Field(
        default_factory=list,
        description="输出文件列表"
    )


class CallbackError(BaseModel):
    """回调错误信息"""
    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误信息")


class TaskCallbackRequest(BaseModel):
    """任务回调请求

    工具服务完成任务后，通过此接口回调平台更新任务状态。
    """
    task_id: str = Field(..., description="任务ID")
    status: str = Field(
        ...,
        pattern="^(SUCCESS|FAILURE)$",
        description="任务状态：SUCCESS 或 FAILURE"
    )
    result: Optional[CallbackResult] = Field(
        None,
        description="任务结果（status=SUCCESS 时必填）"
    )
    error: Optional[CallbackError] = Field(
        None,
        description="错误信息（status=FAILURE 时必填）"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="元数据，如 execution_time_sec"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "SUCCESS",
                "result": {
                    "data": {"processed": True, "count": 100},
                    "output_files": [
                        {
                            "name": "result.csv",
                            "url": "http://tool-service/files/result.csv",
                            "size": 1024,
                            "content_type": "text/csv"
                        }
                    ]
                },
                "metadata": {"execution_time_sec": 120}
            }
        }


class TaskCallbackResponse(BaseModel):
    """任务回调响应"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务最终状态")
    received_at: str = Field(..., description="回调接收时间（ISO格式）")
    first_received_at: Optional[str] = Field(
        None,
        description="首次回调接收时间（幂等处理时返回）"
    )
```

### 4.2 工具配置 Schema 扩展

```python
# backend/app/schemas/tools.py（扩展）

class ToolVersionConfig(BaseModel):
    """工具版本配置"""
    type: str = Field(..., description="执行器类型：remote_api, docker_image, python_script")
    endpoint: Optional[str] = Field(None, description="API端点（remote_api类型）")
    method: str = Field(default="POST", description="HTTP方法")
    timeout_sec: int = Field(default=600, description="超时时间（秒）")
    headers: Dict[str, str] = Field(default_factory=dict, description="请求头")

    # 回调模式配置
    callback_mode: bool = Field(default=False, description="是否启用回调模式")
    callback_timeout_sec: int = Field(default=3600, description="回调超时时间（秒）")
    callback_secret: Optional[str] = Field(None, description="回调签名密钥（自动生成）")

    # GPU配置
    gpu_required: bool = Field(default=False, description="是否需要GPU")
    gpu_config: Optional[Dict[str, Any]] = Field(None, description="GPU配置")

    # 资源限制
    memory_limit: str = Field(default="4g", description="内存限制")
    cpu_limit: int = Field(default=2, description="CPU核心数限制")

    class Config:
        extra = "allow"  # 允许额外字段
```


---

## 5. 实施步骤

### 5.1 第一阶段：基础设施（1天）

#### 5.1.1 新增文件

| 文件路径 | 说明 |
|----------|------|
| `backend/app/utils/callback_signature.py` | 签名生成和验证工具 |
| `backend/app/services/tool_service.py` | 工具服务（含密钥生成） |

#### 5.1.2 实施清单

- [ ] 创建 `backend/app/utils/callback_signature.py`
  - 实现 `generate_callback_signature()` 函数
  - 实现 `verify_callback_signature()` 函数
  - 添加 nonce 缓存逻辑
- [ ] 创建 `backend/app/services/tool_service.py`
  - 实现 `generate_callback_secret()` 函数
  - 实现 `ensure_callback_secret()` 函数
- [ ] 扩展 `backend/app/schemas/tasks.py`
  - 添加 `CallbackOutputFile` Schema
  - 添加 `CallbackResult` Schema
  - 添加 `CallbackError` Schema
  - 添加 `TaskCallbackRequest` Schema
  - 添加 `TaskCallbackResponse` Schema

### 5.2 第二阶段：核心功能（2天）

#### 5.2.1 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `backend/app/tasks/executor.py` | 扩展 `RemoteAPIExecutor` 支持回调模式 |
| `backend/app/worker/tasks.py` | 添加回调状态处理逻辑 |
| `backend/app/api/v1/tasks.py` | 添加回调接口 |

#### 5.2.2 实施清单

- [ ] 修改 `backend/app/tasks/executor.py`
  - 在 `RemoteAPIExecutor.__init__` 中添加回调配置读取
  - 实现 `_prepare_headers()` 方法（注入回调头部）
  - 实现 `_handle_callback_response()` 方法
  - 修改 `execute()` 方法处理 code=20001 响应
- [ ] 修改 `backend/app/worker/tasks.py`
  - 在 `_execute_tool_task_impl()` 中添加回调状态处理
  - 更新 `task.extra_data` 存储回调元数据
- [ ] 修改 `backend/app/api/v1/tasks.py`
  - 添加 `POST /{task_id}/callback` 路由
  - 实现 `task_callback()` 接口函数
  - 实现 `_process_callback()` 辅助函数
  - 实现 `_download_callback_output_files()` 辅助函数

### 5.3 第三阶段：超时处理（0.5天）

#### 5.3.1 实施清单

- [ ] 修改 `backend/app/worker/tasks.py`
  - 添加 `check_callback_timeout` Celery 任务
  - 实现 `_check_callback_timeout_impl()` 函数
- [ ] 修改 `backend/app/config.py`
  - 添加 `CELERY_BEAT_SCHEDULE` 配置
- [ ] （可选）修改 `backend/app/monitoring/alert_rules.py`
  - 添加 `CallbackTimeoutAlertRule` 告警规则

### 5.4 第四阶段：测试与文档（1.5天）

#### 5.4.1 测试文件

| 文件路径 | 说明 |
|----------|------|
| `backend/tests/test_callback_signature.py` | 签名验证单元测试 |
| `backend/tests/test_callback_api.py` | 回调接口集成测试 |
| `example/callback-test-tool/` | 回调模式测试工具 |

#### 5.4.2 实施清单

- [ ] 创建 `backend/tests/test_callback_signature.py`
  - 测试签名生成
  - 测试签名验证
  - 测试签名超时
  - 测试 nonce 重放检测
- [ ] 创建 `backend/tests/test_callback_api.py`
  - 测试成功回调
  - 测试失败回调
  - 测试无效签名
  - 测试幂等性
  - 测试非回调模式任务
- [ ] 创建 `example/callback-test-tool/`
  - 实现测试工具服务
  - 编写 Docker Compose 配置
  - 编写工具配置文件
- [ ] 更新文档
  - 更新 `docs/API_DOCUMENTATION.md`
  - 更新 `docs/工具创建调用完整指南.md`


---

## 6. 测试方案

### 6.1 单元测试

#### 6.1.1 签名验证测试

```python
# backend/tests/test_callback_signature.py

import pytest
import time
import hmac
import hashlib
import secrets
from unittest.mock import AsyncMock, patch

from app.utils.callback_signature import (
    generate_callback_signature,
    verify_callback_signature,
    SIGNATURE_VALIDITY_SECONDS
)


class TestSignatureGeneration:
    """签名生成测试"""

    def test_signature_generation_basic(self):
        """测试基本签名生成"""
        task_id = "test-task-123"
        body = '{"status": "SUCCESS"}'
        secret = "test-secret-key"

        signature, timestamp, nonce = generate_callback_signature(task_id, body, secret)

        assert signature is not None
        assert len(signature) == 64  # SHA256 hex digest
        assert timestamp.isdigit()
        assert len(nonce) == 32  # 16 bytes hex

    def test_signature_generation_with_custom_nonce(self):
        """测试使用自定义 nonce"""
        task_id = "test-task-123"
        body = '{"status": "SUCCESS"}'
        secret = "test-secret-key"
        custom_nonce = "custom-nonce-12345678"

        signature, timestamp, nonce = generate_callback_signature(
            task_id, body, secret, nonce=custom_nonce
        )

        assert nonce == custom_nonce

    def test_signature_deterministic(self):
        """测试相同输入产生相同签名"""
        task_id = "test-task-123"
        body = '{"status": "SUCCESS"}'
        secret = "test-secret-key"
        fixed_nonce = "fixed-nonce"

        sig1, ts1, _ = generate_callback_signature(task_id, body, secret, nonce=fixed_nonce)

        # 手动计算预期签名
        message = f"{task_id}:{ts1}:{fixed_nonce}:{body}"
        expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

        assert sig1 == expected


class TestSignatureVerification:
    """签名验证测试"""

    @pytest.mark.asyncio
    async def test_valid_signature(self):
        """测试有效签名验证"""
        task_id = "test-task-123"
        body = '{"status": "SUCCESS"}'
        secret = "test-secret-key"

        signature, timestamp, nonce = generate_callback_signature(task_id, body, secret)

        with patch('app.utils.callback_signature.cache_manager') as mock_cache:
            mock_cache.exists = AsyncMock(return_value=False)
            mock_cache.set = AsyncMock()

            is_valid, error = await verify_callback_signature(
                task_id, body, signature, timestamp, nonce, secret
            )

            assert is_valid is True
            assert error is None

    @pytest.mark.asyncio
    async def test_invalid_signature(self):
        """测试无效签名"""
        task_id = "test-task-123"
        body = '{"status": "SUCCESS"}'
        secret = "test-secret-key"
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)

        with patch('app.utils.callback_signature.cache_manager') as mock_cache:
            mock_cache.exists = AsyncMock(return_value=False)

            is_valid, error = await verify_callback_signature(
                task_id, body, "invalid-signature", timestamp, nonce, secret
            )

            assert is_valid is False
            assert "Invalid signature" in error

    @pytest.mark.asyncio
    async def test_expired_signature(self):
        """测试过期签名"""
        task_id = "test-task-123"
        body = '{"status": "SUCCESS"}'
        secret = "test-secret-key"
        nonce = secrets.token_hex(16)

        # 使用过期的时间戳
        old_timestamp = str(int(time.time()) - SIGNATURE_VALIDITY_SECONDS - 100)
        message = f"{task_id}:{old_timestamp}:{nonce}:{body}"
        signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

        is_valid, error = await verify_callback_signature(
            task_id, body, signature, old_timestamp, nonce, secret
        )

        assert is_valid is False
        assert "expired" in error.lower()

    @pytest.mark.asyncio
    async def test_nonce_replay_detection(self):
        """测试 nonce 重放检测"""
        task_id = "test-task-123"
        body = '{"status": "SUCCESS"}'
        secret = "test-secret-key"

        signature, timestamp, nonce = generate_callback_signature(task_id, body, secret)

        with patch('app.utils.callback_signature.cache_manager') as mock_cache:
            # 模拟 nonce 已存在（重放攻击）
            mock_cache.exists = AsyncMock(return_value=True)

            is_valid, error = await verify_callback_signature(
                task_id, body, signature, timestamp, nonce, secret
            )

            assert is_valid is False
            assert "replay" in error.lower()
```

#### 6.1.2 回调接口测试

```python
# backend/tests/test_callback_api.py

import pytest
import json
import time
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient

from app.models.tasks import Task, TaskStatus
from app.utils.callback_signature import generate_callback_signature


@pytest.fixture
def callback_mode_task(db_session):
    """创建回调模式任务"""
    task = Task(
        id="test-callback-task",
        user_id="test-user",
        tool_id="test-tool",
        tool_version_id="test-version",
        status=TaskStatus.RUNNING.value,
        extra_data={
            "callback_mode": True,
            "callback_url": "http://localhost:8000/api/v1/tasks/test-callback-task/callback",
            "callback_timeout_sec": 3600,
            "callback_sent_at": "2025-12-24T10:00:00"
        }
    )
    db_session.add(task)
    db_session.commit()
    return task


@pytest.fixture
def tool_version_with_secret(db_session):
    """创建带回调密钥的工具版本"""
    from app.models.tools import ToolVersion
    version = ToolVersion(
        id="test-version",
        tool_id="test-tool",
        version="1.0.0",
        config={
            "type": "remote_api",
            "endpoint": "http://tool-service/process",
            "callback_mode": True,
            "callback_secret": "test-callback-secret-key"
        }
    )
    db_session.add(version)
    db_session.commit()
    return version


class TestCallbackAPI:
    """回调接口测试"""

    @pytest.mark.asyncio
    async def test_callback_success(
        self, client: AsyncClient, callback_mode_task, tool_version_with_secret
    ):
        """测试成功回调"""
        callback_data = {
            "task_id": callback_mode_task.id,
            "status": "SUCCESS",
            "result": {
                "data": {"processed": True, "count": 100},
                "output_files": []
            },
            "metadata": {"execution_time_sec": 60}
        }

        body = json.dumps(callback_data)
        signature, timestamp, nonce = generate_callback_signature(
            callback_mode_task.id,
            body,
            tool_version_with_secret.config["callback_secret"]
        )

        response = await client.post(
            f"/api/v1/tasks/{callback_mode_task.id}/callback",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Callback-Signature": signature,
                "X-Callback-Timestamp": timestamp,
                "X-Callback-Nonce": nonce
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["status"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_callback_failure(
        self, client: AsyncClient, callback_mode_task, tool_version_with_secret
    ):
        """测试失败回调"""
        callback_data = {
            "task_id": callback_mode_task.id,
            "status": "FAILURE",
            "error": {
                "code": 1001,
                "message": "Processing failed: invalid input"
            }
        }

        body = json.dumps(callback_data)
        signature, timestamp, nonce = generate_callback_signature(
            callback_mode_task.id,
            body,
            tool_version_with_secret.config["callback_secret"]
        )

        response = await client.post(
            f"/api/v1/tasks/{callback_mode_task.id}/callback",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Callback-Signature": signature,
                "X-Callback-Timestamp": timestamp,
                "X-Callback-Nonce": nonce
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    async def test_callback_idempotency(
        self, client: AsyncClient, callback_mode_task, tool_version_with_secret, db_session
    ):
        """测试回调幂等性"""
        # 先将任务标记为已完成
        callback_mode_task.status = TaskStatus.SUCCESS.value
        callback_mode_task.extra_data["callback_received_at"] = "2025-12-24T10:05:00"
        db_session.commit()

        callback_data = {
            "task_id": callback_mode_task.id,
            "status": "SUCCESS",
            "result": {"data": {}}
        }

        body = json.dumps(callback_data)
        signature, timestamp, nonce = generate_callback_signature(
            callback_mode_task.id,
            body,
            tool_version_with_secret.config["callback_secret"]
        )

        response = await client.post(
            f"/api/v1/tasks/{callback_mode_task.id}/callback",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Callback-Signature": signature,
                "X-Callback-Timestamp": timestamp,
                "X-Callback-Nonce": nonce
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "already processed" in data["message"].lower()
        assert data["data"]["first_received_at"] is not None

    @pytest.mark.asyncio
    async def test_callback_invalid_signature(
        self, client: AsyncClient, callback_mode_task
    ):
        """测试无效签名"""
        callback_data = {
            "task_id": callback_mode_task.id,
            "status": "SUCCESS",
            "result": {"data": {}}
        }

        response = await client.post(
            f"/api/v1/tasks/{callback_mode_task.id}/callback",
            json=callback_data,
            headers={
                "X-Callback-Signature": "invalid-signature",
                "X-Callback-Timestamp": str(int(time.time())),
                "X-Callback-Nonce": "test-nonce"
            }
        )

        assert response.status_code == 200  # 返回业务错误码
        data = response.json()
        assert data["code"] == 40101  # 签名验证失败

    @pytest.mark.asyncio
    async def test_callback_missing_headers(
        self, client: AsyncClient, callback_mode_task
    ):
        """测试缺少必要头部"""
        callback_data = {
            "task_id": callback_mode_task.id,
            "status": "SUCCESS",
            "result": {"data": {}}
        }

        response = await client.post(
            f"/api/v1/tasks/{callback_mode_task.id}/callback",
            json=callback_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 40001

    @pytest.mark.asyncio
    async def test_callback_non_callback_mode_task(
        self, client: AsyncClient, db_session, tool_version_with_secret
    ):
        """测试非回调模式任务"""
        # 创建非回调模式任务
        task = Task(
            id="non-callback-task",
            user_id="test-user",
            tool_id="test-tool",
            tool_version_id="test-version",
            status=TaskStatus.RUNNING.value,
            extra_data={}  # 没有 callback_mode
        )
        db_session.add(task)
        db_session.commit()

        callback_data = {
            "task_id": task.id,
            "status": "SUCCESS",
            "result": {"data": {}}
        }

        body = json.dumps(callback_data)
        signature, timestamp, nonce = generate_callback_signature(
            task.id,
            body,
            tool_version_with_secret.config["callback_secret"]
        )

        response = await client.post(
            f"/api/v1/tasks/{task.id}/callback",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Callback-Signature": signature,
                "X-Callback-Timestamp": timestamp,
                "X-Callback-Nonce": nonce
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 40003  # 非回调模式任务
```


### 6.2 集成测试

#### 6.2.1 创建测试工具

```python
# example/callback-test-tool/app.py

import asyncio
import json
import secrets
from fastapi import FastAPI, BackgroundTasks, Request
import httpx
import hmac
import hashlib
import time

app = FastAPI(title="Callback Test Tool")


def generate_callback_signature(task_id: str, body: str, secret: str) -> tuple:
    """生成回调签名"""
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    message = f"{task_id}:{timestamp}:{nonce}:{body}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature, timestamp, nonce


async def send_callback(callback_url: str, task_id: str, secret: str, result_data: dict):
    """发送回调"""
    await asyncio.sleep(2)  # 模拟处理时间

    # 准备回调数据
    callback_data = {
        "task_id": task_id,
        "status": "SUCCESS",
        "result": {
            "data": result_data,
            "output_files": []
        },
        "metadata": {
            "execution_time_sec": 2
        }
    }

    # 生成签名
    body = json.dumps(callback_data)
    signature, timestamp, nonce = generate_callback_signature(task_id, body, secret)

    # 发送回调
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                callback_url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Callback-Signature": signature,
                    "X-Callback-Timestamp": timestamp,
                    "X-Callback-Nonce": nonce
                },
                timeout=30
            )
            print(f"Callback response: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Callback failed: {e}")


@app.post("/process")
async def process(request: Request, background_tasks: BackgroundTasks):
    """处理请求（回调模式）"""
    # 从请求头获取回调信息
    callback_url = request.headers.get("X-SCIMINER-CALLBACK-URL")
    task_id = request.headers.get("X-SCIMINER-TASK-ID")
    callback_secret = request.headers.get("X-SCIMINER-CALLBACK-SECRET")

    # 获取请求数据
    data = await request.json()
    params = data.get("params", {})

    # 模拟处理结果
    result_data = {
        "processed": True,
        "input_params": params,
        "message": "Processing completed successfully"
    }

    # 添加后台任务发送回调
    if callback_url and callback_secret:
        background_tasks.add_task(
            send_callback,
            callback_url,
            task_id,
            callback_secret,
            result_data
        )

    # 立即返回 20001
    return {
        "code": 20001,
        "message": "Task accepted, processing in background",
        "data": {"task_id": task_id}
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}
```

#### 6.2.2 测试工具 Docker 配置

```yaml
# example/callback-test-tool/docker-compose.yml

version: '3.8'

services:
  callback-test-tool:
    build: .
    ports:
      - "8001:8000"
    environment:
      - LOG_LEVEL=INFO
    networks:
      - sciminer-network

networks:
  sciminer-network:
    external: true
```

```dockerfile
# example/callback-test-tool/Dockerfile

FROM python:3.11-slim

WORKDIR /app

RUN pip install fastapi uvicorn httpx

COPY app.py .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 6.2.3 测试工具配置

```json
// example/callback-test-tool/tool_config.json
{
  "name": "callback-test-tool",
  "slug": "callback-test-tool",
  "display_name": "回调模式测试工具",
  "description": "用于测试回调模式的示例工具",
  "category": "测试",
  "version": "1.0.0",
  "config": {
    "type": "remote_api",
    "endpoint": "http://callback-test-tool:8000/process",
    "method": "POST",
    "timeout_sec": 30,
    "callback_mode": true,
    "callback_timeout_sec": 300
  },
  "input_schema": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string",
        "description": "输入文本"
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "processed": {
        "type": "boolean"
      },
      "message": {
        "type": "string"
      }
    }
  }
}
```

#### 6.2.4 端到端测试流程

```bash
# 1. 启动测试工具
cd example/callback-test-tool
docker-compose up -d

# 2. 注册测试工具到平台
cd ../../backend
python3 ../create_tool.py --config ../example/callback-test-tool/tool_config.json

# 3. 通过 API 提交测试任务
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "tool_id": "<callback-test-tool-id>",
    "params": {"text": "Hello World"}
  }'

# 4. 监控任务状态
# - 在 Flower 中查看: http://localhost:5555
# - 查看数据库: sqlite3 storage/scitool.db "SELECT id, status, extra_data FROM tasks ORDER BY created_at DESC LIMIT 1"
# - 查看日志: docker-compose logs -f backend

# 5. 验证回调接收
# - 检查任务状态是否从 RUNNING 更新为 SUCCESS
# - 检查 extra_data.callback_received_at 是否有值
# - 检查 task_outputs 表是否有结果记录
```


---

## 7. 安全考虑

### 7.1 签名安全

| 安全措施 | 说明 |
|----------|------|
| **HMAC-SHA256** | 使用强加密算法，防止签名伪造 |
| **时间戳验证** | 5分钟有效期，防止重放攻击 |
| **Nonce 机制** | 每次请求唯一随机数，防止重放攻击 |
| **密钥隔离** | 每个工具独立的 callback_secret |
| **密钥轮换** | 支持定期更新密钥（通过更新工具配置） |

### 7.2 访问控制

| 控制点 | 说明 |
|--------|------|
| **任务存在性** | 验证回调的任务是否存在 |
| **回调模式检查** | 只允许回调模式任务接收回调 |
| **状态检查** | 只允许 RUNNING 状态的任务接收回调 |
| **幂等性** | 已完成任务的重复回调返回成功但不重复处理 |

### 7.3 数据验证

| 验证项 | 说明 |
|--------|------|
| **Schema 验证** | 使用 Pydantic 验证回调数据结构 |
| **task_id 一致性** | URL 中的 task_id 必须与请求体中的一致 |
| **文件 URL 验证** | 验证输出文件 URL 格式和可访问性 |
| **结果大小限制** | 限制回调数据大小（建议 10MB） |

### 7.4 网络安全建议

```yaml
# 生产环境建议配置

# 1. 使用 HTTPS
PLATFORM_BASE_URL: "https://api.sciminer.example.com"

# 2. 配置防火墙规则，只允许已知工具服务 IP 访问回调接口

# 3. 配置请求频率限制
# nginx 配置示例：
# limit_req_zone $binary_remote_addr zone=callback:10m rate=10r/s;
# location /api/v1/tasks/*/callback {
#     limit_req zone=callback burst=20 nodelay;
# }
```


---

## 8. 性能优化

### 8.1 异步处理

- 回调接口使用 `async/await`，避免阻塞
- 文件下载使用 `httpx.AsyncClient`
- 数据库操作使用 `AsyncSession`

### 8.2 缓存策略

```python
# 工具配置缓存（减少数据库查询）
# 在 backend/app/cache/__init__.py 中配置

TOOL_VERSION_CACHE_TTL = 300  # 5分钟

async def get_tool_version_config(version_id: str) -> dict:
    """获取工具版本配置（带缓存）"""
    cache_key = f"tool_version:{version_id}:config"
    cached = await cache_manager.get(cache_key)
    if cached:
        return json.loads(cached)

    # 从数据库获取
    config = await _fetch_from_db(version_id)
    await cache_manager.set(cache_key, json.dumps(config), ttl=TOOL_VERSION_CACHE_TTL)
    return config
```

### 8.3 监控指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| `callback_latency_seconds` | 回调接收延迟 | > 5s |
| `callback_success_rate` | 回调成功率 | < 99% |
| `callback_timeout_count` | 超时任务数量 | > 10/5min |
| `signature_failure_count` | 签名验证失败次数 | > 50/5min |


---

## 9. 兼容性说明

### 9.1 向后兼容

- 现有标准模式工具**不受影响**
- 通过配置字段 `callback_mode` 区分模式
- 默认为标准模式（`callback_mode: false`）
- 无需数据库迁移（使用现有 `extra_data` 字段）

### 9.2 工具迁移指南

**旧版 SciMiner 工具迁移步骤**：

1. **更新工具配置**
   ```json
   {
     "callback_mode": true,
     "callback_timeout_sec": 3600
   }
   ```

2. **修改工具代码**
   - 从请求头获取回调信息：
     - `X-SCIMINER-CALLBACK-URL`
     - `X-SCIMINER-TASK-ID`
     - `X-SCIMINER-CALLBACK-SECRET`
   - 使用平台提供的签名算法生成签名
   - 添加 `X-Callback-Nonce` 头部

3. **测试验证**
   - 在测试环境验证回调功能
   - 检查签名验证是否通过
   - 检查任务状态是否正确更新

### 9.3 API 版本兼容

| 版本 | 变更 |
|------|------|
| v1.0 | 初始版本，支持基本回调功能 |
| v1.1（计划） | 添加回调重试机制 |
| v1.2（计划） | 支持批量回调 |


---

## 10. 总结

### 10.1 核心特性

✅ **双模式支持**
- 标准模式：工具直接返回结果
- 回调模式：工具后台执行，完成后回调

✅ **安全可靠**
- HMAC-SHA256 签名验证
- 时间戳 + Nonce 防重放攻击
- 独立密钥管理

✅ **幂等性保证**
- 重复回调不会重复处理
- 返回首次处理时间

✅ **超时保护**
- Celery 定时任务检查超时
- 自动标记超时任务为失败
- 可配置超时时间

✅ **向后兼容**
- 不影响现有工具
- 通过配置启用回调模式
- 无需数据库迁移

✅ **完整的 WebSocket 通知**
- 回调状态实时推送
- 与现有通知机制无缝集成

### 10.2 预期收益

1. **兼容性提升**：支持旧版 SciMiner 工具无缝迁移
2. **灵活性增强**：工具可选择最适合的执行模式
3. **可靠性保障**：完善的超时和错误处理机制
4. **安全性加固**：签名验证防止恶意回调
5. **可观测性**：完整的日志和监控指标

### 10.3 工作量评估（更新）

| 阶段 | 工作量 | 优先级 | 涉及文件 |
|------|--------|--------|----------|
| 基础设施 | 1天 | 高 | 2个新文件 |
| 核心功能 | 2天 | 高 | 3个修改文件 |
| 超时处理 | 0.5天 | 中 | 2个修改文件 |
| 测试文档 | 1.5天 | 中 | 3个新文件 |
| **总计** | **5天** | - | - |


---

## 11. 附录

### 11.1 完整示例：工具端实现

```python
# 工具端完整示例代码
# 文件：tool_service/app.py

import asyncio
import json
import secrets
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, BackgroundTasks, Request
import httpx
import hmac
import hashlib
import time

app = FastAPI(title="Callback Mode Tool Example")
logger = logging.getLogger(__name__)


def generate_callback_signature(
    task_id: str,
    body: str,
    secret: str
) -> tuple[str, str, str]:
    """
    生成回调签名

    Args:
        task_id: 任务ID
        body: 请求体JSON字符串
        secret: 回调密钥

    Returns:
        (signature, timestamp, nonce)
    """
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)

    # 签名消息格式：task_id:timestamp:nonce:body
    message = f"{task_id}:{timestamp}:{nonce}:{body}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    return signature, timestamp, nonce


def perform_processing(input_data: dict) -> dict:
    """
    执行实际的业务处理逻辑

    这里是您的核心业务代码
    """
    # 示例：简单的数据处理
    params = input_data.get("params", {})
    return {
        "processed": True,
        "input_count": len(params),
        "result_message": "Processing completed successfully"
    }


async def process_and_callback(
    callback_url: str,
    task_id: str,
    callback_secret: str,
    input_data: dict
):
    """后台处理并回调"""
    start_time = time.time()

    try:
        # 1. 执行实际处理
        logger.info(f"Processing task {task_id}")
        result = perform_processing(input_data)
        execution_time = int(time.time() - start_time)

        # 2. 准备成功回调数据
        callback_data = {
            "task_id": task_id,
            "status": "SUCCESS",
            "result": {
                "data": result,
                "output_files": []  # 如有输出文件，在此添加
            },
            "metadata": {
                "execution_time_sec": execution_time
            }
        }

    except Exception as e:
        # 处理失败
        logger.error(f"Task {task_id} failed: {e}")
        callback_data = {
            "task_id": task_id,
            "status": "FAILURE",
            "error": {
                "code": 1000,
                "message": str(e)
            },
            "metadata": {
                "execution_time_sec": int(time.time() - start_time)
            }
        }

    # 3. 生成签名
    body = json.dumps(callback_data, ensure_ascii=False)
    signature, timestamp, nonce = generate_callback_signature(
        task_id, body, callback_secret
    )

    # 4. 发送回调（带重试）
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    callback_url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Callback-Signature": signature,
                        "X-Callback-Timestamp": timestamp,
                        "X-Callback-Nonce": nonce
                    },
                    timeout=30
                )

                if response.status_code == 200:
                    logger.info(f"Callback sent successfully for task {task_id}")
                    return
                else:
                    logger.warning(
                        f"Callback failed for task {task_id}: "
                        f"{response.status_code} - {response.text}"
                    )

        except Exception as e:
            logger.error(f"Callback attempt {attempt + 1} failed: {e}")

        # 等待后重试
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)  # 指数退避

    logger.error(f"All callback attempts failed for task {task_id}")


@app.post("/process")
async def process(request: Request, background_tasks: BackgroundTasks):
    """
    接收处理请求

    平台会在请求头中注入回调信息：
    - X-SCIMINER-CALLBACK-URL: 回调地址
    - X-SCIMINER-TASK-ID: 任务ID
    - X-SCIMINER-CALLBACK-SECRET: 回调密钥
    """
    # 1. 获取平台注入的头部
    callback_url = request.headers.get("X-SCIMINER-CALLBACK-URL")
    task_id = request.headers.get("X-SCIMINER-TASK-ID")
    callback_secret = request.headers.get("X-SCIMINER-CALLBACK-SECRET")

    # 2. 获取请求数据
    data = await request.json()

    logger.info(f"Received task {task_id}, callback_url: {callback_url}")

    # 3. 验证必要参数
    if not all([callback_url, task_id, callback_secret]):
        return {
            "code": 40001,
            "message": "Missing callback headers",
            "data": None
        }

    # 4. 添加后台任务
    background_tasks.add_task(
        process_and_callback,
        callback_url,
        task_id,
        callback_secret,
        data
    )

    # 5. 立即返回 20001（表示任务已接收）
    return {
        "code": 20001,
        "message": "Task accepted, processing in background",
        "data": {"task_id": task_id}
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy", "mode": "callback"}
```


### 11.2 工具配置示例

```json
{
  "name": "callback-example-tool",
  "slug": "callback-example-tool",
  "display_name": "回调模式示例工具",
  "description": "演示回调模式的示例工具",
  "category": "示例",
  "version": "1.0.0",
  "config": {
    "type": "remote_api",
    "endpoint": "http://tool-service:8000/process",
    "method": "POST",
    "timeout_sec": 30,
    "callback_mode": true,
    "callback_timeout_sec": 3600
  },
  "input_schema": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string",
        "title": "输入文本",
        "description": "需要处理的文本内容"
      },
      "options": {
        "type": "object",
        "title": "处理选项",
        "properties": {
          "uppercase": {
            "type": "boolean",
            "default": false
          }
        }
      }
    },
    "required": ["text"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "processed": {
        "type": "boolean"
      },
      "result_message": {
        "type": "string"
      }
    }
  }
}
```

### 11.3 环境变量配置

```bash
# backend/.env（新增）

# 平台基础URL（用于构建回调地址）
PLATFORM_BASE_URL=http://localhost:8000

# 回调签名有效期（秒）
CALLBACK_SIGNATURE_VALIDITY_SECONDS=300

# Nonce 缓存过期时间（秒）
CALLBACK_NONCE_CACHE_TTL=600
```

### 11.4 错误码定义

| 错误码 | 说明 |
|--------|------|
| 0 | 成功 |
| 40001 | 缺少必要的请求头 |
| 40002 | task_id 不匹配 |
| 40003 | 任务不是回调模式 |
| 40101 | 签名验证失败 |
| 50001 | 回调密钥未配置 |
| 50002 | 回调处理失败 |

### 11.5 参考资料

- [FastAPI 后台任务](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [HMAC 签名算法](https://docs.python.org/3/library/hmac.html)
- [Celery Beat 定时任务](https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html)
- [httpx 异步HTTP客户端](https://www.python-httpx.org/)

---

**文档版本**: v1.1
**创建日期**: 2025-12-24
**最后更新**: 2025-12-25
**作者**: SciTool Team

