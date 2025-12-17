"""
FastAPI 依赖注入

管理模型加载器和其他共享资源
"""

import logging
import time
from typing import Optional

from app.config import settings
from app.core.lvpocket import LVPocketPredictor

logger = logging.getLogger(__name__)


class ModelManager:
    """模型管理器 - 单例模式"""

    _instance: Optional["ModelManager"] = None
    _predictor: Optional[LVPocketPredictor] = None
    _start_time: float = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._start_time = time.time()
        return cls._instance

    @property
    def predictor(self) -> Optional[LVPocketPredictor]:
        return self._predictor

    @property
    def is_loaded(self) -> bool:
        return self._predictor is not None

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time

    def load_model(self) -> bool:
        """
        加载模型

        使用默认结构分类（baseline）初始化预测器
        后续预测时可根据请求参数动态切换模型
        """
        if self._predictor is not None:
            logger.info("模型已加载，跳过重复加载")
            return True

        try:
            logger.info(f"开始加载模型")
            logger.info(f"LVpocket 源码路径: {settings.LVPOCKET_SOURCE_PATH}")
            logger.info(f"模型目录: {settings.MODEL_DIR}")
            logger.info(f"默认结构分类: {settings.DEFAULT_MODEL}")

            # 使用默认结构分类初始化预测器
            # 预测器支持动态切换模型，会根据 structure_class 参数自动加载对应模型
            self._predictor = LVPocketPredictor(
                model_path=None,  # 使用 structure_class 自动选择模型
                scale=settings.SCALE,
                max_dist=settings.MAX_DIST,
                structure_class=settings.DEFAULT_MODEL,
            )

            # 显示可用模型
            available_models = settings.get_available_models()
            for class_name, model_info in available_models.items():
                status = "✓" if model_info["exists"] else "✗"
                logger.info(f"  [{status}] {class_name}: {model_info['file']}")

            logger.info("模型加载成功")
            return True
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            self._predictor = None
            return False

    def unload_model(self):
        """卸载模型"""
        if self._predictor is not None:
            self._predictor.close()
            self._predictor = None
            logger.info("模型已卸载")


# 全局模型管理器实例
model_manager = ModelManager()


def get_model_manager() -> ModelManager:
    """获取模型管理器依赖"""
    return model_manager


def get_predictor() -> LVPocketPredictor:
    """获取预测器依赖"""
    if not model_manager.is_loaded:
        raise RuntimeError("模型未加载，请检查服务状态")
    return model_manager.predictor
