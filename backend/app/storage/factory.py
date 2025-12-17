# backend/app/storage/factory.py
"""存储后端工厂"""

from functools import lru_cache
from typing import Literal

from app.storage.base import StorageBackend
from app.config import settings


StorageType = Literal["local", "minio"]


@lru_cache()
def get_storage_backend(backend_type: StorageType = None) -> StorageBackend:
    """
    获取存储后端实例（单例）

    通过配置 STORAGE_BACKEND 环境变量切换:
    - local: 本地文件存储（开发环境）
    - minio: MinIO 对象存储（生产环境）

    Args:
        backend_type: 存储类型，默认从配置读取

    Returns:
        StorageBackend: 存储后端实例
    """
    backend = backend_type or settings.STORAGE_BACKEND

    if backend == "local":
        from app.storage.local import LocalStorageBackend
        return LocalStorageBackend()

    elif backend == "minio":
        from app.storage.minio_backend import MinIOStorageBackend
        return MinIOStorageBackend()

    else:
        raise ValueError(f"不支持的存储后端: {backend}")


# 便捷访问
storage = get_storage_backend()
