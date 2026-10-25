"""分片上传会话领域用例（docs/04 §5.8、docs/05 §4.2）。

设计取舍
--------
**为什么分片落本地临时目录而不是 MinIO Multipart**：本期先落地「可续传 + 可合并」
的能力，MinIO 服务端直传是后续步骤（docs/17 §5.7 明列未落地）。因此分片写到
``STORAGE_PATH/_uploads/{session_id}/{part:05d}.part``，complete 时按序拼装后交给
``store_file_bytes``，与其它上传入口共享同一套 ``files`` 记录与 sha256 口径。

**为什么 complete 有 256MB 上限**：拼装在服务端进程内做，超大文件会同时打满内存与
磁盘。超过上限时显式 422 并指向 MinIO 直传，而不是悄悄 OOM。

**为什么 parts 必须整列重新赋值**：``parts`` 是 JSON 列，SQLAlchemy 不追踪 list 的
原地 mutate。写成 ``session.parts.append(entry)`` 再 commit，数据库里仍是空数组——
续传列表永远为空。必须 ``session.parts = [...]`` + ``flag_modified``。
"""

from __future__ import annotations

import hashlib
import math
import shutil
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.common.exceptions import ConflictException, NotFoundException, ValidationException
from app.common.time import utcnow
from app.config import settings
from app.files.storage_path import safe_storage_filename
from app.files.writer import store_file_bytes
from app.models.files import File as FileModel
from app.models.files import FileSourceType
from app.models.uploads import UploadSession
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
#: 服务端拼装上限 256MB；超出提示改走 MinIO 直传（docs/17 §5.7）。
UPLOAD_MAX_ASSEMBLY_BYTES = settings.UPLOAD_MAX_ASSEMBLY_BYTES

#: 允许继续上传分片 / 合并的状态。其余状态一律 409，避免「已完成/已取消」被续写。
ACTIVE_STATES = ("INITIATED", "UPLOADING")


def part_count_for(size: int) -> int:
    """按 16MB 分片计算片数，至少 1 片（0 字节由 schema 的 ``gt=0`` 挡掉）。"""
    return max(1, math.ceil(int(size) / UPLOAD_PART_SIZE_BYTES))


def parts_directory(session_id: str) -> Path:
    """分片临时目录：``{STORAGE_PATH}/_uploads/{session_id}``。"""
    return Path(settings.STORAGE_PATH) / "_uploads" / str(session_id)


def part_file_path(session_id: str, part_number: int) -> Path:
    """单个分片文件：``{STORAGE_PATH}/_uploads/{session_id}/{part:05d}.part``。"""
    return parts_directory(session_id) / f"{int(part_number):05d}.part"


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


def _normalize_parts(raw) -> list[dict]:
    """``parts`` 可能是 None（旧行/默认值未落库），统一成列表。"""
    if not raw:
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _stored_part_numbers(session: UploadSession) -> set[int]:
    return {
        int(item["partNumber"])
        for item in _normalize_parts(session.parts)
        if item.get("partNumber") is not None
    }


def serialize_upload_session(session: UploadSession) -> dict:
    """会话的对外表示（docs/05 §4.2 的创建与断点续传响应）。"""
    parts = _normalize_parts(session.parts)
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


