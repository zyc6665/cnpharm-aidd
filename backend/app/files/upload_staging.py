"""上传文件的分块暂存与内容校验。"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

import aiofiles

from app.common.exceptions import ValidationException
from app.config import settings
from app.files.storage_path import STORAGE_PATH


UPLOAD_CHUNK_SIZE = 1024 * 1024
UPLOAD_SIGNATURE_BYTES = 16

_ALLOWED_UPLOAD_EXTENSIONS = {
    ".bz2", ".cif", ".csv", ".dat", ".fa", ".faa", ".fasta",
    ".fastq", ".fna", ".fq", ".gz", ".jpeg", ".jpg", ".json",
    ".log", ".mol", ".mol2", ".mmcif", ".out", ".pdb", ".pdbqt",
    ".pdf", ".png", ".sdf", ".smi", ".smiles", ".tar", ".tgz",
    ".tsv", ".txt", ".xml", ".xyz", ".xz", ".yaml", ".yml",
    ".zip",
}
_EXPECTED_FILE_SIGNATURES = {
    ".bz2": (b"BZh",),
    ".gz": (b"\x1f\x8b",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".jpg": (b"\xff\xd8\xff",),
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".xz": (b"\xfd7zXZ\x00",),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}
_EXECUTABLE_SIGNATURES = (
    b"\x7fELF",
    b"MZ",
    b"#!",
    b"\xfe\xed\xfa\xce",
    b"\xcf\xfa\xed\xfe",
)


async def stream_upload(
    file: Any,
    *,
    max_size: int,
    storage_path: Path | None = None,
) -> tuple[Path, int, str, bytes]:
    """分块暂存上传文件，并在单次读取中计算大小与 SHA-256。"""
    root = storage_path or STORAGE_PATH
    root.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix=".upload-", dir=root)
    os.close(descriptor)
    staged_path = Path(raw_path)
    sha256_hash = hashlib.sha256()
    file_size = 0
    header = bytearray()

    try:
        await file.seek(0)
        async with aiofiles.open(staged_path, "wb") as staged_file:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                file_size += len(chunk)
                if file_size > max_size:
                    raise ValidationException(
                        f"文件大小超过限制 ({settings.MAX_FILE_SIZE_MB}MB)"
                    )
                sha256_hash.update(chunk)
                if len(header) < UPLOAD_SIGNATURE_BYTES:
                    header.extend(
                        chunk[: UPLOAD_SIGNATURE_BYTES - len(header)]
                    )
                await staged_file.write(chunk)
        await file.seek(0)
        return staged_path, file_size, sha256_hash.hexdigest(), bytes(header)
    except Exception:
        staged_path.unlink(missing_ok=True)
        raise


def validate_upload_content(filename: str, header: bytes) -> None:
    """校验上传扩展名与可识别二进制文件头。"""
    extension = Path(filename).suffix.lower()
    if extension not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationException(f"不支持的上传文件类型: {extension or '无扩展名'}")

    if any(
        header.startswith(signature) for signature in _EXECUTABLE_SIGNATURES
    ):
        raise ValidationException("禁止上传可执行文件")

    expected_signatures = _EXPECTED_FILE_SIGNATURES.get(extension)
    if expected_signatures and not any(
        header.startswith(signature) for signature in expected_signatures
    ):
        raise ValidationException("文件内容与扩展名不匹配")
