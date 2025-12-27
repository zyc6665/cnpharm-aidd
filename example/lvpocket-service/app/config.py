"""
配置管理模块

使用 pydantic BaseSettings 管理环境变量配置
"""

import os
import sys
from functools import lru_cache
from typing import Dict, List, Optional

from pydantic import BaseSettings, Field, validator


# SCOP 蛋白质结构分类枚举
# 参考 LVpocket scop_classifier/classifier.py
class SCOPClass:
    """SCOP 蛋白质结构分类"""
    BASELINE = "baseline"  # 基线模型（默认）
    ALPHA = "alpha"        # α 类（全螺旋）
    BETA = "beta"          # β 类（全折叠）
    ALPHA_BETA = "alpha_beta"  # α/β 类（交替）
    ALPHA_PLUS_BETA = "alpha_plus_beta"  # α+β 类（分离）

    # 所有有效的分类
    ALL_CLASSES = [BASELINE, ALPHA, BETA, ALPHA_BETA, ALPHA_PLUS_BETA]

    # 分类描述
    DESCRIPTIONS = {
        BASELINE: "基线模型 - 通用模型，适用于所有蛋白质",
        ALPHA: "α 类 - 主要由 α 螺旋组成的蛋白质",
        BETA: "β 类 - 主要由 β 折叠组成的蛋白质",
        ALPHA_BETA: "α/β 类 - α 螺旋和 β 折叠交替排列",
        ALPHA_PLUS_BETA: "α+β 类 - α 螺旋和 β 折叠分离排列",
    }


class Settings(BaseSettings):
    """应用配置"""

    # 服务配置
    APP_NAME: str = "LVPocket Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1

    # LVpocket 源代码路径（用于导入 model.LV_former 和 tfbio.data）
    LVPOCKET_SOURCE_PATH: str = "/data/zhouyc/cpumodel_sciminer/example/lvpocket-service/model/LVpocket"

    # ==================== 多模型配置 ====================
    # 模型目录（包含所有 SCOP 分类模型）
    MODEL_DIR: str = "/data/zhouyc/cpumodel_sciminer/example/lvpocket-service/model/LVpocket/trained_model"

    # 各 SCOP 分类对应的模型文件名
    # 实际使用 newbest/new_best 目录中的微调模型
    MODEL_FILES: Dict[str, str] = {
        # 基线模型（默认）
        "baseline": "newbest/new_best/baseline_model.hdf",
        # α 类蛋白质模型
        "alpha": "newbest/new_best/α_finetuned_model.hdf",
        # β 类蛋白质模型
        "beta": "newbest/new_best/β_finetuned_model.hdf",
        # α/β 类蛋白质模型
        "alpha_beta": "newbest/new_best/α_and_β_finetuned_model.hdf",
        # α+β 类蛋白质模型
        "alpha_plus_beta": "newbest/new_best/α_or_β_finetuned_model.hdf",
    }

    # 默认使用的模型（基线模型）
    DEFAULT_MODEL: str = "baseline"

    # 旧的单模型配置（保持兼容）
    MODEL_PATH: str = "/data/zhouyc/cpumodel_sciminer/example/lvpocket-service/model/LVpocket/trained_model/newbest/new_best/baseline_model.hdf"
    MODEL_VERSION: str = "1.0.0"

    # 模型参数（参考 predict.py 默认参数）
    SCALE: float = 0.5  # 体素分辨率 (Å)
    MAX_DIST: float = 35.0  # 最大距离阈值

    # ==================== 预测参数 ====================
    DEFAULT_THRESHOLD: float = 0.5  # 默认口袋预测阈值
    DEFAULT_MIN_SIZE: int = 50  # 默认最小口袋体素数
    DEFAULT_OUTPUT_FORMATS: List[str] = ["json"]
    # 默认蛋白质结构分类
    DEFAULT_STRUCTURE_CLASS: str = "baseline"

    # ==================== 文件配置 ====================
    MAX_FILE_SIZE: int = 52428800  # 50MB
    ALLOWED_INPUT_FORMATS: List[str] = ["pdb", "mol2"]
    ALLOWED_OUTPUT_FORMATS: List[str] = ["json", "mol2", "cmap", "cube"]
    TEMP_DIR: str = "/tmp/lvpocket"
    OUTPUT_DIR: str = "/app/data/output"

    # ==================== 超时配置 ====================
    REQUEST_TIMEOUT: int = 300  # 秒
    DOWNLOAD_TIMEOUT: int = 60  # 文件下载超时

    # ==================== GPU 配置 ====================
    CUDA_VISIBLE_DEVICES: Optional[str] = None
    TF_FORCE_GPU_ALLOW_GROWTH: bool = True

    def get_model_path(self, structure_class: str = None) -> str:
        """
        根据蛋白质结构分类获取对应的模型文件路径

        Args:
            structure_class: 蛋白质结构分类 (baseline/alpha/beta/alpha_beta/alpha_plus_beta)

        Returns:
            模型文件的完整路径
        """
        if structure_class is None:
            structure_class = self.DEFAULT_MODEL

        # 验证分类是否有效
        if structure_class not in self.MODEL_FILES:
            structure_class = self.DEFAULT_MODEL

        model_file = self.MODEL_FILES.get(structure_class, self.MODEL_FILES["baseline"])
        return os.path.join(self.MODEL_DIR, model_file)

    def get_available_models(self) -> Dict[str, dict]:
        """
        获取所有可用的模型信息

        Returns:
            模型信息字典
        """
        models = {}
        for class_name, model_file in self.MODEL_FILES.items():
            model_path = os.path.join(self.MODEL_DIR, model_file)
            models[class_name] = {
                "file": model_file,
                "path": model_path,
                "exists": os.path.exists(model_path),
                "description": SCOPClass.DESCRIPTIONS.get(class_name, ""),
            }
        return models

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