async def find_idempotent_session(
    db: AsyncSession, *, project_id: str, idempotency_key: str
) -> UploadSession | None:
    """同 project + 同幂等键的既有会话。

    幂等键单独成列而不是塞进 ``parts``：创建会话时还没有任何分片，塞进 ``parts``
    会被第一次上报整列覆盖掉，幂等随即失效。
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
    """创建会话；同幂等键重复调用返回同一会话（不重置状态与已传分片）。"""
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
        content_type=data.content_type,
        object_key=build_object_key(project_id=str(project_id), filename=data.filename),
        part_size=UPLOAD_PART_SIZE_BYTES,
        parts=[],
        state="INITIATED",
        expires_at=utcnow() + timedelta(hours=UPLOAD_SESSION_TTL_HOURS),
        idempotency_key=idempotency_key,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def record_upload_part(
    db: AsyncSession, *, session: UploadSession, part_number: int, content: bytes
) -> dict:
    """落分片字节，并把 ``{partNumber, etag, size}`` 追加进 ``parts``。

    追加而非覆盖：同一片可能被重传（网络抖动），按片号替换自己的旧项、其余保留；
    整列覆盖会让先到的分片全部丢失（docs/04 §5.6「例外与补充」）。
    """
    if session.state not in ACTIVE_STATES:
        raise ConflictException(f"会话状态为 {session.state}，不能继续上传分片")

    part_count = _declared_part_count(session)
    if int(part_number) < 1 or int(part_number) > part_count:
        raise ValidationException(f"分片号 {part_number} 超出范围 1..{part_count}")

    parts_directory(session.id).mkdir(parents=True, exist_ok=True)
    part_file_path(session.id, part_number).write_bytes(content)

    # ETag 用 md5 与 S3/MinIO 的单片 ETag 同口径，客户端可原样回传。
    etag = hashlib.md5(content, usedforsecurity=False).hexdigest()
    entry = {"partNumber": int(part_number), "etag": etag, "size": len(content)}

    current = _normalize_parts(session.parts)
    kept = [item for item in current if item.get("partNumber") != int(part_number)]
    # 整列重新赋值 + flag_modified：JSON 列的原地 append 不会被 SQLAlchemy 感知。
    session.parts = [*kept, entry]
    session.state = "UPLOADING"
    flag_modified(session, "parts")

    await db.commit()
    await db.refresh(session)
    return entry


async def complete_upload_session(
    db: AsyncSession,
    *,
    session: UploadSession,
    user: User,
    parts: list[UploadPartRef],
) -> FileModel:
    """按 ``part_number`` 排序拼装分片，写入 files 表并置会话 COMPLETED。"""
    if session.state not in ACTIVE_STATES:
        raise ConflictException(f"会话状态为 {session.state}，不能再次合并")

    part_count = _declared_part_count(session)
    available = {int(item.part_number) for item in parts} | _stored_part_numbers(session)
    missing = [n for n in range(1, part_count + 1) if n not in available]
    if missing:
        raise ValidationException(
            "缺少分片: " + ",".join(str(n) for n in missing)
        )

    ordered = sorted(available)
    total = 0
    for number in ordered:
        path = part_file_path(session.id, number)
        if not path.exists():
            raise ValidationException(f"分片 {number} 的数据已丢失，请重新上传")
        total += path.stat().st_size
        if total > UPLOAD_MAX_ASSEMBLY_BYTES:
            raise ValidationException(
                "合并后的文件超过 "
                f"{UPLOAD_MAX_ASSEMBLY_BYTES // (1024 ** 2)}MB 的服务端拼装上限；"
                "后续步骤将接入 MinIO 分片直传（docs/17 §5.7），届时无需本地拼装"
            )

    buffer = bytearray()
    for number in ordered:
        buffer.extend(part_file_path(session.id, number).read_bytes())

    digest = hashlib.sha256(buffer).hexdigest()
    stored_file = await store_file_bytes(
        db,
        content=bytes(buffer),
        filename=session.declared_filename,
        content_type=session.content_type,
        source_type=FileSourceType.UPLOAD.value,
        owner_id=str(user.id),
        project_id=str(session.project_id),
        is_permanent=True,
        sha256=digest,
    )
    session.state = "COMPLETED"
    await db.commit()
    await db.refresh(session)
    _cleanup_parts(session.id)
    return stored_file


async def abort_upload_session(db: AsyncSession, *, session: UploadSession) -> None:
    """取消会话：置 ABORTED 并清理临时分片。"""
    if session.state == "COMPLETED":
        raise ConflictException("会话已完成，不能取消")
    session.state = "ABORTED"
    await db.commit()
    _cleanup_parts(session.id)


def _cleanup_parts(session_id: str) -> None:
    """尽力清理分片目录；清理失败不回滚已完成的业务结果。"""
    shutil.rmtree(parts_directory(session_id), ignore_errors=True)


__all__ = [
    "ACTIVE_STATES",
    "UPLOAD_MAX_ASSEMBLY_BYTES",
    "UPLOAD_MAX_OBJECT_BYTES",
    "UPLOAD_PART_SIZE_BYTES",
    "UPLOAD_SESSION_TTL_HOURS",
    "abort_upload_session",
    "build_object_key",
    "complete_upload_session",
    "create_upload_session",
    "find_idempotent_session",
    "get_upload_session",
    "part_count_for",
    "part_file_path",
    "parts_directory",
    "record_upload_part",
    "serialize_upload_session",
]
