"""分片上传会话领域用例（docs/04 §5.8、docs/05 §4.2）。

设计取舍
--------
**分片字节放哪里**：交给 ``app.files.part_staging``——它按 ``STORAGE_BACKEND``
选本地盘或对象存储。生产强制 ``minio``（``app.config`` 有硬校验）而 backend 容器
不挂卷，分片若写本地盘，进程重启即丢、换副本即找不到，断点续传形同虚设。

**分片索引放哪里**：``upload_parts`` 表，``(session_id, part_number)`` 复合主键 +
原生 upsert。JSON 列只能整列读整列写，两个并发 ``PUT`` 会互相覆盖整列——字节还在
暂存里，索引却只剩最后一片（PR #15 评审 B1）。行级记录让并发写落到同一行上。

**为什么合并要流式**：早期实现在进程内 ``bytearray`` 拼装，2GB 文件要常驻 2GB 内存，
并发两个合并就 OOM。现在先按片统计字节数做上限与 ``declared_size`` 校验，再逐片
读、写临时文件、增量算 sha256，最后交给 ``store_file_path``——峰值内存只有一片。

**过期**：会话 24 小时有效。三个入口（上报分片、合并、取消）都会检查 ``expires_at``，
过期的当场置 ``EXPIRED`` 并清理暂存；另有 ``app.services.upload_maintenance`` 的
定时任务兜底，处理「创建后就没再动过」的会话。
"""

from __future__ import annotations

import hashlib
import math
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
    PayloadTooLargeException,
    ValidationException,
)
from app.common.time import utcnow
from app.config import settings
from app.files.part_staging import PartStaging, build_part_staging
from app.files.storage_path import ensure_storage_dir, safe_storage_filename
from app.files.writer import store_file_path
from app.models.files import File as FileModel
from app.models.files import FileSourceType
from app.models.uploads import UploadPart, UploadSession
from app.models.users import User
from app.schemas.uploads import UploadPartRef, UploadSessionCreate

#: 分片大小 16MB：2GB / 16MB = 128 片，正好对上 docs/04 §5.8 的片数上限。
#: 取自 ``settings``，让部署侧能按存储后端调整而不必改代码。
UPLOAD_PART_SIZE_BYTES = settings.UPLOAD_PART_SIZE_BYTES
#: 会话存活 24 小时（docs/04 §5.8）；过期会话由定时任务置 EXPIRED 并清理分片。
UPLOAD_SESSION_TTL_HOURS = settings.UPLOAD_SESSION_TTL_HOURS
#: 单文件上限 2GB（docs/04 §13.2、docs/16 §4.1）；与 ``UploadSessionCreate.size`` 的
#: ``le`` 同口径，服务层再兜一次，防止绕过 schema 直接调服务。
UPLOAD_MAX_OBJECT_BYTES = 2 * 1024 * 1024 * 1024
#: 服务端合并上限。流式落盘后不再受进程内存约束，因此与单文件上限同口径；
#: 保留独立开关是为了部署侧能用更小的值限制临时盘占用。
UPLOAD_MAX_ASSEMBLY_BYTES = settings.UPLOAD_MAX_ASSEMBLY_BYTES

#: 单个分片的大小上限（P2 注入/存储 DoS 硬化）。请求体按块计量，一旦累计超过
#: 该值立即 413，不把整段分片读入内存。默认取部署侧配置；未配置时默认 8 MiB，
#: 但**不得小于声明分片大小** ``UPLOAD_PART_SIZE_BYTES``——否则客户端按会话返回的
#: ``part_size``（16 MiB）正常上传的整片会被误杀，破坏既有契约。
UPLOAD_MAX_PART_SIZE_BYTES = max(
    int(getattr(settings, "UPLOAD_MAX_PART_SIZE_BYTES", 8 * 1024 * 1024)),
    int(UPLOAD_PART_SIZE_BYTES),
)

#: 允许继续上传分片 / 合并的状态。其余状态一律 409，避免「已完成/已取消」被续写。
ACTIVE_STATES = ("INITIATED", "UPLOADING")

#: 合并时逐片读写的块大小；与 ``store_file_path`` 的哈希块大小一致。
_ASSEMBLY_CHUNK_BYTES = 1024 * 1024


def part_count_for(size: int) -> int:
    """按 16MB 分片计算片数，至少 1 片（0 字节由 schema 的 ``gt=0`` 挡掉）。"""
    return max(1, math.ceil(int(size) / UPLOAD_PART_SIZE_BYTES))


