# backend/app/gpu/degradation_strategy.py
"""GPU降级策略模块

根据详细设计说明书 8.2 节实现。
提供GPU资源不足时的降级策略。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class DegradationMode(str, Enum):
    """降级模式"""
    NONE = "none"                       # 无降级
    CPU_FALLBACK = "cpu_fallback"       # 降级到CPU
    BATCH_REDUCTION = "batch_reduction" # 减小批次大小
    PRECISION_REDUCTION = "precision"   # 降低精度
    FEATURE_REDUCTION = "feature"       # 减少特征
    QUEUE_WAIT = "queue_wait"           # 排队等待


class CPUFallbackMode(str, Enum):
    """CPU降级模式"""
    FULL = "full"               # 完全使用CPU
    HYBRID = "hybrid"           # CPU+GPU混合
    PARTIAL = "partial"         # 部分使用CPU


@dataclass
class DegradationConfig:
    """降级配置"""
    mode: DegradationMode
    cpu_fallback_mode: Optional[CPUFallbackMode] = None
    batch_size_factor: float = 1.0      # 批次大小倍数 (0-1)
    precision: str = "fp32"              # 精度: fp32, fp16, int8
    enabled_features: List[str] = field(default_factory=list)
    max_wait_seconds: int = 300         # 最大等待时间
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DegradationResult:
    """降级结果"""
    success: bool
    original_mode: DegradationMode
    applied_mode: DegradationMode
    config: DegradationConfig
    performance_impact: str              # 性能影响描述
    message: str


class ToolCapability:
    """工具能力描述"""

    def __init__(
        self,
        tool_id: str,
        requires_gpu: bool = False,
        supports_cpu_fallback: bool = False,
        supports_batch_reduction: bool = False,
        supports_precision_reduction: bool = False,
        min_batch_size: int = 1,
        default_batch_size: int = 32,
        supported_precisions: List[str] = None,
        gpu_memory_mb: int = 4096,
        cpu_memory_mb: int = 8192,
        estimated_gpu_time_seconds: int = 60,
        estimated_cpu_time_seconds: int = 300
    ):
        self.tool_id = tool_id
        self.requires_gpu = requires_gpu
        self.supports_cpu_fallback = supports_cpu_fallback
        self.supports_batch_reduction = supports_batch_reduction
        self.supports_precision_reduction = supports_precision_reduction
        self.min_batch_size = min_batch_size
        self.default_batch_size = default_batch_size
        self.supported_precisions = supported_precisions or ["fp32"]
        self.gpu_memory_mb = gpu_memory_mb
        self.cpu_memory_mb = cpu_memory_mb
        self.estimated_gpu_time_seconds = estimated_gpu_time_seconds
        self.estimated_cpu_time_seconds = estimated_cpu_time_seconds


class GPUDegradationStrategy:
    """GPU降级策略

    根据工具能力和系统状态，选择合适的降级策略。
    """

    # 降级优先级（从轻到重）
    DEGRADATION_PRIORITY = [
        DegradationMode.BATCH_REDUCTION,
        DegradationMode.PRECISION_REDUCTION,
        DegradationMode.CPU_FALLBACK,
        DegradationMode.QUEUE_WAIT
    ]

    def __init__(
        self,
        prefer_cpu_fallback: bool = True,
        max_performance_loss: float = 0.5,  # 最大允许50%性能损失
        enable_auto_batch_reduction: bool = True,
        min_batch_factor: float = 0.25      # 最小批次因子
    ):
        """初始化降级策略

        Args:
            prefer_cpu_fallback: 是否优先选择CPU降级
            max_performance_loss: 最大允许的性能损失比例
            enable_auto_batch_reduction: 是否启用自动批次减小
            min_batch_factor: 最小批次因子
        """
        self.prefer_cpu_fallback = prefer_cpu_fallback
        self.max_performance_loss = max_performance_loss
        self.enable_auto_batch_reduction = enable_auto_batch_reduction
        self.min_batch_factor = min_batch_factor

        # 工具能力缓存
        self._tool_capabilities: Dict[str, ToolCapability] = {}

    def register_tool_capability(self, capability: ToolCapability) -> None:
        """注册工具能力

        Args:
            capability: 工具能力
        """
        self._tool_capabilities[capability.tool_id] = capability
        logger.info(f"Registered tool capability: {capability.tool_id}")

    def get_tool_capability(self, tool_id: str) -> Optional[ToolCapability]:
        """获取工具能力

        Args:
            tool_id: 工具ID

        Returns:
            Optional[ToolCapability]: 工具能力
        """
        return self._tool_capabilities.get(tool_id)

    async def try_cpu_fallback(
        self,
        tool_id: str,
        task_params: Dict[str, Any]
    ) -> DegradationResult:
        """尝试CPU降级

        Args:
            tool_id: 工具ID
            task_params: 任务参数

        Returns:
            DegradationResult: 降级结果
        """
        capability = self.get_tool_capability(tool_id)

        if capability is None:
            # 没有工具能力信息，假设不支持降级
            return DegradationResult(
                success=False,
                original_mode=DegradationMode.NONE,
                applied_mode=DegradationMode.NONE,
                config=DegradationConfig(mode=DegradationMode.NONE),
                performance_impact="unknown",
                message="Tool capability information not available"
            )

        if not capability.supports_cpu_fallback:
            return DegradationResult(
                success=False,
                original_mode=DegradationMode.NONE,
                applied_mode=DegradationMode.NONE,
                config=DegradationConfig(mode=DegradationMode.NONE),
                performance_impact="not_applicable",
                message="Tool does not support CPU fallback"
            )

        # 计算性能影响
        if capability.estimated_gpu_time_seconds > 0:
            slowdown = capability.estimated_cpu_time_seconds / capability.estimated_gpu_time_seconds
        else:
            slowdown = 5.0  # 默认假设5倍慢

        performance_loss = (slowdown - 1) / slowdown  # 转换为损失比例

        if performance_loss > self.max_performance_loss:
            performance_impact = f"severe ({slowdown:.1f}x slower)"
        elif performance_loss > 0.3:
            performance_impact = f"moderate ({slowdown:.1f}x slower)"
        else:
            performance_impact = f"minimal ({slowdown:.1f}x slower)"

        config = DegradationConfig(
            mode=DegradationMode.CPU_FALLBACK,
            cpu_fallback_mode=CPUFallbackMode.FULL,
            metadata={
                "expected_slowdown": slowdown,
                "cpu_memory_required_mb": capability.cpu_memory_mb,
                "estimated_time_seconds": capability.estimated_cpu_time_seconds
            }
        )

        logger.info(f"CPU fallback configured for tool {tool_id}: {slowdown:.1f}x slowdown expected")

        return DegradationResult(
            success=True,
            original_mode=DegradationMode.NONE,
            applied_mode=DegradationMode.CPU_FALLBACK,
            config=config,
            performance_impact=performance_impact,
            message=f"Task will run on CPU ({slowdown:.1f}x slower than GPU)"
        )

    async def reduce_batch_size(
        self,
        tool_id: str,
        current_batch_size: int,
        available_memory_mb: int
    ) -> DegradationResult:
        """减小批次大小

        Args:
            tool_id: 工具ID
            current_batch_size: 当前批次大小
            available_memory_mb: 可用内存 (MB)

        Returns:
            DegradationResult: 降级结果
        """
        capability = self.get_tool_capability(tool_id)

        if capability is None or not capability.supports_batch_reduction:
            return DegradationResult(
                success=False,
                original_mode=DegradationMode.NONE,
                applied_mode=DegradationMode.NONE,
                config=DegradationConfig(mode=DegradationMode.NONE),
                performance_impact="not_applicable",
                message="Tool does not support batch size reduction"
            )

        # 计算新的批次大小
        memory_per_sample = capability.gpu_memory_mb / capability.default_batch_size
        new_batch_size = int(available_memory_mb / memory_per_sample)
        new_batch_size = max(new_batch_size, capability.min_batch_size)

        if new_batch_size >= current_batch_size:
            return DegradationResult(
                success=False,
                original_mode=DegradationMode.NONE,
                applied_mode=DegradationMode.NONE,
                config=DegradationConfig(mode=DegradationMode.NONE),
                performance_impact="not_needed",
                message="Batch size reduction not needed"
            )

        batch_factor = new_batch_size / current_batch_size
        if batch_factor < self.min_batch_factor:
            batch_factor = self.min_batch_factor
            new_batch_size = int(current_batch_size * batch_factor)

        # 性能影响估算
        iterations_increase = current_batch_size / new_batch_size
        if iterations_increase > 4:
            performance_impact = f"severe ({iterations_increase:.1f}x more iterations)"
        elif iterations_increase > 2:
            performance_impact = f"moderate ({iterations_increase:.1f}x more iterations)"
        else:
            performance_impact = f"minimal ({iterations_increase:.1f}x more iterations)"

        config = DegradationConfig(
            mode=DegradationMode.BATCH_REDUCTION,
            batch_size_factor=batch_factor,
            metadata={
                "original_batch_size": current_batch_size,
                "new_batch_size": new_batch_size,
                "iterations_increase": iterations_increase
            }
        )

        logger.info(
            f"Batch size reduced for tool {tool_id}: "
            f"{current_batch_size} -> {new_batch_size}"
        )

        return DegradationResult(
            success=True,
            original_mode=DegradationMode.NONE,
            applied_mode=DegradationMode.BATCH_REDUCTION,
            config=config,
            performance_impact=performance_impact,
            message=f"Batch size reduced from {current_batch_size} to {new_batch_size}"
        )

    async def reduce_precision(
        self,
        tool_id: str,
        current_precision: str = "fp32"
    ) -> DegradationResult:
        """降低计算精度

        Args:
            tool_id: 工具ID
            current_precision: 当前精度

        Returns:
            DegradationResult: 降级结果
        """
        capability = self.get_tool_capability(tool_id)

        if capability is None or not capability.supports_precision_reduction:
            return DegradationResult(
                success=False,
                original_mode=DegradationMode.NONE,
                applied_mode=DegradationMode.NONE,
                config=DegradationConfig(mode=DegradationMode.NONE),
                performance_impact="not_applicable",
                message="Tool does not support precision reduction"
            )

        # 精度降级顺序
        precision_order = ["fp32", "fp16", "int8"]
        current_index = precision_order.index(current_precision) if current_precision in precision_order else 0

        # 找到下一个支持的精度
        new_precision = None
        for precision in precision_order[current_index + 1:]:
            if precision in capability.supported_precisions:
                new_precision = precision
                break

        if new_precision is None:
            return DegradationResult(
                success=False,
                original_mode=DegradationMode.NONE,
                applied_mode=DegradationMode.NONE,
                config=DegradationConfig(mode=DegradationMode.NONE),
                performance_impact="not_applicable",
                message="No lower precision available"
            )

        # 性能影响
        memory_savings = {
            "fp32->fp16": 0.5,
            "fp16->int8": 0.5,
            "fp32->int8": 0.25
        }
        key = f"{current_precision}->{new_precision}"
        savings = memory_savings.get(key, 0.5)

        performance_impact = f"minimal (memory reduced by {(1-savings)*100:.0f}%)"

        config = DegradationConfig(
            mode=DegradationMode.PRECISION_REDUCTION,
            precision=new_precision,
            metadata={
                "original_precision": current_precision,
                "new_precision": new_precision,
                "memory_savings": savings
            }
        )

        logger.info(
            f"Precision reduced for tool {tool_id}: "
            f"{current_precision} -> {new_precision}"
        )

        return DegradationResult(
            success=True,
            original_mode=DegradationMode.NONE,
            applied_mode=DegradationMode.PRECISION_REDUCTION,
            config=config,
            performance_impact=performance_impact,
            message=f"Precision reduced from {current_precision} to {new_precision}"
        )

    async def select_best_strategy(
        self,
        tool_id: str,
        task_params: Dict[str, Any],
        available_gpu_memory_mb: int = 0,
        queue_wait_seconds: int = 0
    ) -> DegradationResult:
        """选择最佳降级策略

        Args:
            tool_id: 工具ID
            task_params: 任务参数
            available_gpu_memory_mb: 可用GPU内存
            queue_wait_seconds: 预计排队等待时间

        Returns:
            DegradationResult: 降级结果
        """
        capability = self.get_tool_capability(tool_id)

        if capability is None:
            # 没有能力信息，默认排队等待
            return DegradationResult(
                success=True,
                original_mode=DegradationMode.NONE,
                applied_mode=DegradationMode.QUEUE_WAIT,
                config=DegradationConfig(
                    mode=DegradationMode.QUEUE_WAIT,
                    max_wait_seconds=queue_wait_seconds
                ),
                performance_impact="delayed execution",
                message="Queued waiting for GPU resources"
            )

        # 如果有足够的GPU内存，不需要降级
        if available_gpu_memory_mb >= capability.gpu_memory_mb:
            return DegradationResult(
                success=True,
                original_mode=DegradationMode.NONE,
                applied_mode=DegradationMode.NONE,
                config=DegradationConfig(mode=DegradationMode.NONE),
                performance_impact="none",
                message="Sufficient GPU resources available"
            )

        results = []

        # 尝试各种降级策略
        for mode in self.DEGRADATION_PRIORITY:
            if mode == DegradationMode.BATCH_REDUCTION:
                if self.enable_auto_batch_reduction:
                    result = await self.reduce_batch_size(
                        tool_id,
                        task_params.get("batch_size", capability.default_batch_size),
                        available_gpu_memory_mb
                    )
                    if result.success:
                        results.append(result)

            elif mode == DegradationMode.PRECISION_REDUCTION:
                result = await self.reduce_precision(
                    tool_id,
                    task_params.get("precision", "fp32")
                )
                if result.success:
                    results.append(result)

            elif mode == DegradationMode.CPU_FALLBACK:
                if self.prefer_cpu_fallback:
                    result = await self.try_cpu_fallback(tool_id, task_params)
                    if result.success:
                        results.append(result)

        # 选择最佳结果（优先选择性能影响最小的）
        if results:
            # 简单选择第一个成功的（按优先级顺序）
            return results[0]

        # 所有策略都失败，排队等待
        return DegradationResult(
            success=True,
            original_mode=DegradationMode.NONE,
            applied_mode=DegradationMode.QUEUE_WAIT,
            config=DegradationConfig(
                mode=DegradationMode.QUEUE_WAIT,
                max_wait_seconds=queue_wait_seconds
            ),
            performance_impact="delayed execution",
            message="No degradation options available, queued for GPU"
        )

    def get_degradation_info(
        self,
        tool_id: str
    ) -> Dict[str, Any]:
        """获取工具的降级信息

        Args:
            tool_id: 工具ID

        Returns:
            Dict: 降级信息
        """
        capability = self.get_tool_capability(tool_id)

        if capability is None:
            return {
                "tool_id": tool_id,
                "degradation_supported": False,
                "available_modes": []
            }

        available_modes = []
        if capability.supports_cpu_fallback:
            available_modes.append(DegradationMode.CPU_FALLBACK.value)
        if capability.supports_batch_reduction:
            available_modes.append(DegradationMode.BATCH_REDUCTION.value)
        if capability.supports_precision_reduction:
            available_modes.append(DegradationMode.PRECISION_REDUCTION.value)

        return {
            "tool_id": tool_id,
            "degradation_supported": len(available_modes) > 0,
            "available_modes": available_modes,
            "requires_gpu": capability.requires_gpu,
            "gpu_memory_mb": capability.gpu_memory_mb,
            "cpu_memory_mb": capability.cpu_memory_mb,
            "supported_precisions": capability.supported_precisions,
            "estimated_cpu_slowdown": (
                capability.estimated_cpu_time_seconds /
                capability.estimated_gpu_time_seconds
                if capability.estimated_gpu_time_seconds > 0 else None
            )
        }


# 全局实例
_degradation_strategy: Optional[GPUDegradationStrategy] = None


def get_degradation_strategy() -> GPUDegradationStrategy:
    """获取GPU降级策略单例

    Returns:
        GPUDegradationStrategy: 策略实例
    """
    global _degradation_strategy
    if _degradation_strategy is None:
        _degradation_strategy = GPUDegradationStrategy()
    return _degradation_strategy
