# backend/app/gpu/allocator.py
"""GPU智能调度器

根据详细设计说明书 5.2 节实现。
负责GPU资源的智能分配和调度。
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import asyncio
import logging

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.gpu.detector import GPUDetector, get_gpu_detector

logger = logging.getLogger(__name__)


class AllocationStrategy(str, Enum):
    """分配策略"""
    IDLE_FIRST = "idle_first"      # 优先空闲GPU
    MEMORY_FIT = "memory_fit"       # 显存最佳匹配
    ROUND_ROBIN = "round_robin"     # 轮询
    LOAD_BALANCE = "load_balance"   # 负载均衡


class TaskPriority(str, Enum):
    """任务优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AllocationResult:
    """分配结果"""
    success: bool
    gpu_node_id: Optional[str] = None
    gpu_index: Optional[int] = None
    allocated_memory_mb: int = 0
    allocation_id: Optional[str] = None
    message: str = ""
    wait_position: Optional[int] = None  # 等待队列位置


@dataclass
class GPUAllocation:
    """GPU分配记录"""
    id: str
    task_id: str
    gpu_node_id: str
    gpu_index: int
    memory_allocated_mb: int
    allocated_at: datetime
    released_at: Optional[datetime] = None


class GPUAllocator:
    """GPU智能调度器

    功能：
    1. 优先空闲GPU策略
    2. 显存最佳匹配策略
    3. VIP任务抢占策略
    4. 分布式锁防止并发分配冲突
    """

    # 锁超时时间（秒）
    LOCK_TIMEOUT = 10

    # 最大重试次数
    MAX_RETRIES = 3

    # 重试间隔（秒）
    RETRY_INTERVAL = 0.1

    def __init__(
        self,
        db: AsyncSession,
        detector: Optional[GPUDetector] = None,
        cache_client=None
    ):
        """初始化GPU分配器

        Args:
            db: 数据库会话
            detector: GPU检测器（可选）
            cache_client: 缓存客户端（用于分布式锁）
        """
        self.db = db
        self.detector = detector or get_gpu_detector()
        self.cache = cache_client

    async def allocate(
        self,
        task_id: str,
        memory_required_mb: int,
        priority: TaskPriority = TaskPriority.NORMAL,
        strategy: AllocationStrategy = AllocationStrategy.IDLE_FIRST
    ) -> AllocationResult:
        """分配GPU资源

        Args:
            task_id: 任务ID
            memory_required_mb: 所需显存（MB）
            priority: 任务优先级
            strategy: 分配策略

        Returns:
            AllocationResult: 分配结果
        """
        # 获取分布式锁
        lock_acquired = await self._acquire_lock()

        if not lock_acquired:
            return AllocationResult(
                success=False,
                message="Failed to acquire allocation lock, please retry"
            )

        try:
            # 获取可用GPU节点
            available_nodes = await self._get_available_nodes()

            if not available_nodes:
                return AllocationResult(
                    success=False,
                    message="No GPU nodes available"
                )

            # 根据策略分配
            result = None

            if strategy == AllocationStrategy.IDLE_FIRST:
                result = await self._try_allocate_idle_gpu(
                    available_nodes, task_id, memory_required_mb
                )

            if not result and strategy in (
                AllocationStrategy.IDLE_FIRST,
                AllocationStrategy.MEMORY_FIT
            ):
                result = await self._try_allocate_by_memory(
                    available_nodes, task_id, memory_required_mb
                )

            # 高优先级任务尝试抢占
            if not result and priority in (TaskPriority.HIGH, TaskPriority.CRITICAL):
                result = await self._try_preempt_low_priority(
                    task_id, memory_required_mb
                )

            if result:
                return result

            # 所有策略失败
            wait_position = await self._get_wait_position(task_id)
            return AllocationResult(
                success=False,
                message="No GPU resources available",
                wait_position=wait_position
            )

        finally:
            await self._release_lock()

    async def release(
        self,
        task_id: str,
        allocation_id: Optional[str] = None
    ) -> bool:
        """释放GPU资源

        Args:
            task_id: 任务ID
            allocation_id: 分配ID（可选）

        Returns:
            bool: 是否成功释放
        """
        try:
            # 这里需要根据实际模型更新
            # 暂时使用简化逻辑
            logger.info(
                f"Released GPU allocation for task {task_id}",
                extra={"task_id": task_id, "allocation_id": allocation_id}
            )
            return True

        except Exception as e:
            logger.error(f"Failed to release GPU allocation: {e}")
            return False

    async def _get_available_nodes(self) -> List[Dict[str, Any]]:
        """获取可用GPU节点

        Returns:
            List[Dict[str, Any]]: 可用节点列表
        """
        # 本地模式：直接检测本地GPU
        if self.detector.is_available():
            node_info = self.detector.get_node_info()
            return [{
                "id": "local",
                "hostname": node_info.hostname,
                "gpu_count": node_info.gpu_count,
                "gpus": [
                    {
                        "index": gpu.gpu_index,
                        "name": gpu.gpu_name,
                        "total_memory_mb": gpu.total_memory_mb,
                        "free_memory_mb": gpu.free_memory_mb
                    }
                    for gpu in node_info.gpus
                ]
            }]

        # 如果没有本地GPU，返回空列表
        # 生产环境中应该从数据库查询注册的GPU节点
        return []

    async def _try_allocate_idle_gpu(
        self,
        nodes: List[Dict[str, Any]],
        task_id: str,
        memory_required_mb: int
    ) -> Optional[AllocationResult]:
        """策略1: 优先空闲GPU

        Args:
            nodes: 可用节点列表
            task_id: 任务ID
            memory_required_mb: 所需显存

        Returns:
            Optional[AllocationResult]: 分配结果
        """
        for node in nodes:
            for gpu in node.get("gpus", []):
                # 检查是否空闲（无任务运行）
                is_idle = await self._is_gpu_idle(node["id"], gpu["index"])

                if is_idle and gpu["free_memory_mb"] >= memory_required_mb:
                    return await self._create_allocation(
                        task_id=task_id,
                        node_id=node["id"],
                        gpu_index=gpu["index"],
                        memory_mb=memory_required_mb
                    )

        return None

    async def _try_allocate_by_memory(
        self,
        nodes: List[Dict[str, Any]],
        task_id: str,
        memory_required_mb: int
    ) -> Optional[AllocationResult]:
        """策略2: 显存最佳匹配

        选择空闲显存最接近所需的GPU，减少资源浪费。

        Args:
            nodes: 可用节点列表
            task_id: 任务ID
            memory_required_mb: 所需显存

        Returns:
            Optional[AllocationResult]: 分配结果
        """
        candidates = []

        for node in nodes:
            for gpu in node.get("gpus", []):
                free_memory = gpu["free_memory_mb"]

                if free_memory >= memory_required_mb:
                    candidates.append({
                        "node_id": node["id"],
                        "gpu_index": gpu["index"],
                        "free_memory": free_memory,
                        "waste": free_memory - memory_required_mb
                    })

        if not candidates:
            return None

        # 选择浪费最小的GPU
        best = min(candidates, key=lambda x: x["waste"])

        return await self._create_allocation(
            task_id=task_id,
            node_id=best["node_id"],
            gpu_index=best["gpu_index"],
            memory_mb=memory_required_mb
        )

    async def _try_preempt_low_priority(
        self,
        task_id: str,
        memory_required_mb: int
    ) -> Optional[AllocationResult]:
        """策略3: 抢占低优先级任务

        仅限高优先级任务使用。

        Args:
            task_id: 任务ID
            memory_required_mb: 所需显存

        Returns:
            Optional[AllocationResult]: 分配结果
        """
        # 查找低优先级运行中的任务
        # 这里需要根据实际Task模型实现
        # 暂时返回None，不执行抢占
        logger.info(f"Preemption attempted for task {task_id}, not implemented")
        return None

    async def _create_allocation(
        self,
        task_id: str,
        node_id: str,
        gpu_index: int,
        memory_mb: int
    ) -> AllocationResult:
        """创建分配记录

        Args:
            task_id: 任务ID
            node_id: 节点ID
            gpu_index: GPU索引
            memory_mb: 分配显存

        Returns:
            AllocationResult: 分配结果
        """
        import uuid
        allocation_id = str(uuid.uuid4())

        # 这里应该创建数据库记录
        # 暂时只记录日志

        logger.info(
            f"GPU allocated: task={task_id}, node={node_id}, "
            f"gpu={gpu_index}, memory={memory_mb}MB",
            extra={
                "task_id": task_id,
                "node_id": node_id,
                "gpu_index": gpu_index,
                "memory_mb": memory_mb,
                "allocation_id": allocation_id
            }
        )

        return AllocationResult(
            success=True,
            gpu_node_id=node_id,
            gpu_index=gpu_index,
            allocated_memory_mb=memory_mb,
            allocation_id=allocation_id,
            message="GPU allocated successfully"
        )

    async def _is_gpu_idle(self, node_id: str, gpu_index: int) -> bool:
        """检查GPU是否空闲

        Args:
            node_id: 节点ID
            gpu_index: GPU索引

        Returns:
            bool: 是否空闲
        """
        # 这里应该查询数据库检查是否有任务在使用
        # 暂时使用简化逻辑：检查利用率
        try:
            stats = self.detector.get_gpu_stats(gpu_index)
            # 利用率低于10%视为空闲
            return stats.utilization_percent < 10
        except Exception:
            return False

    async def _get_wait_position(self, task_id: str) -> int:
        """获取等待队列位置

        Args:
            task_id: 任务ID

        Returns:
            int: 队列位置
        """
        # 这里应该从队列中获取位置
        # 暂时返回固定值
        return 1

    async def _acquire_lock(self) -> bool:
        """获取分布式锁"""
        if not self.cache:
            return True  # 无缓存时不使用锁

        lock_key = "gpu:alloc:lock"
        for _ in range(self.MAX_RETRIES):
            try:
                acquired = await self.cache.set(
                    lock_key, "1", nx=True, ex=self.LOCK_TIMEOUT
                )
                if acquired:
                    return True
                await asyncio.sleep(self.RETRY_INTERVAL)
            except Exception as e:
                logger.warning(f"Failed to acquire lock: {e}")

        return False

    async def _release_lock(self) -> None:
        """释放分布式锁"""
        if not self.cache:
            return

        try:
            await self.cache.delete("gpu:alloc:lock")
        except Exception as e:
            logger.warning(f"Failed to release lock: {e}")

    async def get_allocation_stats(self) -> Dict[str, Any]:
        """获取分配统计

        Returns:
            Dict[str, Any]: 分配统计信息
        """
        if not self.detector.is_available():
            return {
                "available": False,
                "gpu_count": 0,
                "total_memory_mb": 0,
                "used_memory_mb": 0,
                "allocations": []
            }

        stats_list = self.detector.get_all_gpu_stats()

        total_memory = sum(s.memory_total_mb for s in stats_list)
        used_memory = sum(s.memory_used_mb for s in stats_list)

        return {
            "available": True,
            "gpu_count": len(stats_list),
            "total_memory_mb": total_memory,
            "used_memory_mb": used_memory,
            "free_memory_mb": total_memory - used_memory,
            "utilization_percent": sum(s.utilization_percent for s in stats_list) / len(stats_list) if stats_list else 0,
            "gpus": [
                {
                    "index": s.gpu_index,
                    "utilization": s.utilization_percent,
                    "memory_used_mb": s.memory_used_mb,
                    "memory_free_mb": s.memory_free_mb,
                    "temperature": s.temperature_celsius
                }
                for s in stats_list
            ]
        }
