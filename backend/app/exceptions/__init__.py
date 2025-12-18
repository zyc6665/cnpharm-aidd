# backend/app/exceptions/__init__.py
"""异常处理模块"""

from app.exceptions.external_api import (
    ExternalAPIException,
    APITimeoutException,
    APIConnectionException,
    APIRateLimitException,
    APIResponseException,
    ExternalAPIHandler,
    APIFallbackHandler
)
from app.exceptions.storage import (
    StorageException,
    StorageUploadException,
    StorageDownloadException,
    StorageDeleteException,
    StorageExceptionHandler
)

__all__ = [
    "ExternalAPIException",
    "APITimeoutException",
    "APIConnectionException",
    "APIRateLimitException",
    "APIResponseException",
    "ExternalAPIHandler",
    "APIFallbackHandler",
    "StorageException",
    "StorageUploadException",
    "StorageDownloadException",
    "StorageDeleteException",
    "StorageExceptionHandler",
]
