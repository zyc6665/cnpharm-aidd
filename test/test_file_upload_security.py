"""文件上传流式处理与类型校验回归测试。"""

import hashlib

import pytest

from app.files import upload_staging
from app.common.exceptions import ValidationException


class ChunkedUpload:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.offset = 0
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 0:
            raise AssertionError("上传处理不应执行无大小限制的 read()")
        chunk = self.content[self.offset: self.offset + size]
        self.offset += len(chunk)
        return chunk

    async def seek(self, offset: int) -> None:
        self.offset = offset


@pytest.mark.asyncio
async def test_stream_upload_calculates_hash_without_unbounded_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    content = b"ATOM test\n" * 300_000
    upload = ChunkedUpload(content)
    monkeypatch.setattr(upload_staging, "STORAGE_PATH", tmp_path)

    upload_result = await upload_staging.stream_upload(
        upload,
        max_size=len(content) + 1,
    )
    staged_path, size_bytes, sha256, header = upload_result

    try:
        assert size_bytes == len(content)
        assert sha256 == hashlib.sha256(content).hexdigest()
        assert header == content[: upload_staging.UPLOAD_SIGNATURE_BYTES]
        assert len(upload.read_sizes) > 1
        assert all(
            size == upload_staging.UPLOAD_CHUNK_SIZE
            for size in upload.read_sizes
        )
    finally:
        staged_path.unlink(missing_ok=True)


def test_upload_type_validation_rejects_executable_content() -> None:
    with pytest.raises(ValidationException, match="可执行文件"):
        upload_staging.validate_upload_content(
            "sample.pdb",
            b"\x7fELF\x02\x01",
        )


def test_upload_type_validation_rejects_mismatched_binary_signature() -> None:
    with pytest.raises(ValidationException, match="文件内容与扩展名"):
        upload_staging.validate_upload_content("report.pdf", b"PK\x03\x04")
