# backend/app/api/v1/websocket.py
"""WebSocket 接口"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.websocket import ws_manager
from app.auth.jwt_handler import verify_token
from app.database.session import get_db
from app.common.exceptions import AppException
from app.models.users import User
from app.services.task_access import load_task_for_read_access

import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()
WS_AUTH_SUBPROTOCOL = "scitool-access-token"


def _resolve_ws_token(websocket: WebSocket, query_token: Optional[str]) -> Optional[str]:
    """Prefer a WebSocket subprotocol token over the legacy query parameter."""
    if query_token:
        return query_token

    headers = getattr(websocket, "headers", {})
    protocol_header = headers.get("sec-websocket-protocol", "")
    protocols = [part.strip() for part in protocol_header.split(",") if part.strip()]
    try:
        marker_index = protocols.index(WS_AUTH_SUBPROTOCOL)
    except ValueError:
        return None
    token_index = marker_index + 1
    return protocols[token_index] if token_index < len(protocols) else None


async def get_user_from_token(token: Optional[str]) -> Optional[str]:
    """
    从 token 中获取用户 ID

    Args:
        token: JWT token

    Returns:
        用户 ID 或 None
    """
    if not token:
        return None

    try:
        payload = verify_token(token, token_type="access")
        user_id = payload.get("sub")
        return str(user_id) if user_id else None
    except Exception as exc:
        logger.debug("Failed to decode WebSocket token: %s", exc)
        return None


async def _load_authenticated_user(
    db: AsyncSession,
    token: Optional[str],
) -> Optional[User]:
    user_id = await get_user_from_token(token)
    if not user_id:
        return None
    user = await db.get(User, user_id)
    if user is None or user.status != "active":
        return None
    return user


async def _reject_websocket(websocket: WebSocket, reason: str) -> None:
    await websocket.close(code=1008, reason=reason)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    通用 WebSocket 连接端点

    认证方式:
    - 首选：Sec-WebSocket-Protocol: scitool-access-token, <JWT access token>
    - 兼容：查询参数 token（旧客户端）

    消息格式（客户端发送）:
    ```json
    {
        "action": "subscribe_task" | "unsubscribe_task" | "ping",
        "task_id": "任务ID"  // subscribe/unsubscribe 时需要
    }
    ```

    消息格式（服务端发送）:
    ```json
    {
        "type": "task_status" | "task_progress" | "task_log" | "task_complete" | "task_error" | "heartbeat" | "connected",
        "task_id": "任务ID",
        "timestamp": "ISO时间戳",
        ... // 其他字段根据类型不同
    }
    ```
    """
    current_user = await _load_authenticated_user(
        db,
        _resolve_ws_token(websocket, token),
    )
    if current_user is None:
        await _reject_websocket(websocket, "需要有效的登录凭证")
        return
    user_id = str(current_user.id)

    # 建立连接
    connection_id = await ws_manager.connect(websocket, user_id)

    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "subscribe_task":
                    # 订阅任务
                    task_id = message.get("task_id")
                    if task_id:
                        try:
                            await load_task_for_read_access(
                                db,
                                task_id=str(task_id),
                                current_user=current_user,
                            )
                        except (AppException, HTTPException):
                            await _reject_websocket(websocket, "无权订阅此任务")
                            return
                        await ws_manager.subscribe_task(connection_id, task_id)
                        await ws_manager.send_personal(connection_id, {
                            "type": "subscribed",
                            "task_id": task_id
                        })

                elif action == "unsubscribe_task":
                    # 取消订阅任务
                    task_id = message.get("task_id")
                    if task_id:
                        await ws_manager.unsubscribe_task(connection_id, task_id)
                        await ws_manager.send_personal(connection_id, {
                            "type": "unsubscribed",
                            "task_id": task_id
                        })

                elif action == "ping":
                    # 心跳响应
                    await ws_manager.send_personal(connection_id, {
                        "type": "pong"
                    })

                else:
                    # 未知操作
                    await ws_manager.send_personal(connection_id, {
                        "type": "error",
                        "message": f"未知操作: {action}"
                    })

            except json.JSONDecodeError:
                await ws_manager.send_personal(connection_id, {
                    "type": "error",
                    "message": "无效的 JSON 格式"
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket 断开: {connection_id}")
    except Exception as e:
        logger.error(f"WebSocket 错误: {connection_id}, {e}")
    finally:
        await ws_manager.disconnect(connection_id)


@router.websocket("/ws/tasks/{task_id}")
async def task_websocket_endpoint(
    websocket: WebSocket,
    task_id: str,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    任务专用 WebSocket 连接端点

    自动订阅指定任务的更新

    路径参数:
    - task_id: 任务 ID

    认证方式:
    - 首选：Sec-WebSocket-Protocol: scitool-access-token, <JWT access token>
    - 兼容：查询参数 token（旧客户端）
    """
    current_user = await _load_authenticated_user(
        db,
        _resolve_ws_token(websocket, token),
    )
    if current_user is None:
        await _reject_websocket(websocket, "需要有效的登录凭证")
        return

    try:
        await load_task_for_read_access(
            db,
            task_id=task_id,
            current_user=current_user,
        )
    except (AppException, HTTPException):
        await _reject_websocket(websocket, "无权订阅此任务")
        return

    # 建立连接
    connection_id = await ws_manager.connect(websocket, str(current_user.id))

    # 自动订阅任务
    await ws_manager.subscribe_task(connection_id, task_id)

    try:
        while True:
            # 接收消息（主要用于心跳）
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "ping":
                    await ws_manager.send_personal(connection_id, {
                        "type": "pong"
                    })

            except json.JSONDecodeError:
                await ws_manager.send_personal(connection_id, {
                    "type": "error",
                    "message": "无效的 JSON 格式"
                })

    except WebSocketDisconnect:
        logger.info(f"任务 WebSocket 断开: {connection_id}, 任务: {task_id}")
    except Exception as e:
        logger.error(f"任务 WebSocket 错误: {connection_id}, {e}")
    finally:
        await ws_manager.disconnect(connection_id)


# ==================== HTTP 接口（用于管理和测试） ====================

@router.get("/ws/stats")
async def get_websocket_stats():
    """
    获取 WebSocket 连接统计信息

    Returns:
        连接统计数据
    """
    return ws_manager.get_stats()
