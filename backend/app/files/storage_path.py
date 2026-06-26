"""本地存储路径工具函数。

该模块属于存储服务层，供 API 层、任务执行器、文件生命周期管理等模块复用，
避免任务执行器反向依赖 API 路由层。
"""

from pathlib import Path

from app.config import settings


# 存储目录
STORAGE_PATH = Path(settings.STORAGE_PATH)


def ensure_storage_dir() -> None:
    """确保存储目录存在"""
    STORAGE_PATH.mkdir(parents=True, exist_ok=True)


def get_file_path(file_id: str, filename: str) -> Path:
    """获取文件存储路径

    使用文件 ID 的前两位作为子目录，避免单目录文件过多。
    """
    subdir = file_id[:2]
    return STORAGE_PATH / subdir / f"{file_id}_{filename}"
