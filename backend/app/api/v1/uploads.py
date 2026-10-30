"""分片上传会话 API（docs/05 §4.2、docs/04 §5.8）。

四个端点覆盖一次完整的大文件上传，外加一个断点续传查询端点：

1. ``POST /uploads`` 创建会话（必填 ``X-Idempotency-Key``，同键重复创建返回同一会话）；
2. ``GET /uploads/{id}`` 查询已收到的分片（断点续传，前端只重传 ``missingPartNumbers``）；
3. ``PUT /uploads/{id}/parts/{partNumber}`` 上报单个分片（原始字节体）；
4. ``POST /uploads/{id}:complete`` 按片号排序流式合并并落 files 表；
5. ``DELETE /uploads/{id}`` 取消会话并清理暂存分片。

领域语义全部在 ``app.services.uploads``，本模块只做 HTTP 语义、权限与响应包装。
权限沿用项目内写角色（owner/editor）；非成员 404「研究项目不存在」，角色不符 403。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.responses import success_response
from app.database.session import get_db
from app.models.users import User
from app.schemas.uploads import UploadCompleteRequest, UploadSessionCreate
from app.services import uploads as uploads_service
from app.services.project_access import require_project_role

router = APIRouter(prefix="/uploads", tags=["分片上传"])

#: 项目内允许创建/续传/合并/取消上传会话的角色。
WRITE_ROLES = ("owner", "editor")


async def _load_authorized_session(db: AsyncSession, *, upload_id: str, user: User):
    """取会话并校验调用者在会话所属项目里有写权限。

    先解析会话再判权限，是为了让「别人的上传 id」也走 404 而不是 403——两者都能
    不暴露存在性，但 404 与「会话不存在」语义一致，前端无需区分。
    """
    session = await uploads_service.get_upload_session(db, upload_id=upload_id)
    await require_project_role(
        db,
        project_id=str(session.project_id),
        user=user,
        allowed_roles=WRITE_ROLES,
    )
    return session


@router.post("", response_model=dict)
async def create_upload(
    data: UploadSessionCreate,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建分片上传会话（幂等：同 project + 同幂等键返回同一会话）。"""
    await require_project_role(
        db,
        project_id=data.project_id,
        user=current_user,
        allowed_roles=WRITE_ROLES,
    )
    session = await uploads_service.create_upload_session(
        db,
        project_id=data.project_id,
        user=current_user,
        data=data,
        idempotency_key=x_idempotency_key,
    )
    return success_response(uploads_service.serialize_upload_session(session))


@router.get("/{upload_id}", response_model=dict)
async def get_upload(
    upload_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """断点续传：返回已完成的分片，前端只重传 ``missingPartNumbers``。"""
    session = await _load_authorized_session(db, upload_id=upload_id, user=current_user)
    return success_response(uploads_service.serialize_upload_session(session))


@router.put("/{upload_id}/parts/{part_number}", response_model=dict)
async def upload_part(
    request: Request,
    upload_id: str = Path(...),
    part_number: int = Path(..., ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上报单个分片。请求体为该分片的原始字节（``application/octet-stream``）。

    分片按块流式消费：边读边计量，累计超过单分片上限（``UPLOAD_MAX_PART_SIZE_BYTES``）
    立即返回 413 业务错误，不再用 ``Body(...)`` 把整段分片读入进程内存（P2 硬化）。
    """
    session = await _load_authorized_session(db, upload_id=upload_id, user=current_user)
    entry = await uploads_service.record_upload_part_stream(
        db, session=session, part_number=part_number, chunks=request.stream()
    )
    return success_response(
        {
            "uploadId": str(session.id),
            "partNumber": entry["partNumber"],
            "etag": entry["etag"],
            "size": entry["size"],
            "received": True,
        }
    )


@router.post("/{upload_id}:complete", response_model=dict)
async def complete_upload(
    upload_id: str = Path(...),
    data: UploadCompleteRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按 ``part_number`` 排序合并分片，返回 ``urn``/``size``/``sha256``。"""
    session = await _load_authorized_session(db, upload_id=upload_id, user=current_user)
    parts = data.parts if data is not None else []
    stored_file = await uploads_service.complete_upload_session(
        db, session=session, user=current_user, parts=parts
    )
    return success_response(
        {
            "urn": f"file:{stored_file.id}",
            "fileId": str(stored_file.id),
            "size": int(stored_file.size_bytes or 0),
            "sha256": stored_file.sha256,
            "uploadId": str(session.id),
            "state": session.state,
        }
    )


@router.delete("/{upload_id}", response_model=dict)
async def abort_upload(
    upload_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取消会话并清理临时分片（docs/05 §4.2 ④）。"""
    session = await _load_authorized_session(db, upload_id=upload_id, user=current_user)
    await uploads_service.abort_upload_session(db, session=session)
    return success_response(
        {"uploadId": str(session.id), "state": session.state}
    )


__all__ = ["router"]
