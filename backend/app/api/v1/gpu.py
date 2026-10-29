# backend/app/api/v1/gpu.py
"""GPU资源管理接口

提供GPU资源查询、分配、监控等API端点。
"""

import hmac
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_admin_user
from app.common.responses import success_response
from app.config import settings
from app.database.session import get_db
from app.gpu.detector import get_gpu_detector
from app.gpu.allocator import GPUAllocator, TaskPriority
from app.gpu.monitor import GPUMonitor
from app.gpu.slots import (
    SLOT_STATES,
    SlotConfigError,
    describe_registry,
    load_slot_registry,
    load_slot_states,
    record_slot_state,
    slot_view,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gpu", tags=["GPU资源管理"])


# ============ Schema 定义 ============

class GPUInfoResponse(BaseModel):
    """GPU信息响应"""
    gpu_index: int
    gpu_name: str
    total_memory_mb: int
    free_memory_mb: int
    used_memory_mb: int
    uuid: Optional[str] = None


class GPUStatsResponse(BaseModel):
    """GPU统计响应"""
    gpu_index: int
    utilization_percent: int
    memory_used_mb: int
    memory_free_mb: int
    memory_total_mb: int
    temperature_celsius: int
    power_watts: int
    fan_speed_percent: Optional[int] = None


class NodeInfoResponse(BaseModel):
    """节点信息响应"""
    hostname: str
    gpu_count: int
    total_memory_mb: int
    cuda_version: str
    driver_version: str
    gpus: List[GPUInfoResponse]


class GPUSummaryResponse(BaseModel):
    """GPU摘要响应"""
    available: bool
    hostname: Optional[str] = None
    gpu_count: int = 0
    cuda_version: Optional[str] = None
    driver_version: Optional[str] = None
    total_memory_mb: int = 0
    used_memory_mb: int = 0
    free_memory_mb: int = 0
    memory_usage_percent: float = 0
    avg_utilization_percent: float = 0
    avg_temperature_celsius: float = 0
    gpus: List[Dict[str, Any]] = []
    message: Optional[str] = None


class GPUHealthResponse(BaseModel):
    """GPU健康检查响应"""
    healthy: bool
    timestamp: str
    gpu_available: bool
    gpu_count: int
    hostname: Optional[str] = None
    cuda_version: Optional[str] = None
    driver_version: Optional[str] = None
    issues: List[str] = []
    gpus: List[Dict[str, Any]] = []


class AllocationRequest(BaseModel):
    """GPU分配请求"""
    task_id: str = Field(..., description="任务ID")
    memory_required_mb: int = Field(..., ge=0, description="所需显存(MB)")
    priority: str = Field(default="normal", description="任务优先级")


class AllocationResponse(BaseModel):
    """GPU分配响应"""
    success: bool
    gpu_node_id: Optional[str] = None
    gpu_index: Optional[int] = None
    allocated_memory_mb: int = 0
    allocation_id: Optional[str] = None
    message: str = ""
    wait_position: Optional[int] = None


class ReleaseRequest(BaseModel):
    """GPU释放请求"""
    task_id: str = Field(..., description="任务ID")
    allocation_id: Optional[str] = Field(None, description="分配ID")


class SlotStateReport(BaseModel):
    """Agent 上报的卡位状态（docs/13 §4.4）。"""

    nodeId: str = Field(..., description="节点 ID，需与 slots.yaml 一致")
    slotId: str = Field(..., description="卡位 ID，如 A3")
    state: str = Field(..., description="FREE / RESERVED / BUSY / FAULT / BORROWED")
    message: Optional[str] = Field(None, description="状态说明，FAULT 时必填")
    deviceCount: Optional[int] = Field(
        None,
        description="容器内 torch.cuda.device_count()；不等于 1 时平台直接置 FAULT",
    )


# ============ API 端点 ============

@router.get(
    "/info",
    response_model=NodeInfoResponse,
    summary="获取GPU节点信息",
    description="获取当前节点的GPU硬件信息"
)
async def get_gpu_info():
    """获取GPU节点信息"""
    detector = get_gpu_detector()

    if not detector.is_available():
        raise HTTPException(
            status_code=503,
            detail="GPU detection not available"
        )

    node_info = detector.get_node_info()

    return NodeInfoResponse(
        hostname=node_info.hostname,
        gpu_count=node_info.gpu_count,
        total_memory_mb=node_info.total_memory_mb,
        cuda_version=node_info.cuda_version,
        driver_version=node_info.driver_version,
        gpus=[
            GPUInfoResponse(
                gpu_index=gpu.gpu_index,
                gpu_name=gpu.gpu_name,
                total_memory_mb=gpu.total_memory_mb,
                free_memory_mb=gpu.free_memory_mb,
                used_memory_mb=gpu.used_memory_mb,
                uuid=gpu.uuid
            )
            for gpu in node_info.gpus
        ]
    )


@router.get(
    "/stats",
    summary="获取GPU实时统计",
    description="获取所有GPU的实时利用率、温度等统计信息"
)
async def get_gpu_stats():
    """获取GPU实时统计"""
    detector = get_gpu_detector()

    if not detector.is_available():
        raise HTTPException(
            status_code=503,
            detail="GPU detection not available"
        )

    stats = detector.get_all_gpu_stats()

    return success_response(
        [
            GPUStatsResponse(
                gpu_index=s.gpu_index,
                utilization_percent=s.utilization_percent,
                memory_used_mb=s.memory_used_mb,
                memory_free_mb=s.memory_free_mb,
                memory_total_mb=s.memory_total_mb,
                temperature_celsius=s.temperature_celsius,
                power_watts=s.power_watts,
                fan_speed_percent=s.fan_speed_percent
            )
            for s in stats
        ]
    )


@router.get(
    "/stats/{gpu_index}",
    response_model=GPUStatsResponse,
    summary="获取指定GPU统计",
    description="获取指定GPU的详细统计信息"
)
async def get_single_gpu_stats(gpu_index: int):
    """获取指定GPU统计"""
    detector = get_gpu_detector()

    if not detector.is_available():
        raise HTTPException(
            status_code=503,
            detail="GPU detection not available"
        )

    try:
        stats = detector.get_gpu_stats(gpu_index)
        return GPUStatsResponse(
            gpu_index=stats.gpu_index,
            utilization_percent=stats.utilization_percent,
            memory_used_mb=stats.memory_used_mb,
            memory_free_mb=stats.memory_free_mb,
            memory_total_mb=stats.memory_total_mb,
            temperature_celsius=stats.temperature_celsius,
            power_watts=stats.power_watts,
            fan_speed_percent=stats.fan_speed_percent
        )
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"GPU {gpu_index} not found or error: {str(e)}"
        )


