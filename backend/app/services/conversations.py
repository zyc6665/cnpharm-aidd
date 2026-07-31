"""Project-scoped conversation access and immutable message operations."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversations import Conversation, ConversationBranch, ConversationMessage
from app.models.projects import ProjectMember
from app.models.users import User
from app.services.project_access import load_project_membership


def plain_text_from_blocks(blocks: list[dict[str, Any]]) -> str:
    return "\n".join(
        str(block.get("text", "")).strip()
        for block in blocks
        if block.get("type") == "text" and str(block.get("text", "")).strip()
    )


async def load_conversation_for_member(
    db: AsyncSession,
    *,
    conversation_id: str,
    user_id: str,
) -> tuple[Conversation, ProjectMember]:
    result = await db.execute(
        select(Conversation, ProjectMember)
        .join(ProjectMember, ProjectMember.project_id == Conversation.project_id)
        .where(Conversation.id == conversation_id, ProjectMember.user_id == user_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return row[0], row[1]


async def create_conversation(
    db: AsyncSession,
    *,
    project_id: str,
    user: User,
    title: str,
) -> tuple[Conversation, ConversationBranch]:
    await load_project_membership(db, project_id=project_id, user_id=user.id)
    conversation = Conversation(project_id=project_id, created_by=user.id, title=title)
    db.add(conversation)
    await db.flush()
    branch = ConversationBranch(
        conversation_id=conversation.id,
        created_by=user.id,
        title="主分支",
        is_root=True,
    )
    db.add(branch)
    await db.flush()
    return conversation, branch


async def append_message(
    db: AsyncSession,
    *,
    conversation: Conversation,
    user: User,
    role: str,
    content: list[dict[str, Any]],
    branch_id: str | None = None,
) -> ConversationMessage:
    branch_query = select(ConversationBranch).where(
        ConversationBranch.conversation_id == conversation.id
    )
    if branch_id:
        branch_query = branch_query.where(ConversationBranch.id == branch_id)
    else:
        branch_query = branch_query.where(ConversationBranch.is_root.is_(True))
    branch = (await db.execute(branch_query.with_for_update())).scalar_one_or_none()
    if branch is None:
        raise HTTPException(status_code=404, detail="会话分支不存在")
    current_sequence = (
        await db.execute(
            select(func.max(ConversationMessage.sequence)).where(
                ConversationMessage.conversation_id == conversation.id,
                ConversationMessage.branch_id == branch.id,
            )
        )
    ).scalar_one()
    message = ConversationMessage(
        conversation_id=conversation.id,
        branch_id=branch.id,
        author_id=user.id,
        role=role,
        content=content,
        plain_text=plain_text_from_blocks(content),
        sequence=(current_sequence or 0) + 1,
    )
    db.add(message)
    await db.flush()
    return message


async def branch_message(
    db: AsyncSession,
    *,
    source: ConversationMessage,
    user: User,
    content: list[dict[str, Any]],
    title: str | None,
) -> tuple[ConversationBranch, ConversationMessage]:
    branch = ConversationBranch(
        conversation_id=source.conversation_id,
        created_by=user.id,
        parent_branch_id=source.branch_id,
        forked_from_message_id=source.id,
        title=title or f"从消息 {source.sequence} 分支",
    )
    db.add(branch)
    await db.flush()
    message = ConversationMessage(
        conversation_id=source.conversation_id,
        branch_id=branch.id,
        author_id=user.id,
        parent_message_id=source.id,
        role=source.role,
        content=content,
        plain_text=plain_text_from_blocks(content),
        sequence=source.sequence,
    )
    db.add(message)
    await db.flush()
    return branch, message
