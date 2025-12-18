# backend/app/storage/__init__.py
"""存储适配层 - 支持本地存储和 MinIO"""

from app.storage.base import StorageBackend
from app.storage.factory import get_storage_backend

__all__ = ["StorageBackend", "get_storage_backend"]