def build_object_key(*, project_id: str, filename: str) -> str:
    """目标对象路径，遵循 docs/04 §13.1 的 ``{projectId}/{type}/{yyyyMMdd}/{uuid}.{ext}``。

    前缀带 12 位随机段而不是直接用原文件名：``object_key`` 上有唯一约束
    （``uq_upload_sessions_object_key``，保证「一个目标对象只有一个活会话」）。
    若键里只有项目 + 日期 + 文件名，用户第二次上传同名文件（或取消后重传）就会撞
    唯一约束返回 500。加随机段后既符合 docs 的 ``{uuid}.{ext}`` 形态，也保留原文件名
    便于排查。
    """
    day = utcnow().strftime("%Y%m%d")
    token = uuid.uuid4().hex[:12]
    return f"{project_id}/upload/{day}/{token}-{safe_storage_filename(filename)}"


def _part_size_of(session: UploadSession) -> int:
    return int(session.part_size or UPLOAD_PART_SIZE_BYTES)


def _declared_part_count(session: UploadSession) -> int:
    return part_count_for(int(session.declared_size or 0))


def _stored_part_numbers(session: UploadSession) -> set[int]:
    return {int(item.part_number) for item in (session.part_records or [])}


def _stored_parts(session: UploadSession) -> list[dict]:
    """已收到分片的对外表示，按上报时间排序（写入顺序，不是片号顺序）。"""
    records = sorted(
        session.part_records or [],
        key=lambda item: (item.reported_at or utcnow(), int(item.part_number)),
    )
    return [
        {
            "partNumber": int(item.part_number),
            "etag": item.etag,
            "size": int(item.size_bytes or 0),
        }
        for item in records
    ]


def serialize_upload_session(session: UploadSession) -> dict:
    """会话的对外表示（docs/05 §4.2 的创建与断点续传响应）。"""
    parts = _stored_parts(session)
    done = _stored_part_numbers(session)
    part_count = _declared_part_count(session)
    return {
        "uploadId": str(session.id),
        "projectId": str(session.project_id),
        "filename": session.declared_filename,
        "size": int(session.declared_size or 0),
        "contentType": session.content_type,
        "objectKey": session.object_key,
        "partSize": _part_size_of(session),
        "partCount": part_count,
        "parts": parts,
        "receivedPartNumbers": sorted(done),
        # 断点续传：前端只重传这些片号（docs/05 §4.2「断点续传」）。
        "missingPartNumbers": [n for n in range(1, part_count + 1) if n not in done],
        "state": session.state,
        "expiresAt": session.expires_at.isoformat() if session.expires_at else None,
    }


async def get_upload_session(db: AsyncSession, *, upload_id: str) -> UploadSession:
    """按 id 取会话，不存在时 404。"""
    session = await db.scalar(
        select(UploadSession).where(UploadSession.id == str(upload_id))
    )
    if session is None:
        raise NotFoundException("上传会话不存在")
    return session


def is_expired(session: UploadSession, *, now=None) -> bool:
    """会话是否已过期；``expires_at`` 为空视为不过期（兼容历史行）。"""
    if session.expires_at is None:
        return False
    return session.expires_at <= (now or utcnow())


async def expire_upload_session(
    db: AsyncSession, *, session: UploadSession, staging: PartStaging | None = None
) -> None:
    """把会话置为 ``EXPIRED`` 并清掉暂存分片（幂等，可重复调用）。"""
    if session.state not in ("EXPIRED", "COMPLETED", "ABORTED"):
        session.state = "EXPIRED"
        await db.commit()
    await (staging or build_part_staging()).discard(str(session.id))


async def _require_active(
    db: AsyncSession, *, session: UploadSession, staging: PartStaging
) -> None:
    """过期 / 非活跃状态一律拦在这里，避免业务分支各写一遍。"""
    if is_expired(session):
        await expire_upload_session(db, session=session, staging=staging)
        raise ConflictException("上传会话已过期（有效期 24 小时），请重新创建上传会话")
    if session.state not in ACTIVE_STATES:
        raise ConflictException(f"会话状态为 {session.state}，不能继续操作分片")


