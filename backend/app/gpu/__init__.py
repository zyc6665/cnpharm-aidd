# backend/app/gpu/__init__.py
"""GPU资源管理模块"""

from app.gpu.detector import GPUDetector, GPUInfo
from app.gpu.allocator import GPUAllocator, AllocationResult
from app.gpu.monitor import GPUMonitor
from app.gpu.shortage_handler import GPUShortageHandler, ShortageAction, get_shortage_handler
from app.gpu.degradation_strategy import (
    GPUDegradationStrategy,
    DegradationMode,
    DegradationResult,
    get_degradation_strategy
)

__all__ = [
    "GPUDetector",
    "GPUInfo",
    "GPUAllocator",
    "AllocationResult",
    "GPUMonitor",
    "GPUShortageHandler",
    "ShortageAction",
    "get_shortage_handler",
    "GPUDegradationStrategy",
    "DegradationMode",
    "DegradationResult",
    "get_degradation_strategy",
]
