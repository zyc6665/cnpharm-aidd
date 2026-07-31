"""用户工作台聚合接口。"""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.common.responses import success_response
from app.common.time import utcnow
from app.database.session import get_db
from app.models.files import File
from app.models.tasks import Task
from app.models.tools import Tool
from app.models.users import User
from app.models.workflows import ResearchBoard, WorkflowDefinition

router = APIRouter()
ATTENTION_STATUSES = {'pending', 'running', 'failure'}


@router.get('/overview', response_model=dict)
async def get_workspace_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task_result = await db.execute(
        select(Task)
        .options(selectinload(Task.tool))
        .where(Task.user_id == current_user.id)
        .order_by(Task.updated_at.desc())
        .limit(12)
    )
    count_result = await db.execute(
        select(func.lower(Task.status), func.count(Task.id))
        .where(Task.user_id == current_user.id)
        .group_by(func.lower(Task.status))
    )
    task_status_counts = {
        'pending': 0,
        'running': 0,
        'success': 0,
        'failure': 0,
        'canceled': 0,
        **{str(status): count for status, count in count_result.all()},
    }
    board_result = await db.execute(
        select(ResearchBoard)
        .where(ResearchBoard.owner_id == current_user.id)
        .order_by(ResearchBoard.updated_at.desc())
        .limit(6)
    )
    workflow_result = await db.execute(
        select(WorkflowDefinition)
        .where(WorkflowDefinition.user_id == current_user.id)
        .order_by(WorkflowDefinition.updated_at.desc())
        .limit(6)
    )
    file_result = await db.execute(
        select(File)
        .where(
            File.owner_id == current_user.id,
            File.deleted_at.is_(None),
            File.is_corrupted.is_(False),
            or_(File.expires_at.is_(None), File.expires_at > utcnow()),
        )
        .order_by(File.updated_at.desc())
        .limit(8)
    )
    frequent_tool_result = await db.execute(
        select(Tool.id, Tool.name, Tool.slug, func.count(Task.id).label('usage_count'))
        .join(Task, Task.tool_id == Tool.id)
        .where(Task.user_id == current_user.id)
        .group_by(Tool.id, Tool.name, Tool.slug)
        .order_by(func.count(Task.id).desc(), Tool.name.asc())
        .limit(6)
    )
    tasks = list(task_result.scalars())
    return success_response(data={
        'tasks': [
            {
                'id': task.id,
                'name': task.name,
                'status': (task.status or '').lower(),
                'progress': task.progress,
                'error_message': task.error_message,
                'tool_id': task.tool_id,
                'tool_name': task.tool.name if task.tool else None,
                'tool_slug': task.tool.slug if task.tool else None,
                'updated_at': task.updated_at,
                'created_at': task.created_at,
            }
            for task in tasks
        ],
        'attention_task_count': sum(task_status_counts[status] for status in ATTENTION_STATUSES),
        'task_status_counts': task_status_counts,
        'boards': [
            {
                'id': board.id,
                'name': board.name,
                'node_count': len((board.content or {}).get('nodes', [])),
                'updated_at': board.updated_at,
            }
            for board in board_result.scalars()
        ],
        'workflows': [
            {
                'id': workflow.id,
                'name': workflow.name,
                'status': workflow.status,
                'updated_at': workflow.updated_at,
            }
            for workflow in workflow_result.scalars()
        ],
        'files': [
            {
                'id': file.id,
                'filename': file.filename,
                'content_type': file.content_type,
                'size_bytes': file.size_bytes,
                'updated_at': file.updated_at,
            }
            for file in file_result.scalars()
        ],
        'frequent_tools': [
            {'id': tool_id, 'name': name, 'slug': slug, 'usage_count': usage_count}
            for tool_id, name, slug, usage_count in frequent_tool_result.all()
        ],
    })