async def find_idempotent_session(
    db: AsyncSession, *, project_id: str, idempotency_key: str
) -> UploadSession | None:
    """同 project + 同幂等键的既有会话。

    幂等键单独成列而不是塞进分片表：创建会话时还没有任何分片，塞进去会被后续
    上报覆盖掉，幂等随即失效。唯一约束在 ``uq_upload_sessions_project_idem``，
    本函数只是快路径——真正的互斥由数据库保证。
    """
    if not idempotency_key:
        return None
    return await db.scalar(
        select(UploadSession).where(
            UploadSession.project_id == str(project_id),
            UploadSession.idempotency_key == idempotency_key,
        )
    )


async def create_upload_session(
    db: AsyncSession,
    *,
    project_id: str,
    user: User,
    data: UploadSessionCreate,
    idempotency_key: str,
) -> UploadSession:
    """创建会话；同幂等键重复调用返回同一会话（不重置状态与已传分片）。

    并发下两个请求都可能走完 ``find_idempotent_session`` 的空结果分支，因此还要
    依赖唯一约束兜底：插入失败（``IntegrityError``）时回滚并重查，返回先落库的
    那个会话。没有这一步，同一个 ``X-Idempotency-Key`` 会换来两个 uploadId，
    客户端的分片就分叉到两个会话里。
    """
    existing = await find_idempotent_session(
        db, project_id=project_id, idempotency_key=idempotency_key
    )
    if existing is not None:
        return existing

    if int(data.size) > UPLOAD_MAX_OBJECT_BYTES:
        raise ValidationException("单文件超过 2GB 上限")

    session = UploadSession(
        project_id=str(project_id),
        created_by=str(user.id),
        declared_filename=data.filename,
        declared_size=int(data.size),
        declared_sha256=data.sha256,
        content_type=data.content_type,
        object_key=build_object_key(project_id=str(project_id), filename=data.filename),
        part_size=UPLOAD_PART_SIZE_BYTES,
        state="INITIATED",
        expires_at=utcnow() + timedelta(hours=UPLOAD_SESSION_TTL_HOURS),
        idempotency_key=idempotency_key,
    )
    db.add(session)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raced = await find_idempotent_session(
            db, project_id=project_id, idempotency_key=idempotency_key
        )
        if raced is not None:
            return raced
        raise
    await db.refresh(session)
    return session


def _upsert_part_statement(
    db: AsyncSession, *, session_id: str, part_number: int, etag: str, size: int
):
    """构造「同片号覆盖」的 upsert 语句；按会话实际绑定的方言选构造器。

    方言从 ``db`` 上取而不是从全局 ``engine``：测试用的是独立的内存库，两者可能
    不是同一个引擎。SQLite 与 PostgreSQL 都支持 ``ON CONFLICT ... DO UPDATE``；
    其它方言返回 ``None``，调用方退化为「先删后插」——同片号仍只有一行，只是不
    原子。部署侧只用前两种，这里只求不崩。
    """
    values = {
        "session_id": str(session_id),
        "part_number": int(part_number),
        "etag": etag,
        "size_bytes": int(size),
        "reported_at": utcnow(),
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    dialect = _dialect_name(db)
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as _insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as _insert
    else:
        return None
    return _insert(UploadPart).values(**values).on_conflict_do_update(
        index_elements=["session_id", "part_number"],
        set_={"etag": etag, "size_bytes": int(size), "updated_at": utcnow()},
    )


def _dialect_name(db: AsyncSession) -> str:
    bind = db.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "sqlite")


async def _persist_part_row(
    db: AsyncSession,
    *,
    session: UploadSession,
    part_number: int,
    etag: str,
    written: int,
) -> dict:
    """把 ``(session_id, part_number)`` 一行 upsert 进 ``upload_parts`` 并返回回执。

    ``record_upload_part``（整段字节）与 ``record_upload_part_stream``（流式）共用，
    保证两条路径的落库行为完全一致：幂等覆盖、状态置 ``UPLOADING``、重载分片集合。
    """
    statement = _upsert_part_statement(
        db,
        session_id=str(session.id),
        part_number=int(part_number),
        etag=etag,
        size=written,
    )
    if statement is not None:
        await db.execute(statement)
    else:  # pragma: no cover - 仅非 sqlite/pg 方言
        await db.delete(UploadPart).where(
            UploadPart.session_id == str(session.id),
            UploadPart.part_number == int(part_number),
        )
        db.add(
            UploadPart(
                session_id=str(session.id),
                part_number=int(part_number),
                etag=etag,
                size_bytes=written,
            )
        )

    if session.state != "UPLOADING":
        session.state = "UPLOADING"
    await db.commit()
    await _reload_parts(db, session)
    return {"partNumber": int(part_number), "etag": etag, "size": written}


