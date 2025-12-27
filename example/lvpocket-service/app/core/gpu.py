"""
GPU 状态检测模块

提供 GPU 信息查询和可用性检测功能
兼容 TensorFlow 1.15 API
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    """GPU 信息数据类"""

    available: bool
    name: Optional[str] = None
    memory_total: Optional[int] = None  # MB
    memory_used: Optional[int] = None  # MB
    memory_free: Optional[int] = None  # MB
    compute_capability: Optional[str] = None


def is_gpu_available() -> bool:
    """
    检查 GPU 是否可用

    Returns:
        bool: GPU 是否可用
    """
    try:
        import tensorflow as tf

        # 检查 TF 版本，使用对应的 API
        tf_version = tf.__version__
        is_tf2 = tf_version.startswith("2.")

        if is_tf2 and hasattr(tf.config, "list_physical_devices"):
            # TF 2.x 方式
            gpus = tf.config.list_physical_devices("GPU")
            return len(gpus) > 0
        else:
            # TF 1.x 方式
            from tensorflow.python.client import device_lib

            devices = device_lib.list_local_devices()
            gpu_devices = [d for d in devices if d.device_type == "GPU"]
            return len(gpu_devices) > 0
    except Exception as e:
        logger.warning(f"GPU 检测失败: {e}")
        return False


def get_gpu_info() -> GPUInfo:
    """
    获取 GPU 详细信息

    Returns:
        GPUInfo: GPU 信息对象
    """
    try:
        import tensorflow as tf

        # 检查 TF 版本
        tf_version = tf.__version__
        is_tf2 = tf_version.startswith("2.")

        # 检查是否有 GPU
        if is_tf2 and hasattr(tf.config, "list_physical_devices"):
            # TF 2.x
            gpus = tf.config.list_physical_devices("GPU")
            if not gpus:
                return GPUInfo(available=False)
        else:
            # TF 1.x
            from tensorflow.python.client import device_lib

            devices = device_lib.list_local_devices()
            gpu_devices = [d for d in devices if d.device_type == "GPU"]
            if not gpu_devices:
                return GPUInfo(available=False)

        # 尝试使用 pynvml 获取详细信息
        try:
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)

            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8")

            memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            memory_total = memory_info.total // (1024 * 1024)  # 转换为 MB
            memory_used = memory_info.used // (1024 * 1024)
            memory_free = memory_info.free // (1024 * 1024)

            # 获取计算能力
            major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
            compute_capability = f"{major}.{minor}"

            pynvml.nvmlShutdown()

            return GPUInfo(
                available=True,
                name=name,
                memory_total=memory_total,
                memory_used=memory_used,
                memory_free=memory_free,
                compute_capability=compute_capability,
            )

        except ImportError:
            logger.info("pynvml 未安装，返回基础 GPU 信息")
            return GPUInfo(available=True, name="GPU (详情不可用)")

        except Exception as e:
            logger.warning(f"获取 GPU 详细信息失败: {e}")
            return GPUInfo(available=True, name="GPU (详情获取失败)")

    except ImportError:
        logger.warning("TensorFlow 未安装")
        return GPUInfo(available=False)

    except Exception as e:
        logger.error(f"GPU 信息获取异常: {e}")
        return GPUInfo(available=False)


def configure_gpu_memory_growth():
    """
    配置 GPU 内存按需增长

    避免 TensorFlow 一次性占用所有 GPU 显存
    """
    try:
        import tensorflow as tf

        # 检查 TF 版本
        tf_version = tf.__version__
        is_tf2 = tf_version.startswith("2.")

        if is_tf2 and hasattr(tf.config, "list_physical_devices"):
            # TF 2.x
            gpus = tf.config.list_physical_devices("GPU")
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
            logger.info(f"已配置 {len(gpus)} 个 GPU 内存按需增长")
        else:
            # TF 1.x - 通过环境变量或 session config 配置
            # 环境变量 TF_FORCE_GPU_ALLOW_GROWTH=true 已在 Dockerfile 中设置
            logger.info("TF 1.x: GPU 内存增长已通过环境变量配置")

    except Exception as e:
        logger.warning(f"配置 GPU 内存增长失败: {e}")


def get_tf_session_config():
    """
    获取 TensorFlow 1.x Session 配置

    Returns:
        tf.ConfigProto: Session 配置对象
    """
    try:
        import tensorflow as tf

        config = tf.ConfigProto()
        config.gpu_options.allow_growth = True
        config.gpu_options.per_process_gpu_memory_fraction = 0.9
        return config
    except ImportError:
        return None