@router.get(
    "/summary",
    response_model=GPUSummaryResponse,
    summary="获取GPU摘要",
    description="获取GPU资源的整体摘要信息"
)
async def get_gpu_summary():
    """获取GPU摘要"""
    monitor = GPUMonitor()
    summary = await monitor.get_gpu_summary()
    return GPUSummaryResponse(**summary)


@router.get(
    "/health",
    response_model=GPUHealthResponse,
    summary="GPU健康检查",
    description="检查GPU节点的健康状态"
)
async def check_gpu_health():
    """GPU健康检查"""
    monitor = GPUMonitor()
    health = await monitor.check_gpu_node_health()
    return GPUHealthResponse(**health)


@router.post(
    "/allocate",
    response_model=AllocationResponse,
    summary="分配GPU资源",
    description="为任务分配GPU资源（需要管理员权限）"
)
async def allocate_gpu(
    request: AllocationRequest,
    admin_user=Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """分配GPU资源"""
    # 验证优先级
    try:
        priority = TaskPriority(request.priority)
    except ValueError:
        priority = TaskPriority.NORMAL

    allocator = GPUAllocator(db=db)

    result = await allocator.allocate(
        task_id=request.task_id,
        memory_required_mb=request.memory_required_mb,
        priority=priority
    )

    if result.success:
        await db.commit()

    return AllocationResponse(
        success=result.success,
        gpu_node_id=result.gpu_node_id,
        gpu_index=result.gpu_index,
        allocated_memory_mb=result.allocated_memory_mb,
        allocation_id=result.allocation_id,
        message=result.message,
        wait_position=result.wait_position
    )


@router.post(
    "/release",
    summary="释放GPU资源",
    description="释放任务占用的GPU资源（需要管理员权限）"
)
async def release_gpu(
    request: ReleaseRequest,
    admin_user=Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """释放GPU资源"""
    allocator = GPUAllocator(db=db)

    success = await allocator.release(
        task_id=request.task_id,
        allocation_id=request.allocation_id
    )

    if success:
        await db.commit()
        return success_response(message="GPU released successfully")
    else:
        raise HTTPException(
            status_code=400,
            detail="Failed to release GPU"
        )


@router.get(
    "/allocations",
    summary="获取GPU分配统计",
    description="获取当前GPU分配情况（需要认证）"
)
async def get_allocation_stats(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取GPU分配统计"""
    allocator = GPUAllocator(db=db)
    stats = await allocator.get_allocation_stats()
    return success_response(data=stats)


@router.get(
    "/history",
    summary="获取GPU历史数据",
    description="获取GPU的历史监控数据（需要管理员权限）"
)
async def get_gpu_history(
    hours: int = Query(default=1, ge=1, le=24, description="查询小时数"),
    admin_user=Depends(get_admin_user)
):
    """获取GPU历史数据"""
    monitor = GPUMonitor()
    history = await monitor.get_historical_metrics(hours=hours)
    return success_response(data={"history": history, "hours": hours})


# ============ 卡位（slot）端点 ============
#
# 设计口径（docs/09 §5.6、docs/13 §4.4）：
# * 卡位声明来自 slots.yaml，状态权威在 Agent；平台只做消费、展示与准入判断。
# * 平台不提供「改卡位声明」的写接口——声明随镜像包与部署一起版本化（Helm values）,
#   允许在线改等于让调度依据脱离版本控制。
# * 响应体口径：本组端点中 /slots 与 /allocations 已对齐 docs/05 §1.2 统一响应体
#   （success_response）；其余 /gpu/* 端点沿用基线裸返回（已有 response_model 与
#   历史消费方），属待收敛技术债——不要照抄这里的裸返回写法。


@router.get(
    "/slots",
    summary="获取卡位与节点视图",
    description="返回 slots.yaml 声明的节点、卡位与当前状态（docs/06 P-36 算力与队列页数据源）",
)
async def get_slot_view(current_user=Depends(get_current_user)):
    """卡位视图：节点 → 卡位 → 状态。"""
    try:
        registry = load_slot_registry()
    except SlotConfigError as exc:
        raise HTTPException(status_code=500, detail=f"卡位声明不可用: {exc}") from exc

    states = await load_slot_states(registry)
    nodes = slot_view(registry, states)
    return success_response(
        data={
            "schemaVersion": registry.schema_version,
            "source": registry.source,
            "configured": bool(registry.nodes),
            "summary": describe_registry(registry),
            "nodeCount": len(registry.nodes),
            "slotCount": len(registry.slots),
            "schedulableSlotCount": sum(
                1 for node in nodes for slot in node["slots"] if slot["schedulable"]
            ),
            "nodes": nodes,
        }
    )


@router.post(
    "/slots/report",
    summary="接收 Agent 卡位状态上报",
    description="drp-node-agent 主动上报卡位状态（辅通道 C，需携带上报 token）",
)
async def report_slot_state(
    payload: SlotStateReport,
    x_drp_agent_token: Optional[str] = Header(default=None, alias="X-DRP-Agent-Token"),
):
    """Agent 上报卡位状态。

    该端点不走用户鉴权（Agent 不是平台用户），改用独立上报 token 校验；
    ``DRP_NODE_AGENT_REPORT_TOKEN`` 未配置时直接 503——**默认关闭**，
    避免内网裸奔部署被随意置 FAULT 造成拒绝服务。
    """
    expected = (settings.DRP_NODE_AGENT_REPORT_TOKEN or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="未配置 DRP_NODE_AGENT_REPORT_TOKEN，卡位状态上报通道未启用",
        )
    provided = (x_drp_agent_token or "").strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="卡位状态上报凭据无效")

    try:
        registry = load_slot_registry()
        slot = registry.find(payload.nodeId, payload.slotId)
        if slot is None:
            raise HTTPException(
                status_code=404,
                detail=f"卡位未在 slots.yaml 中声明: {payload.nodeId}/{payload.slotId}",
            )
        record = await record_slot_state(
            node_id=payload.nodeId,
            slot_id=payload.slotId,
            state=payload.state,
            message=payload.message,
            device_count=payload.deviceCount,
        )
    except SlotConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if record["state"] not in SLOT_STATES:  # pragma: no cover - record_slot_state 已校验
        raise HTTPException(status_code=422, detail=f"不支持的卡位状态: {record['state']}")

    logger.info(
        "Slot state reported: node=%s slot=%s state=%s device_count=%s",
        payload.nodeId,
        payload.slotId,
        record["state"],
        payload.deviceCount,
    )
    return record
