# backend/app/files/__init__.py
"""文件管理模块"""

from app.files.deduplication import FileDeduplicator, DeduplicationResult
from app.files.lifecycle_manager import FileLifecycleManager, CleanupResult, FileStatistics
from app.files.reference_manager import FileReferenceManager, ReferenceManagerError
from app.files.storage_fallback import (
    StorageFallbackStrategy,
    StorageBackend,
    FallbackReason,
    get_storage_fallback
)

__all__ = [
    "FileDeduplicator",
    "DeduplicationResult",
    "FileLifecycleManager",
    "CleanupResult",
    "FileStatistics",
    "FileReferenceManager",
    "ReferenceManagerError",
    "StorageFallbackStrategy",
    "StorageBackend",
    "FallbackReason",
    "get_storage_fallback",
]
