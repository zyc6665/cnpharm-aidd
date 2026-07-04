# backend/app/api/v1/gpu.py
"""GPU资源管理接口

提供GPU资源查询、分配、监控等API端点。
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user, get_admin_user
from app.gpu.detector import get_gpu_detector
from app.gpu.allocator import GPUAllocator, TaskPriority
from app.gpu.monitor import GPUMonitor

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
    response_model=List[GPUStatsResponse],
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

    return [
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
    description="为任务分配GPU资源（需要认证）"
)
async def allocate_gpu(
    request: AllocationRequest,
    current_user=Depends(get_current_user)
):
    """分配GPU资源"""
    # 验证优先级
    try:
        priority = TaskPriority(request.priority)
    except ValueError:
        priority = TaskPriority.NORMAL

    # 创建分配器（需要数据库会话，这里简化处理）
    allocator = GPUAllocator(db=None)

    result = await allocator.allocate(
        task_id=request.task_id,
        memory_required_mb=request.memory_required_mb,
        priority=priority
    )

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
    description="释放任务占用的GPU资源（需要认证）"
)
async def release_gpu(
    request: ReleaseRequest,
    current_user=Depends(get_current_user)
):
    """释放GPU资源"""
    allocator = GPUAllocator(db=None)

    success = await allocator.release(
        task_id=request.task_id,
        allocation_id=request.allocation_id
    )

    if success:
        return {"message": "GPU released successfully"}
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
    current_user=Depends(get_current_user)
):
    """获取GPU分配统计"""
    allocator = GPUAllocator(db=None)
    stats = await allocator.get_allocation_stats()
    return stats


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
    return {"history": history, "hours": hours}
