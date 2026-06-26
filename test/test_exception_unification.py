"""测试异常体系统一。"""

import pytest

from app.common.exceptions import AppException
from app.exceptions.external_api import (
    ExternalAPIException,
    APITimeoutException,
    APIRateLimitException,
)
from app.exceptions.storage import (
    StorageException,
    StorageUploadException,
    StorageQuotaException,
    StorageCorruptionException,
)


class TestExternalAPIExceptionInheritance:
    def test_external_api_exception_is_app_exception(self):
        assert issubclass(ExternalAPIException, AppException)

    def test_subclasses_inherit_app_exception(self):
        assert issubclass(APITimeoutException, AppException)
        assert issubclass(APIRateLimitException, AppException)

    def test_to_dict_preserves_original_shape(self):
        exc = ExternalAPIException(
            message="timeout",
            api_name="chembl",
            status_code=503,
            response_body="bad gateway",
        )
        assert exc.to_dict() == {
            "error_type": "ExternalAPIException",
            "message": "timeout",
            "api_name": "chembl",
            "status_code": 503,
        }

    def test_app_exception_attributes_populated(self):
        exc = ExternalAPIException(
            message="timeout",
            status_code=503,
            response_body="bad gateway",
        )
        assert exc.message == "timeout"
        assert exc.code == 503
        assert exc.detail == "bad gateway"

    def test_rate_limit_subclass_keeps_retry_after(self):
        exc = APIRateLimitException(
            message="rate limited",
            retry_after=60,
            api_name="pubchem",
            status_code=429,
        )
        assert exc.retry_after == 60
        assert exc.code == 429
        assert issubclass(APIRateLimitException, AppException)


class TestStorageExceptionInheritance:
    def test_storage_exception_is_app_exception(self):
        assert issubclass(StorageException, AppException)

    def test_subclasses_inherit_app_exception(self):
        assert issubclass(StorageUploadException, AppException)
        assert issubclass(StorageQuotaException, AppException)
        assert issubclass(StorageCorruptionException, AppException)

    def test_to_dict_preserves_original_shape(self):
        exc = StorageException(
            message="upload failed",
            storage_backend="minio",
            file_path="foo/bar.txt",
            operation="upload",
        )
        assert exc.to_dict() == {
            "error_type": "StorageException",
            "message": "upload failed",
            "storage_backend": "minio",
            "file_path": "foo/bar.txt",
            "operation": "upload",
        }

    def test_app_exception_attributes_populated(self):
        exc = StorageException(
            message="upload failed",
            storage_backend="minio",
            file_path="foo/bar.txt",
            operation="upload",
        )
        assert exc.message == "upload failed"
        assert exc.code == 500
        assert exc.detail == {
            "storage_backend": "minio",
            "file_path": "foo/bar.txt",
            "operation": "upload",
        }

    def test_quota_exception_keeps_extra_fields(self):
        exc = StorageQuotaException(
            message="quota exceeded",
            quota_limit=100,
            current_usage=101,
            storage_backend="minio",
        )
        assert exc.quota_limit == 100
        assert exc.current_usage == 101
        assert exc.storage_backend == "minio"
        assert issubclass(StorageQuotaException, AppException)

    def test_corruption_exception_keeps_extra_fields(self):
        exc = StorageCorruptionException(
            message="hash mismatch",
            expected_hash="abc",
            actual_hash="def",
            file_path="foo.txt",
        )
        assert exc.expected_hash == "abc"
        assert exc.actual_hash == "def"
        assert exc.file_path == "foo.txt"
        assert issubclass(StorageCorruptionException, AppException)
