"""P2 注入/文件/存储 DoS 硬化回归测试。

覆盖 docs/22 §2 P2 的六项硬化：

1. 分片上传单分片上限（流式计量，超限 413）；
2. ``/files/convert/sdf-to-pdb`` 边读边累计，超限 413；
3. 搜索 LIKE 通配符转义 + keyword 限长；
4. 解压后总大小 / 条目数上限（zip / tar）；
5. ``Content-Disposition`` 头注入清洗；
6. 本地存储根约束（拒绝绝对路径与 ``..`` 越界）。
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, MetaData, String, Table, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

import app.api.v1.files as files_api
from app.common.exceptions import PayloadTooLargeException, ValidationException
from app.common.search import (
    DEFAULT_KEYWORD_MAX_LENGTH,
    LIKE_ESCAPE,
    escape_like,
    like_pattern,
)
from app.files.part_staging import LocalPartStaging
from app.services import image_asset_import, uploads as uploads_service
from app.services.artifact_responses import content_disposition
from app.storage.local import LocalStorageBackend


# --------------------------------------------------------------------------- #
# 辅助构造
# --------------------------------------------------------------------------- #
def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _tar_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class _FakeUpload:
    """最小 ``UploadFile`` 替身，只需 ``read`` 与文件元信息。"""

    def __init__(
        self,
        data: bytes,
        filename: str = "mol.sdf",
        content_type: str = "chemical/x-mdl-sdfile",
    ) -> None:
        self._buffer = io.BytesIO(data)
        self.filename = filename
        self.content_type = content_type

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


class _CountingStaging:
    """只消费流、记录总字节数的假暂存后端。"""

    def __init__(self) -> None:
        self.total = 0

    async def write_part_stream(self, session_id, part_number, chunks) -> int:
        async for chunk in chunks:
            self.total += len(chunk)
        return self.total


# --------------------------------------------------------------------------- #
# 1. 分片上传单分片上限
# --------------------------------------------------------------------------- #
def test_payload_too_large_exception_contract():
    exc = PayloadTooLargeException("too big")
    assert exc.http_status == 413
    assert exc.code == 41300


@pytest.mark.asyncio
async def test_stream_part_over_cap_raises_payload_too_large():
    session = SimpleNamespace(
        id="session-1", state="UPLOADING", expires_at=None, declared_size=10
    )

    async def _chunks():
        yield b"a" * 600
        yield b"b" * 600

    with pytest.raises(PayloadTooLargeException):
        await uploads_service.record_upload_part_stream(
            None,
            session=session,
            part_number=1,
            chunks=_chunks(),
            staging=_CountingStaging(),
            max_part_bytes=1000,
        )


@pytest.mark.asyncio
async def test_local_part_staging_stream_writes_without_buffering(tmp_path):
    staging = LocalPartStaging(base_path=tmp_path)

    async def _chunks():
        yield b"abc"
        yield b""
        yield b"defg"

    written = await staging.write_part_stream("session-1", 1, _chunks())
    assert written == 7
    assert staging.part_path("session-1", 1).read_bytes() == b"abcdefg"


# --------------------------------------------------------------------------- #
# 2. convert/sdf-to-pdb 边读边累计，超限 413
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_convert_sdf_rejects_oversize_while_streaming(monkeypatch):
    # 上限设为 0，任何非空请求体都应在读取阶段被拦下（转换/落库不会执行）。
    monkeypatch.setattr(files_api, "settings", SimpleNamespace(MAX_FILE_SIZE_MB=0))
    upload = _FakeUpload(b"x" * 4096)
    with pytest.raises(PayloadTooLargeException):
        await files_api.convert_sdf_to_pdb(file=upload, current_user=None, db=None)


# --------------------------------------------------------------------------- #
# 3. 搜索 LIKE 通配符转义 + keyword 限长
# --------------------------------------------------------------------------- #
def test_escape_like_escapes_wildcards_and_backslash():
    assert escape_like("a%b_c\\d") == "a\\%b\\_c\\\\d"
    assert like_pattern("100%") == "%100\\%%"
    assert like_pattern("%") == "%\\%%"


def test_like_pattern_truncates_to_max_length():
    long_keyword = "x" * (DEFAULT_KEYWORD_MAX_LENGTH + 50)
    pattern = like_pattern(long_keyword)
    assert pattern.count("x") == DEFAULT_KEYWORD_MAX_LENGTH
    assert pattern.startswith("%") and pattern.endswith("%")


@pytest.mark.asyncio
async def test_like_escape_prevents_wildcard_injection():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    table = Table("search_demo", metadata, Column("name", String(64)))
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            await conn.execute(
                table.insert(),
                [{"name": "abc"}, {"name": "100%"}, {"name": "a_b"}],
            )

        async def _names(keyword: str) -> set[str]:
            async with engine.connect() as conn:
                result = await conn.execute(
                    select(table.c.name).where(
                        table.c.name.ilike(like_pattern(keyword), escape=LIKE_ESCAPE)
                    )
                )
                return {row[0] for row in result}

        # 转义后 ``%`` 是字面量：只命中真正含 ``%`` 的行。
        assert await _names("%") == {"100%"}
        # 转义后 ``_`` 是字面量：只命中真正含下划线的行。
        assert await _names("_") == {"a_b"}
        assert await _names("abc") == {"abc"}
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- #
# 4. 解压后大小 / 条目数上限
# --------------------------------------------------------------------------- #
def test_zip_extract_rejects_too_many_entries(monkeypatch):
    from app.tasks import molecule_scoring

    monkeypatch.setattr(molecule_scoring, "MAX_ARCHIVE_ENTRIES", 2)
    content = _zip_bytes({"a.sdf": b"x", "b.sdf": b"y", "c.sdf": b"z"})
    record = SimpleNamespace(id="file-1", filename="mol.zip")
    with pytest.raises(ValidationException):
        molecule_scoring._extract_candidates_from_zip_content(
            record, next_global_index=0, content=content
        )


def test_zip_extract_rejects_decompressed_bomb(monkeypatch):
    from app.tasks import molecule_scoring

    monkeypatch.setattr(molecule_scoring, "MAX_ARCHIVE_ENTRIES", 10000)
    monkeypatch.setattr(molecule_scoring, "MAX_ARCHIVE_UNCOMPRESSED_BYTES", 10)
    content = _zip_bytes({"big.sdf": b"A" * 1000})
    record = SimpleNamespace(id="file-1", filename="mol.zip")
    with pytest.raises(ValidationException):
        molecule_scoring._extract_candidates_from_zip_content(
            record, next_global_index=0, content=content
        )


def test_docker_save_archive_rejects_decompressed_bomb(tmp_path, monkeypatch):
    monkeypatch.setattr(image_asset_import, "MAX_ARCHIVE_UNCOMPRESSED_BYTES", 8)
    payload = _tar_bytes(
        {
            "manifest.json": b'[{"Config":"c.json","RepoTags":["x:1"],"Layers":["l.tar"]}]',
            "c.json": b"{}",
            "l.tar": b"A" * 4096,
        }
    )
    archive = tmp_path / "image.tar"
    archive.write_bytes(payload)
    with pytest.raises(image_asset_import.ImageArchiveError):
        image_asset_import._load_archive(archive, tmp_path / "work")


# --------------------------------------------------------------------------- #
# 5. Content-Disposition 头注入
# --------------------------------------------------------------------------- #
def test_content_disposition_encodes_utf8_and_strips_quotes():
    value = content_disposition('分子 "结构".sdf')
    assert value.startswith("attachment;")
    assert "filename*=UTF-8''" in value
    assert "%E5%88%86" in value  # “分”的 UTF-8 百分号编码
    # 仅保留包裹 ASCII 回退名的两个引号，文件名内不再残留引号破坏头部语法。
    assert value.count('"') == 2


def test_content_disposition_strips_header_injection():
    value = content_disposition("evil\r\nSet-Cookie: pwn=1.sdf")
    assert "\r" not in value
    assert "\n" not in value
    assert "filename*=UTF-8''" in value


def test_content_disposition_matches_existing_contract():
    value = content_disposition('ligand "3d".sdf')
    assert 'filename="ligand 3d.sdf"' in value
    assert "filename*=UTF-8''ligand%20%223d%22.sdf" in value


# --------------------------------------------------------------------------- #
# 6. 本地存储根约束
# --------------------------------------------------------------------------- #
def test_local_storage_rejects_traversal_and_absolute(tmp_path):
    backend = LocalStorageBackend(base_path=str(tmp_path))
    for bad in ("../escape", "/etc/passwd", "ab/../../../etc/passwd", ""):
        with pytest.raises(ValueError):
            backend._get_full_path(bad)


@pytest.mark.asyncio
async def test_local_storage_rejects_absolute_read_outside_root(tmp_path):
    backend = LocalStorageBackend(base_path=str(tmp_path))
    with pytest.raises(ValueError):
        await backend.download("/etc/passwd")
    with pytest.raises(ValueError):
        await backend.exists("../escape")


@pytest.mark.asyncio
async def test_local_storage_allows_legit_relative_and_in_root_absolute(tmp_path):
    backend = LocalStorageBackend(base_path=str(tmp_path))
    info = await backend.upload(b"hello", "ab/abcdef", "text/plain")
    assert await backend.exists("ab/abcdef")
    assert await backend.download("ab/abcdef") == b"hello"
    # 数据库里记录的绝对路径（位于根内）仍应可用。
    assert await backend.download(info.path) == b"hello"
