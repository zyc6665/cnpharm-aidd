# backend/app/gpu/detector.py
"""GPU检测器

根据详细设计说明书 5.1 节实现。
负责检测GPU设备、获取GPU状态信息。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
import platform

from app.common.time import utcnow

logger = logging.getLogger(__name__)

# 尝试导入NVML
try:
    import pynvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False
    logger.warning("pynvml not available, GPU detection will be disabled")


@dataclass
class GPUInfo:
    """GPU信息"""
    gpu_index: int
    gpu_name: str
    total_memory_mb: int
    free_memory_mb: int
    used_memory_mb: int
    uuid: Optional[str] = None


@dataclass
class GPUStats:
    """GPU详细统计"""
    gpu_index: int
    utilization_percent: int
    memory_used_mb: int
    memory_free_mb: int
    memory_total_mb: int
    temperature_celsius: int
    power_watts: int
    fan_speed_percent: Optional[int] = None
    timestamp: datetime = field(default_factory=utcnow)


@dataclass
class NodeInfo:
    """节点信息"""
    hostname: str
    gpu_count: int
    total_memory_mb: int
    cuda_version: str
    driver_version: str
    gpus: List[GPUInfo]


class GPUDetector:
    """GPU检测器

    功能：
    1. 检测本地GPU设备
    2. 获取GPU详细统计
    3. 注册GPU节点
    """

    def __init__(self):
        """初始化GPU检测器"""
        self.initialized = False
        self._handle_cache: Dict[int, Any] = {}

        if HAS_NVML:
            try:
                pynvml.nvmlInit()
                self.initialized = True
                logger.info("NVML initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize NVML: {e}")
        else:
            logger.warning("NVML library not available")

    def detect_gpus(self) -> List[GPUInfo]:
        """检测GPU设备

        Returns:
            List[GPUInfo]: GPU信息列表
        """
        if not self.initialized:
            return []

        gpus = []
        try:
            device_count = pynvml.nvmlDeviceGetCount()

            for i in range(device_count):
                try:
                    handle = self._get_handle(i)
                    name = pynvml.nvmlDeviceGetName(handle)
                    if isinstance(name, bytes):
                        name = name.decode('utf-8')

                    memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)

                    try:
                        uuid = pynvml.nvmlDeviceGetUUID(handle)
                        if isinstance(uuid, bytes):
                            uuid = uuid.decode('utf-8')
                    except Exception:
                        uuid = None

                    gpu_info = GPUInfo(
                        gpu_index=i,
                        gpu_name=name,
                        total_memory_mb=memory_info.total // 1024 // 1024,
                        free_memory_mb=memory_info.free // 1024 // 1024,
                        used_memory_mb=memory_info.used // 1024 // 1024,
                        uuid=uuid
                    )
                    gpus.append(gpu_info)

                except Exception as e:
                    logger.error(f"Failed to get info for GPU {i}: {e}")

        except Exception as e:
            logger.error(f"Failed to detect GPUs: {e}")

        return gpus

    def get_gpu_stats(self, gpu_index: int) -> GPUStats:
        """获取GPU详细统计

        Args:
            gpu_index: GPU索引

        Returns:
            GPUStats: GPU统计信息

        Raises:
            RuntimeError: NVML未初始化或GPU不存在
        """
        if not self.initialized:
            raise RuntimeError("NVML not initialized")

        try:
            handle = self._get_handle(gpu_index)
            memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)

            # 温度
            try:
                temperature = pynvml.nvmlDeviceGetTemperature(
                    handle, pynvml.NVML_TEMPERATURE_GPU
                )
            except Exception:
                temperature = 0

            # 功率
            try:
                power = pynvml.nvmlDeviceGetPowerUsage(handle) // 1000  # mW -> W
            except Exception:
                power = 0

            # 风扇转速
            try:
                fan_speed = pynvml.nvmlDeviceGetFanSpeed(handle)
            except Exception:
                fan_speed = None

            return GPUStats(
                gpu_index=gpu_index,
                utilization_percent=utilization.gpu,
                memory_used_mb=memory_info.used // 1024 // 1024,
                memory_free_mb=memory_info.free // 1024 // 1024,
                memory_total_mb=memory_info.total // 1024 // 1024,
                temperature_celsius=temperature,
                power_watts=power,
                fan_speed_percent=fan_speed
            )

        except Exception as e:
            logger.error(f"Failed to get stats for GPU {gpu_index}: {e}")
            raise RuntimeError(f"Failed to get GPU stats: {e}")

    def get_all_gpu_stats(self) -> List[GPUStats]:
        """获取所有GPU的统计信息

        Returns:
            List[GPUStats]: GPU统计列表
        """
        stats = []
        gpus = self.detect_gpus()

        for gpu in gpus:
            try:
                stat = self.get_gpu_stats(gpu.gpu_index)
                stats.append(stat)
            except Exception as e:
                logger.warning(f"Failed to get stats for GPU {gpu.gpu_index}: {e}")

        return stats

    def get_node_info(self, hostname: Optional[str] = None) -> NodeInfo:
        """获取节点信息

        Args:
            hostname: 主机名，如果不提供则自动获取

        Returns:
            NodeInfo: 节点信息
        """
        if hostname is None:
            hostname = platform.node()

        gpus = self.detect_gpus()

        # 获取CUDA和驱动版本
        cuda_version = "N/A"
        driver_version = "N/A"

        if self.initialized:
            try:
                cuda_ver = pynvml.nvmlSystemGetCudaDriverVersion()
                cuda_version = f"{cuda_ver // 1000}.{(cuda_ver % 1000) // 10}"
            except Exception as e:
                logger.debug("Failed to read CUDA driver version: %s", e)

            try:
                driver_version = pynvml.nvmlSystemGetDriverVersion()
                if isinstance(driver_version, bytes):
                    driver_version = driver_version.decode('utf-8')
            except Exception as e:
                logger.debug("Failed to read NVIDIA driver version: %s", e)

        total_memory = sum(gpu.total_memory_mb for gpu in gpus)

        return NodeInfo(
            hostname=hostname,
            gpu_count=len(gpus),
            total_memory_mb=total_memory,
            cuda_version=cuda_version,
            driver_version=driver_version,
            gpus=gpus
        )

    def check_gpu_health(self, gpu_index: int) -> Dict[str, Any]:
        """检查GPU健康状态

        Args:
            gpu_index: GPU索引

        Returns:
            Dict[str, Any]: 健康检查结果
        """
        health = {
            "gpu_index": gpu_index,
            "healthy": True,
            "issues": [],
            "stats": None
        }

        try:
            stats = self.get_gpu_stats(gpu_index)
            health["stats"] = {
                "utilization": stats.utilization_percent,
                "temperature": stats.temperature_celsius,
                "memory_used_percent": (
                    stats.memory_used_mb / stats.memory_total_mb * 100
                    if stats.memory_total_mb > 0 else 0
                )
            }

            # 温度检查
            if stats.temperature_celsius > 85:
                health["healthy"] = False
                health["issues"].append(
                    f"High temperature: {stats.temperature_celsius}C"
                )
            elif stats.temperature_celsius > 75:
                health["issues"].append(
                    f"Warning: temperature {stats.temperature_celsius}C"
                )

            # 内存检查
            memory_percent = stats.memory_used_mb / stats.memory_total_mb * 100
            if memory_percent > 95:
                health["issues"].append(
                    f"Memory almost full: {memory_percent:.1f}%"
                )

        except Exception as e:
            health["healthy"] = False
            health["issues"].append(f"Failed to get GPU stats: {e}")

        return health

    def _get_handle(self, gpu_index: int):
        """获取GPU句柄（带缓存）"""
        if gpu_index not in self._handle_cache:
            self._handle_cache[gpu_index] = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
        return self._handle_cache[gpu_index]

    def is_available(self) -> bool:
        """检查GPU是否可用"""
        return self.initialized and len(self.detect_gpus()) > 0

    def get_device_count(self) -> int:
        """获取GPU设备数量"""
        if not self.initialized:
            return 0
        try:
            return pynvml.nvmlDeviceGetCount()
        except Exception as e:
            logger.debug("Failed to read GPU device count: %s", e)
            return 0

    def __del__(self):
        """清理资源"""
        if self.initialized:
            try:
                pynvml.nvmlShutdown()
            except Exception as e:
                logger.debug("Failed to shutdown NVML: %s", e)


# 全局单例
_gpu_detector: Optional[GPUDetector] = None


def get_gpu_detector() -> GPUDetector:
    """获取GPU检测器单例"""
    global _gpu_detector
    if _gpu_detector is None:
        _gpu_detector = GPUDetector()
    return _gpu_detector
