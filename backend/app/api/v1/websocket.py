# backend/app/api/v1/websocket.py
"""WebSocket 接口"""

from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.websocket import ws_manager
from app.auth.jwt_handler import decode_token

import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()


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
        payload = decode_token(token)
        return payload.get("sub")
    except Exception:
        return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    通用 WebSocket 连接端点

    连接参数:
    - token: JWT token（可选，用于身份认证）

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
    # 验证用户身份
    user_id = await get_user_from_token(token)

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
    token: Optional[str] = Query(None)
):
    """
    任务专用 WebSocket 连接端点

    自动订阅指定任务的更新

    路径参数:
    - task_id: 任务 ID

    查询参数:
    - token: JWT token（可选）
    """
    # 验证用户身份
    user_id = await get_user_from_token(token)

    # 建立连接
    connection_id = await ws_manager.connect(websocket, user_id)

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