async def record_upload_part(
    db: AsyncSession,
    *,
    session: UploadSession,
    part_number: int,
    content: bytes,
    staging: PartStaging | None = None,
) -> dict:
    """落分片字节，并把 ``(session_id, part_number)`` 一行写进 ``upload_parts``。

    重传同一片是常态（网络抖动）：字节覆盖同名的暂存对象，索引行用 upsert 覆盖，
    两者都幂等。**不要**改成「读现有列表再整列写回」——并发下会丢掉别人刚写的片。
    """
    staging = staging or build_part_staging()
    await _require_active(db, session=session, staging=staging)

    part_count = _declared_part_count(session)
    if int(part_number) < 1 or int(part_number) > part_count:
        raise ValidationException(f"分片号 {part_number} 超出范围 1..{part_count}")

    written = await staging.write_part(str(session.id), int(part_number), content)
    # ETag 用 md5 与 S3/MinIO 的单片 ETag 同口径，客户端可原样回传。
    etag = hashlib.md5(content, usedforsecurity=False).hexdigest()
    return await _persist_part_row(
        db, session=session, part_number=part_number, etag=etag, written=written
    )


async def record_upload_part_stream(
    db: AsyncSession,
    *,
    session: UploadSession,
    part_number: int,
    chunks: AsyncIterator[bytes],
    staging: PartStaging | None = None,
    max_part_bytes: int | None = None,
) -> dict:
    """流式落分片：边读边计量，超过单分片上限立即 413，不整段驻留内存（P2）。

    ``chunks`` 是请求体的异步字节块迭代器（FastAPI ``Request.stream()``）。计量
    生成器把「超限检查」与「md5 计算」放进同一次遍历，字节只被消费一遍，进程内存
    峰值仅为单个块——这是相对旧 ``Body(...)``（整段读入内存）的核心硬化点。
    """
    staging = staging or build_part_staging()
    await _require_active(db, session=session, staging=staging)

    part_count = _declared_part_count(session)
    if int(part_number) < 1 or int(part_number) > part_count:
        raise ValidationException(f"分片号 {part_number} 超出范围 1..{part_count}")

    limit = int(
        max_part_bytes if max_part_bytes is not None else UPLOAD_MAX_PART_SIZE_BYTES
    )
    digest = hashlib.md5(usedforsecurity=False)
    total = 0

    async def _metered() -> AsyncIterator[bytes]:
        nonlocal total
        async for chunk in chunks:
            if not chunk:
                continue
            total += len(chunk)
            if total > limit:
                raise PayloadTooLargeException(
                    f"分片大小超过上限 {limit // (1024 * 1024)}MB"
                )
            digest.update(chunk)
            yield chunk

    written = await staging.write_part_stream(
        str(session.id), int(part_number), _metered()
    )
    etag = digest.hexdigest()
    return await _persist_part_row(
        db, session=session, part_number=part_number, etag=etag, written=written
    )


async def _reload_parts(db: AsyncSession, session: UploadSession) -> None:
    """重新加载分片集合。

    用 ``db.execute`` 写的 upsert 不经过 ORM 身份映射，内存里的 ``part_records``
    仍是旧集合；直接返回会让响应里的 ``receivedPartNumbers`` 缺一片。
    """
    try:
        await db.refresh(session, attribute_names=["part_records"])
    except Exception:  # noqa: BLE001 - 关系刷新失败时退化为整对象刷新
        await db.refresh(session)


