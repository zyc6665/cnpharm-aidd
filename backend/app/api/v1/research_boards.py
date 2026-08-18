"""私有科研白板接口。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.feature_flags import require_feature_flag
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
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
from app.services.research_board_content import (
    board_node_count,
    normalize_board_content,
)

router = APIRouter(
    dependencies=[Depends(require_feature_flag("PROJECT_RESEARCH_BOARD_ENABLED"))]
)


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
        "content": normalize_board_content(board.content),
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
        "node_count": board_node_count(board.content),
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


def _artifact_standard_ref(artifact: Artifact) -> str | None:
    if artifact.standard_type and artifact.standard_version:
        return f"{artifact.standard_type}@{artifact.standard_version}"
    semantic_type = str(artifact.semantic_type or "").strip()
    return semantic_type or None


def _artifact_primary_file_id(artifact: Artifact) -> str | None:
    latest_version = artifact.latest_version
    if latest_version is None:
        return None
    version_files = list(latest_version.files or [])
    if not version_files:
        return None
    primary_link = next((item for item in version_files if item.is_primary), None)
    return str((primary_link or version_files[0]).file_id)


def _tool_version_summary(tool: Tool) -> dict[str, Any] | None:
    current_version = tool.current_version
    if current_version is None:
        return None
    return {
        "id": str(current_version.id),
        "version": current_version.version,
        "is_active": bool(current_version.is_active),
        "deprecated": bool(current_version.deprecated),
    }


def _tool_artifacts_config(tool: Tool) -> dict[str, Any]:
    current_version = tool.current_version
    config = current_version.config if current_version is not None else None
    if not isinstance(config, dict):
        return {}

    manifest = config.get("tool_package_manifest")
    if not isinstance(manifest, dict):
        tool_package = config.get("tool_package")
        if isinstance(tool_package, dict):
            manifest = tool_package.get("manifest")
    if isinstance(manifest, dict) and isinstance(manifest.get("artifacts"), dict):
        return manifest["artifacts"]

    artifacts = config.get("artifacts")
    return artifacts if isinstance(artifacts, dict) else {}


def _normalize_artifact_input_slot(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = str(item.get("name") or item.get("field") or "").strip()
    artifact_type = str(
        item.get("type") or item.get("semantic_type") or item.get("artifact_type") or ""
    ).strip()
    if not name or not artifact_type:
        return None
    return {
        "name": name,
        "type": artifact_type,
        "required": bool(item.get("required", True)),
    }


def _normalize_artifact_output_slot(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = str(item.get("name") or item.get("field") or item.get("path") or "").strip()
    artifact_type = str(
        item.get("type") or item.get("semantic_type") or item.get("artifact_type") or ""
    ).strip()
    if not name or not artifact_type:
        return None
    return {
        "name": name,
        "type": artifact_type,
        "cardinality": str(item.get("cardinality") or "one"),
        "required": bool(item.get("required", True)),
    }


def _tool_artifact_input_slots(tool: Tool) -> list[dict[str, Any]]:
    artifacts = _tool_artifacts_config(tool)
    return [
        slot
        for slot in (_normalize_artifact_input_slot(item) for item in artifacts.get("inputs", []))
        if slot is not None
    ]


def _tool_artifact_output_slots(tool: Tool) -> list[dict[str, Any]]:
    artifacts = _tool_artifacts_config(tool)
    return [
        slot
        for slot in (_normalize_artifact_output_slot(item) for item in artifacts.get("outputs", []))
        if slot is not None
    ]


def _board_edges_by_target(content_edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    edges_by_target: dict[str, list[dict[str, Any]]] = {}
    for edge in content_edges:
        target = str(edge.get("target") or "")
        if target:
            edges_by_target.setdefault(target, []).append(edge)
    return edges_by_target


def _explicit_artifact_input_binding(
    *,
    node_id: str,
    slot: dict[str, Any],
    incoming_edges: list[dict[str, Any]],
    content_nodes_by_id: dict[str, dict[str, Any]],
    tools_by_id: dict[str, Tool],
    artifact_sources_by_node: dict[str, dict[str, str]],
) -> dict[str, Any] | None:
    slot_name = str(slot["name"])
    slot_type = str(slot["type"])
    for edge in incoming_edges:
        target_input = edge.get("target_input")
        if target_input and str(target_input) != slot_name:
            continue
        source_node_id = str(edge.get("source") or "")
        artifact_source = artifact_sources_by_node.get(source_node_id)
        if artifact_source and artifact_source.get("semantic_type") == slot_type:
            return {
                "artifact_input": f"workflow_input:{slot_type}",
                "artifact_version_id": artifact_source.get("artifact_version_id") or "",
                "edge": {
                    "id": f"{source_node_id}->{node_id}:{slot_type}",
                    "source": source_node_id,
                    "target": node_id,
                    "source_output": slot_type,
                    "target_input": slot_name,
                },
            }

        source_node = content_nodes_by_id.get(source_node_id)
        if not source_node or source_node.get("type") != "tool" or not source_node.get("tool_id"):
            continue
        source_tool = tools_by_id.get(str(source_node["tool_id"]))
        if not source_tool:
            continue
        output_slot = _matching_output_slot(
            _tool_artifact_output_slots(source_tool),
            slot_type=slot_type,
            source_output=edge.get("source_output"),
        )
        if output_slot:
            source_output = str(output_slot["name"])
            return {
                "artifact_input": f"node:{source_node_id}:{source_output}",
                "artifact_version_id": "",
                "edge": {
                    "id": f"{source_node_id}->{node_id}:{source_output}",
                    "source": source_node_id,
                    "target": node_id,
                    "source_output": source_output,
                    "target_input": slot_name,
                },
            }
    return None


def _matching_output_slot(
    output_slots: list[dict[str, Any]],
    *,
    slot_type: str,
    source_output: Any,
) -> dict[str, Any] | None:
    if source_output:
        explicit_name = str(source_output)
        explicit = next(
            (
                item
                for item in output_slots
                if str(item.get("name")) == explicit_name and str(item.get("type")) == slot_type
            ),
            None,
        )
        if explicit:
            return explicit
    return next((item for item in output_slots if str(item.get("type")) == slot_type), None)


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
    normalized_content = normalize_board_content(board.content)
    content_nodes = normalized_content["nodes"]
    content_edges = normalized_content["edges"]
    content_nodes_by_id = {
        str(node.get("id")): node for node in content_nodes if str(node.get("id") or "")
    }
    board_edges_by_target = _board_edges_by_target(content_edges)
    tool_nodes = [
        node
        for node in content_nodes
        if node.get("type") == "tool" and node.get("tool_id")
    ]
    artifact_nodes = [
        node
        for node in content_nodes
        if node.get("type") == "artifact" and node.get("artifact_id")
    ]

    tool_ids = {str(node["tool_id"]) for node in tool_nodes}
    tools_by_id: dict[str, Tool] = {}
    if tool_ids:
        result = await db.execute(
            select(Tool)
            .options(selectinload(Tool.current_version))
            .where(
                Tool.id.in_(tool_ids),
                Tool.status == ToolStatus.PUBLISHED.value,
                or_(Tool.owner_id == current_user.id, Tool.is_public.is_(True)),
            )
        )
        tools_by_id = {tool.id: tool for tool in result.scalars()}
    if len(tools_by_id) != len(tool_ids):
        raise HTTPException(status_code=400, detail="白板中的工具已不存在或不可用")

    artifact_ids = {str(node["artifact_id"]) for node in artifact_nodes}
    artifacts_by_id: dict[str, Artifact] = {}
    if artifact_ids:
        artifact_query = (
            select(Artifact)
            .options(
                selectinload(Artifact.latest_version)
                .selectinload(ArtifactVersion.files)
                .selectinload(ArtifactVersionFile.file)
            )
            .where(Artifact.id.in_(artifact_ids))
        )
        if board.project_id:
            artifact_query = artifact_query.where(Artifact.project_id == board.project_id)
        else:
            artifact_query = artifact_query.where(Artifact.created_by == current_user.id)
        artifact_result = await db.execute(artifact_query)
        artifacts_by_id = {artifact.id: artifact for artifact in artifact_result.scalars()}
    if len(artifacts_by_id) != len(artifact_ids):
        raise HTTPException(status_code=400, detail="白板中的 Artifact 已不存在或不可用")

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    selected_tool_by_node: dict[str, str] = {}
    artifact_bindings_by_node: dict[str, dict[str, str]] = {}
    artifact_sources_by_type: dict[str, dict[str, str]] = {}
    artifact_sources_by_node: dict[str, dict[str, str]] = {}
    input_files: dict[str, str] = {}

    for node in content_nodes:
        if node.get("type") != "artifact" or not node.get("artifact_id"):
            continue
        artifact = artifacts_by_id[str(node["artifact_id"])]
        semantic_type = _artifact_standard_ref(artifact)
        if not semantic_type:
            continue
        latest_version_id = (
            str(artifact.latest_version.id)
            if artifact.latest_version is not None
            else str(artifact.latest_version_id or "")
        )
        file_id = _artifact_primary_file_id(artifact)
        source = {
            "node_id": str(node.get("id") or ""),
            "semantic_type": semantic_type,
            "artifact_version_id": latest_version_id,
            "file_id": file_id or "",
        }
        artifact_sources_by_node[source["node_id"]] = source
        artifact_sources_by_type.setdefault(semantic_type, source)
        if file_id:
            input_files.setdefault(semantic_type, file_id)

    for node in content_nodes:
        node_id = str(node.get("id") or "")
        if node.get("type") == "artifact" and node.get("artifact_id"):
            artifact = artifacts_by_id[str(node["artifact_id"])]
            semantic_type = _artifact_standard_ref(artifact)
            if not semantic_type:
                continue
            latest_version_id = (
                str(artifact.latest_version.id)
                if artifact.latest_version is not None
                else str(artifact.latest_version_id or "")
            )
            nodes.append(
                {
                    "id": node_id,
                    "kind": "input",
                    "type": "artifact",
                    "semantic_type": semantic_type,
                    "titleKey": artifact.name,
                    "position": node.get("position", {}),
                    "artifact_id": str(artifact.id),
                    "artifact_version_id": latest_version_id or None,
                }
            )
            continue

        if node.get("type") != "tool" or not node.get("tool_id"):
            continue

        tool = tools_by_id[str(node["tool_id"])]
        input_slots = _tool_artifact_input_slots(tool)
        output_slots = _tool_artifact_output_slots(tool)
        artifact_inputs: dict[str, str] = {}
        tool_bindings: dict[str, str] = {}

        for slot in input_slots:
            binding = _explicit_artifact_input_binding(
                node_id=node_id,
                slot=slot,
                incoming_edges=board_edges_by_target.get(node_id, []),
                content_nodes_by_id=content_nodes_by_id,
                tools_by_id=tools_by_id,
                artifact_sources_by_node=artifact_sources_by_node,
            )
            if binding:
                artifact_inputs[str(slot["name"])] = binding["artifact_input"]
                if binding.get("artifact_version_id"):
                    tool_bindings[str(slot["name"])] = binding["artifact_version_id"]
                edges.append(binding["edge"])
                continue

            source = artifact_sources_by_type.get(str(slot["type"]))
            if not source:
                continue
            artifact_inputs[str(slot["name"])] = f"workflow_input:{slot['type']}"
            if source.get("artifact_version_id"):
                tool_bindings[str(slot["name"])] = source["artifact_version_id"]
            edges.append(
                {
                    "id": f"{source['node_id']}->{node_id}:{slot['type']}",
                    "source": source["node_id"],
                    "target": node_id,
                    "source_output": str(slot["type"]),
                    "target_input": str(slot["name"]),
                }
            )

        tool_node = {
            "id": node_id,
            "kind": "tool",
            "type": "tool",
            "tool_id": str(node["tool_id"]),
            "tool_slug": tool.slug,
            "toolSlugs": [tool.slug],
            "recommendedToolSlug": tool.slug,
            "titleKey": tool.name,
            "position": node.get("position", {}),
        }
        tool_version = _tool_version_summary(tool)
        if tool_version:
            tool_node["tool_version"] = tool_version
        if input_slots:
            tool_node["artifact_input_slots"] = input_slots
            tool_node["artifact_inputs"] = artifact_inputs
        if output_slots:
            tool_node["artifact_outputs"] = output_slots
        nodes.append(tool_node)
        selected_tool_by_node[node_id] = tool.slug
        if tool_bindings:
            artifact_bindings_by_node[node_id] = tool_bindings

    definition = {
        "nodes": nodes,
        "edges": edges,
        "selected_tool_by_node": selected_tool_by_node,
        "artifact_bindings_by_node": artifact_bindings_by_node,
    }
    return success_response(
        data={
            "name": f"{board.name} workflow",
            "description": board.description,
            "intent": "research_board_conversion",
            "definition": definition,
            "input_files": input_files,
            "requested_outputs": [],
            "analysis_trace": [],
            "nodes": nodes,
        },
        message="工作流草稿已生成",
    )
