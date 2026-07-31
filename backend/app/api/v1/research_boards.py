"""私有科研白板接口。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.models.artifacts import Artifact
from app.models.users import User
from app.models.files import File
from app.models.tools import Tool, ToolStatus
from app.models.workflows import ResearchBoard
from app.schemas.research_boards import (
    BoardContent,
    ResearchBoardCreate,
    ResearchBoardUpdate,
)
from app.logging.audit import AuditAction, ResourceType, get_audit_logger
from app.services.project_access import load_project_membership, require_project_role

router = APIRouter()


def audit_board_read(*, admin_id: str, board_id: str, owner_id: str) -> None:
    get_audit_logger().log_admin_operation(
        admin_id=admin_id,
        action=AuditAction.READ,
        target_type=ResourceType.RESEARCH_BOARD,
        target_id=board_id,
        owner_id=owner_id,
    )


async def _validate_references(
    content: BoardContent,
    current_user: User,
    db: AsyncSession,
    *,
    project_id: str | None,
) -> None:
    file_ids = {node.file_id for node in content.nodes if node.file_id}
    if file_ids:
        result = await db.execute(
            select(File.id).where(
                File.id.in_(file_ids),
                File.owner_id == current_user.id,
                File.deleted_at.is_(None),
                File.is_corrupted.is_(False),
            )
        )
        accessible_ids = set(result.scalars())
        if accessible_ids != file_ids:
            raise HTTPException(
                status_code=400, detail="白板包含不存在或无权访问的文件"
            )

    tool_ids = {node.tool_id for node in content.nodes if node.tool_id}
    if tool_ids:
        result = await db.execute(
            select(Tool.id).where(
                Tool.id.in_(tool_ids),
                Tool.status == ToolStatus.PUBLISHED.value,
                or_(Tool.owner_id == current_user.id, Tool.is_public.is_(True)),
            )
        )
        accessible_ids = set(result.scalars())
        if accessible_ids != tool_ids:
            raise HTTPException(status_code=400, detail="白板包含不存在或不可用的工具")

    artifact_ids = {node.artifact_id for node in content.nodes if node.artifact_id}
    if artifact_ids:
        query = select(Artifact.id).where(Artifact.id.in_(artifact_ids))
        if project_id:
            query = query.where(Artifact.project_id == project_id)
        else:
            query = query.where(Artifact.created_by == current_user.id)
        result = await db.execute(query)
        accessible_ids = set(result.scalars())
        if accessible_ids != artifact_ids:
            raise HTTPException(
                status_code=400, detail="白板包含不存在或跨项目的 Artifact"
            )


def _serialize(board: ResearchBoard) -> dict[str, Any]:
    return {
        "id": board.id,
        "project_id": board.project_id,
        "owner_id": board.owner_id,
        "name": board.name,
        "description": board.description,
        "content": board.content or {},
        "version": board.version,
        "created_at": board.created_at,
        "updated_at": board.updated_at,
    }


def _serialize_summary(board: ResearchBoard) -> dict[str, Any]:
    return {
        "id": board.id,
        "project_id": board.project_id,
        "owner_id": board.owner_id,
        "name": board.name,
        "description": board.description,
        "version": board.version,
        "node_count": len((board.content or {}).get("nodes", [])),
        "created_at": board.created_at,
        "updated_at": board.updated_at,
    }


async def _load_board(
    board_id: str, current_user: User, db: AsyncSession
) -> ResearchBoard:
    board = await db.get(ResearchBoard, board_id)
    if not board:
        raise HTTPException(status_code=404, detail="科研白板不存在")
    if current_user.role == "admin":
        return board
    if board.project_id:
        await load_project_membership(
            db, project_id=board.project_id, user_id=current_user.id
        )
        return board
    if board.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="科研白板不存在")
    return board


async def _require_board_write_access(
    board: ResearchBoard,
    current_user: User,
    db: AsyncSession,
) -> None:
    if board.project_id:
        await require_project_role(
            db,
            project_id=board.project_id,
            user=current_user,
            allowed_roles={"owner", "editor"},
        )
        return
    if board.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="管理员仅可查看科研白板")


@router.get("", response_model=dict)
async def list_research_boards(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(ResearchBoard)
    if project_id:
        if current_user.role != "admin":
            await load_project_membership(
                db, project_id=project_id, user_id=current_user.id
            )
        query = query.where(ResearchBoard.project_id == project_id)
    elif current_user.role != "admin":
        query = query.where(ResearchBoard.owner_id == current_user.id)
    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    result = await db.execute(
        query.order_by(ResearchBoard.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return paginated_response(
        items=[_serialize_summary(board) for board in result.scalars()],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=dict)
async def create_research_board(
    data: ResearchBoardCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.project_id:
        await require_project_role(
            db,
            project_id=data.project_id,
            user=current_user,
            allowed_roles={"owner", "editor"},
        )
    await _validate_references(
        data.content, current_user, db, project_id=data.project_id
    )
    board = ResearchBoard(owner_id=current_user.id, **data.model_dump())
    db.add(board)
    await db.commit()
    await db.refresh(board)
    return success_response(data=_serialize(board), message="科研白板已创建")


@router.get("/{board_id}", response_model=dict)
async def get_research_board(
    board_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    board = await _load_board(board_id, current_user, db)
    if current_user.role == "admin" and board.owner_id != current_user.id:
        audit_board_read(
            admin_id=current_user.id, board_id=board.id, owner_id=board.owner_id
        )
    return success_response(data=_serialize(board))


@router.patch("/{board_id}", response_model=dict)
async def update_research_board(
    board_id: str,
    data: ResearchBoardUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    board = await _load_board(board_id, current_user, db)
    await _require_board_write_access(board, current_user, db)
    if board.version != data.version:
        raise HTTPException(
            status_code=409, detail="科研白板已被其他会话更新，请刷新后重试"
        )
    if data.content is not None:
        await _validate_references(
            data.content, current_user, db, project_id=board.project_id
        )
    for field, value in data.model_dump(
        exclude_unset=True, exclude={"version"}
    ).items():
        setattr(board, field, value)
    board.version += 1
    await db.commit()
    await db.refresh(board)
    return success_response(data=_serialize(board), message="科研白板已保存")


@router.delete("/{board_id}", response_model=dict)
async def delete_research_board(
    board_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    board = await _load_board(board_id, current_user, db)
    await _require_board_write_access(board, current_user, db)
    await db.delete(board)
    await db.commit()
    return success_response(message="科研白板已删除")


@router.post("/{board_id}/workflow-draft", response_model=dict)
async def create_workflow_draft(
    board_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    board = await _load_board(board_id, current_user, db)
    if board.project_id:
        await require_project_role(
            db,
            project_id=board.project_id,
            user=current_user,
            allowed_roles={"owner", "editor", "runner"},
        )
    elif board.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="管理员仅可查看科研白板")
    tools = [
        node
        for node in (board.content or {}).get("nodes", [])
        if node.get("type") == "tool" and node.get("tool_id")
    ]
    tool_ids = {str(node["tool_id"]) for node in tools}
    result = await db.execute(
        select(Tool).where(
            Tool.id.in_(tool_ids),
            Tool.status == ToolStatus.PUBLISHED.value,
            or_(Tool.owner_id == current_user.id, Tool.is_public.is_(True)),
        )
    )
    tools_by_id = {tool.id: tool for tool in result.scalars()}
    if len(tools_by_id) != len(tool_ids):
        raise HTTPException(status_code=400, detail="白板中的工具已不存在或不可用")
    nodes = [
        {
            "id": str(node["id"]),
            "type": "tool",
            "tool_id": str(node["tool_id"]),
            "toolSlugs": [tools_by_id[str(node["tool_id"])].slug],
            "recommendedToolSlug": tools_by_id[str(node["tool_id"])].slug,
            "titleKey": tools_by_id[str(node["tool_id"])].name,
            "position": node.get("position", {}),
        }
        for node in tools
    ]
    selected_tool_by_node = {
        str(node["id"]): tools_by_id[str(node["tool_id"])].slug for node in tools
    }
    definition = {
        "nodes": nodes,
        "edges": [],
        "selected_tool_by_node": selected_tool_by_node,
        "artifact_bindings_by_node": {},
    }
    return success_response(
        data={
            "name": f"{board.name} workflow",
            "description": board.description,
            "intent": "research_board_conversion",
            "definition": definition,
            "input_files": {},
            "requested_outputs": [],
            "analysis_trace": [],
            "nodes": nodes,
        },
        message="工作流草稿已生成",
    )