async def complete_upload_session(
    db: AsyncSession,
    *,
    session: UploadSession,
    user: User,
    parts: list[UploadPartRef],
    staging: PartStaging | None = None,
) -> FileModel:
    """按 ``part_number`` 排序流式合并分片，写入 files 表并置会话 COMPLETED。"""
    staging = staging or build_part_staging()
    await _require_active(db, session=session, staging=staging)

    part_count = _declared_part_count(session)
    available = {int(item.part_number) for item in parts} | _stored_part_numbers(session)
    missing = [n for n in range(1, part_count + 1) if n not in available]
    if missing:
        raise ValidationException("缺少分片: " + ",".join(str(n) for n in missing))

    ordered = sorted(available)
    sizes: dict[int, int] = {}
    total = 0
    for number in ordered:
        size = await staging.part_size(str(session.id), number)
        if size is None:
            raise ValidationException(f"分片 {number} 的数据已丢失，请重新上传")
        sizes[number] = int(size)
        total += int(size)
        if total > UPLOAD_MAX_ASSEMBLY_BYTES:
            raise ValidationException(
                "合并后的文件超过 "
                f"{UPLOAD_MAX_ASSEMBLY_BYTES // (1024 ** 2)}MB 的服务端合并上限；"
                "请改用更小的分片集合或联系管理员调整 UPLOAD_MAX_ASSEMBLY_BYTES"
            )

    declared_size = int(session.declared_size or 0)
    if total != declared_size:
        raise ValidationException(
            f"合并后的字节数 {total} 与创建会话时声明的 {declared_size} 不一致，"
            "请重传缺失或有误的分片"
        )

    temp_path, digest = await _assemble_to_temp(staging, str(session.id), ordered, sizes)

    declared_sha256 = (session.declared_sha256 or "").strip().lower()
    if declared_sha256 and declared_sha256 != digest:
        Path(temp_path).unlink(missing_ok=True)
        raise ValidationException("合并后的文件 sha256 与客户端声明不一致（docs/05 §4.2 的 42205）")

    try:
        stored_file = await store_file_path(
            db,
            source_path=Path(temp_path),
            filename=session.declared_filename,
            content_type=session.content_type,
            source_type=FileSourceType.UPLOAD.value,
            owner_id=str(user.id),
            project_id=str(session.project_id),
            is_permanent=True,
            size_bytes=total,
            sha256=digest,
        )
    finally:
        Path(temp_path).unlink(missing_ok=True)

    session.state = "COMPLETED"
    await db.commit()
    await db.refresh(session)
    await staging.discard(str(session.id))
    return stored_file


async def _assemble_to_temp(
    staging: PartStaging, session_id: str, ordered: list[int], sizes: dict[int, int]
) -> tuple[str, str]:
    """把分片按序写进临时文件，返回 ``(临时路径, sha256)``。

    逐片读写 + 增量哈希：峰值内存等于一片大小，而不是整个文件。临时文件放在
    ``STORAGE_PATH`` 下的 ``.assembly-`` 前缀，与正式文件同盘，``store_file_path``
    的复制不会跨文件系统。
    """
    ensure_storage_dir()
    descriptor, raw_path = tempfile.mkstemp(prefix=".assembly-", dir=settings.STORAGE_PATH)
    import os

    os.close(descriptor)
    temp_path = Path(raw_path)
    digest = hashlib.sha256()
    try:
        with temp_path.open("wb") as handle:
            for number in ordered:
                chunk_offset = 0
                content = await staging.read_part(session_id, number)
                if len(content) != sizes[number]:
                    raise ValidationException(
                        f"分片 {number} 的大小在上报后发生变化，请重新上传该分片"
                    )
                view = memoryview(content)
                while chunk_offset < len(content):
                    end = min(chunk_offset + _ASSEMBLY_CHUNK_BYTES, len(content))
                    block = view[chunk_offset:end]
                    digest.update(block)
                    handle.write(block)
                    chunk_offset = end
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return str(temp_path), digest.hexdigest()


async def abort_upload_session(
    db: AsyncSession, *, session: UploadSession, staging: PartStaging | None = None
) -> None:
    """取消会话：置 ABORTED 并清理暂存分片。"""
    if session.state == "COMPLETED":
        raise ConflictException("会话已完成，不能取消")
    session.state = "ABORTED"
    await db.commit()
    await (staging or build_part_staging()).discard(str(session.id))


__all__ = [
    "ACTIVE_STATES",
    "UPLOAD_MAX_ASSEMBLY_BYTES",
    "UPLOAD_MAX_OBJECT_BYTES",
    "UPLOAD_MAX_PART_SIZE_BYTES",
    "UPLOAD_PART_SIZE_BYTES",
    "UPLOAD_SESSION_TTL_HOURS",
    "abort_upload_session",
    "build_object_key",
    "complete_upload_session",
    "create_upload_session",
    "expire_upload_session",
    "find_idempotent_session",
    "get_upload_session",
    "is_expired",
    "part_count_for",
    "record_upload_part",
    "record_upload_part_stream",
    "serialize_upload_session",
]
