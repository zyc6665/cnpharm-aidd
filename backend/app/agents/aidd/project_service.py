"""Project-scoped AIDD Agent planning, approval, and execution lifecycle."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.aidd.event_publisher import AgentEventPublisher
from app.agents.aidd.graph_nodes import build_project_lvpocket_plan_node
from app.common.time import utcnow
from app.models.agent import AgentRun
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.conversations import Conversation, PlanDecision, PlanVersion
from app.models.tasks import Task
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User
from app.schemas.tasks import TaskCreate
from app.services.conversations import append_message
from app.services.project_access import load_project_membership, require_project_role
from app.tasks.cancellation import cancel_platform_task
from app.tasks.direct_runner import direct_task_runner as default_direct_task_runner
from app.tasks.service import create_and_schedule_tool_task
from app.tool_packages.config_resolver import tool_package_v2_manifest
from app.tool_packages.schemas import ToolPackageV2Manifest


LVPOCKET_SLUG = "lvpocket-pocket-prediction"
PROJECT_AGENT_RUN_OPERATION_ROLES = {"owner", "runner"}
TERMINAL_RUN_STATUSES = {"success", "failure", "canceled"}
ACTIVE_STEP_STATUSES = {"pending", "ready", "dispatching", "waiting_task", "running"}


@dataclass(frozen=True)
class ProjectPlanResult:
    run: AgentRun
    plan_version: PlanVersion | None


@dataclass(frozen=True)
class ProjectTaskSubmission:
    task: Task
    tool_slug: str

    def as_execution_payload(self) -> dict[str, Any]:
        return {
            "execution_id": self.task.id,
            "task_id": self.task.id,
            "state": "queued",
            "tool_slug": self.tool_slug,
        }


class ProjectAgentService:
    """Own state transitions that prompts and graph nodes must not perform."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        schedule_task_fn=create_and_schedule_tool_task,
        direct_runner=None,
        event_publisher: AgentEventPublisher | None = None,
    ) -> None:
        self._db = db
        self._schedule_task_fn = schedule_task_fn
        self._direct_runner = direct_runner or default_direct_task_runner
        self._events = event_publisher or AgentEventPublisher(db)

    async def _commit_and_notify(self, run_id: str) -> None:
        await self._db.commit()
        await self._events.notify(run_id)

    async def _load_project_run_for_member(
        self,
        *,
        project_id: str,
        run_id: str,
        user_id: str,
    ) -> AgentRun:
        await load_project_membership(
            self._db,
            project_id=project_id,
            user_id=user_id,
        )
        run = await self._db.scalar(
            select(AgentRun)
            .options(selectinload(AgentRun.steps))
            .where(AgentRun.id == run_id, AgentRun.project_id == project_id)
        )
        if run is None:
            raise HTTPException(status_code=404, detail="智能体运行不存在")
        return run

    async def list_project_runs(
        self,
        *,
        project_id: str,
        user: User,
    ) -> list[AgentRun]:
        await load_project_membership(
            self._db,
            project_id=project_id,
            user_id=user.id,
        )
        runs = await self._db.scalars(
            select(AgentRun)
            .options(selectinload(AgentRun.steps))
            .where(AgentRun.project_id == project_id)
            .order_by(AgentRun.created_at.desc())
        )
        return list(runs.all())

    async def get_project_run(
        self,
        *,
        project_id: str,
        run_id: str,
        user: User,
    ) -> AgentRun:
        return await self._load_project_run_for_member(
            project_id=project_id,
            run_id=run_id,
            user_id=user.id,
        )

    async def cancel_project_run(
        self,
        *,
        project_id: str,
        run_id: str,
        user: User,
    ) -> AgentRun:
        await require_project_role(
            self._db,
            project_id=project_id,
            user=user,
            allowed_roles=PROJECT_AGENT_RUN_OPERATION_ROLES,
        )
        run = await self._db.scalar(
            select(AgentRun)
            .options(selectinload(AgentRun.steps))
            .where(AgentRun.id == run_id, AgentRun.project_id == project_id)
            .with_for_update()
        )
        if run is None:
            raise HTTPException(status_code=404, detail="智能体运行不存在")
        if run.status in TERMINAL_RUN_STATUSES:
            return run

        for step in run.steps:
            if not step.task_id:
                continue
            task = await self._db.get(Task, step.task_id)
            if task:
                await cancel_platform_task(
                    self._db,
                    task=task,
                    current_user=user,
                    direct_runner=self._direct_runner,
                )
        run.status = "canceled"
        run.finished_at = utcnow()
        for step in run.steps:
            if step.status in ACTIVE_STEP_STATUSES:
                step.status = "canceled"
                step.finished_at = utcnow()
        await self._events.append(
            run_id=run.id,
            event_type="run_canceled",
            payload={"run_id": run.id, "project_id": project_id},
        )
        await self._commit_and_notify(run.id)
        return await self._load_project_run_for_member(
            project_id=project_id,
            run_id=run.id,
            user_id=user.id,
        )

    async def _load_conversation(
        self,
        *,
        project_id: str,
        conversation_id: str,
        user_id: str,
    ) -> Conversation:
        await load_project_membership(self._db, project_id=project_id, user_id=user_id)
        conversation = await self._db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.project_id == project_id,
            )
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="项目会话不存在")
        return conversation

    async def _load_protein_version(
        self,
        *,
        project_id: str,
        version_id: str,
    ) -> ArtifactVersion:
        version = await self._db.scalar(
            select(ArtifactVersion)
            .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
            .where(
                ArtifactVersion.id == version_id,
                Artifact.project_id == project_id,
                Artifact.semantic_type.in_({"protein_pdb", "protein_structure"}),
                ArtifactVersion.status == "available",
            )
        )
        if version is None:
            raise HTTPException(
                status_code=404, detail="可用的蛋白 Artifact 版本不存在"
            )
        return version

    async def _next_plan_version(self, conversation_id: str) -> int:
        await self._db.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .with_for_update()
        )
        current = await self._db.scalar(
            select(func.max(PlanVersion.version)).where(
                PlanVersion.conversation_id == conversation_id
            )
        )
        return (current or 0) + 1

    @staticmethod
    def _approval_message_content(
        *,
        plan: PlanVersion,
        run: AgentRun,
    ) -> list[dict[str, Any]]:
        return [
            {
                "type": "text",
                "text": "已生成 LVpocket 口袋识别执行计划，请审批后启动任务。",
            },
            {
                "type": "approval_ref",
                "plan_id": plan.id,
                "run_id": run.id,
                "tool": "LVpocket",
                "parameters": dict((plan.content or {}).get("parameters") or {}),
                "resources": {"accelerator": "NVIDIA GPU", "gpu_count": 1},
                "estimated_duration_seconds": 180,
                "network_access": False,
                "status": "pending",
            },
        ]

    async def create_plan(
        self,
        *,
        project_id: str,
        conversation_id: str,
        user: User,
        goal: str,
        protein_artifact_version_id: str | None,
    ) -> ProjectPlanResult:
        conversation = await self._load_conversation(
            project_id=project_id,
            conversation_id=conversation_id,
            user_id=user.id,
        )
        run = AgentRun(
            project_id=project_id,
            user_id=user.id,
            message=goal,
            intent="pocket_detection",
            status="planning",
            input_type="protein_pdb",
            requested_outputs=["pocket_pdb", "pocket_report"],
            plan={},
        )
        self._db.add(run)
        await self._db.flush()

        if not protein_artifact_version_id:
            run.status = "input_required"
            await self._events.append(
                run_id=run.id,
                event_type="input_required",
                payload={
                    "semantic_type": "protein_pdb",
                    "message": "请先上传或选择蛋白结构 Artifact。",
                },
            )
            await self._commit_and_notify(run.id)
            return ProjectPlanResult(run=run, plan_version=None)

        protein = await self._load_protein_version(
            project_id=project_id,
            version_id=protein_artifact_version_id,
        )
        plan_data = build_project_lvpocket_plan_node(
            {
                "project_id": project_id,
                "conversation_id": conversation_id,
                "message": goal,
                "protein_artifact_version_id": protein.id,
            }
        )["plan"]
        plan = PlanVersion(
            project_id=project_id,
            conversation_id=conversation_id,
            agent_run_id=run.id,
            created_by=user.id,
            version=await self._next_plan_version(conversation_id),
            content=deepcopy(plan_data),
            risk_level="medium",
            status="pending",
        )
        self._db.add(plan)
        await self._db.flush()
        run.plan = deepcopy(plan_data)
        run.status = "awaiting_approval"
        await self._events.append(
            run_id=run.id,
            event_type="plan_created",
            payload={"plan_version_id": plan.id, "version": plan.version},
        )
        await self._events.append(
            run_id=run.id,
            event_type="approval_required",
            payload={"plan_version_id": plan.id, "risk_level": plan.risk_level},
        )
        await append_message(
            self._db,
            conversation=conversation,
            user=user,
            role="assistant",
            content=self._approval_message_content(plan=plan, run=run),
        )
        await self._commit_and_notify(run.id)
        return ProjectPlanResult(run=run, plan_version=plan)

    async def _load_executable_plan(
        self,
        *,
        plan_version_id: str,
        user: User,
    ) -> tuple[PlanVersion, AgentRun]:
        plan = await self._db.scalar(
            select(PlanVersion)
            .where(PlanVersion.id == plan_version_id)
            .with_for_update()
        )
        if plan is None or plan.agent_run_id is None:
            raise HTTPException(status_code=404, detail="项目计划版本不存在")
        await require_project_role(
            self._db,
            project_id=plan.project_id,
            user=user,
            allowed_roles={"owner", "runner"},
        )
        decision = await self._db.scalar(
            select(PlanDecision).where(
                PlanDecision.plan_version_id == plan.id,
                PlanDecision.decision == "approve",
            )
        )
        if plan.status != "approved" or decision is None:
            raise HTTPException(status_code=409, detail="计划尚未审批，禁止执行")
        run = await self._db.get(AgentRun, plan.agent_run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="智能体运行不存在")
        if run.status not in {"awaiting_approval", "approved"}:
            raise HTTPException(status_code=409, detail="计划已提交或不可执行")
        return plan, run

    async def _load_lvpocket_tool_version(
        self,
    ) -> tuple[Tool, ToolVersion, ToolPackageV2Manifest]:
        tool = await self._db.scalar(
            select(Tool)
            .options(selectinload(Tool.current_version))
            .where(
                Tool.slug == LVPOCKET_SLUG,
                Tool.status == ToolStatus.PUBLISHED.value,
                Tool.is_public.is_(True),
            )
        )
        if (
            tool is None
            or tool.current_version is None
            or tool.current_version.is_active is not True
            or tool.current_version.deprecated is True
        ):
            raise HTTPException(status_code=409, detail="LVpocket 标准任务版本不可用")

        manifest = tool_package_v2_manifest(
            tool.current_version.config if isinstance(tool.current_version.config, dict) else {},
            ignore_invalid=True,
        )
        if manifest is None or manifest.exposure.agent is not True:
            raise HTTPException(status_code=409, detail="LVpocket 标准任务版本不可用")
        return tool, tool.current_version, manifest

    @staticmethod
    def _required_input_name(
        manifest: ToolPackageV2Manifest,
        *,
        standard_ref: str,
    ) -> str:
        for item in manifest.artifacts.inputs:
            if item.type == standard_ref and item.required is True:
                return item.name
        raise HTTPException(
            status_code=409,
            detail=f"LVpocket 标准输入 {standard_ref} 不可用",
        )

    async def submit_approved_plan(
        self,
        *,
        plan_version_id: str,
        user: User,
    ) -> ProjectTaskSubmission:
        plan, run = await self._load_executable_plan(
            plan_version_id=plan_version_id,
            user=user,
        )
        tool, tool_version, manifest = await self._load_lvpocket_tool_version()
        protein_version_id = str(plan.content.get("protein_artifact_version_id") or "")
        protein = await self._load_protein_version(
            project_id=plan.project_id,
            version_id=protein_version_id,
        )
        input_name = self._required_input_name(
            manifest,
            standard_ref="protein_structure@1",
        )
        task = await self._schedule_task_fn(
            db=self._db,
            current_user=user,
            task_data=TaskCreate(
                name=f"AIDD LVpocket - Plan {plan.version}",
                project_id=plan.project_id,
                tool_id=tool.id,
                tool_version_id=tool_version.id,
                params=dict(plan.content.get("parameters") or {}),
                input_bindings={input_name: protein.id},
            ),
            direct_runner=self._direct_runner,
            extra_data={
                "agent_run_id": run.id,
                "plan_version_id": plan.id,
                "conversation_id": plan.conversation_id,
            },
        )
        await self._events.append(
            run_id=run.id,
            event_type="execution_submitted",
            payload={
                "plan_version_id": plan.id,
                "tool_slug": LVPOCKET_SLUG,
                "task_id": task.id,
            },
        )
        run.status = "queued"
        await self._events.append(
            run_id=run.id,
            event_type="execution_queued",
            payload={
                "execution_id": task.id,
                "task_id": task.id,
                "state": "queued",
            },
        )
        await self._commit_and_notify(run.id)
        return ProjectTaskSubmission(task=task, tool_slug=LVPOCKET_SLUG)

    async def complete_run(
        self,
        *,
        run_id: str,
        artifact_version_ids: list[str],
        summary: str,
    ) -> AgentRun:
        run = await self._db.scalar(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        )
        if run is None:
            raise HTTPException(status_code=404, detail="智能体运行不存在")
        if run.status in {"success", "failure", "canceled"}:
            raise HTTPException(status_code=409, detail="智能体运行已结束")
        run.status = "success"
        run.summary = summary
        run.finished_at = utcnow()
        await self._events.append(
            run_id=run.id,
            event_type="artifact_completed",
            payload={"artifact_version_ids": list(artifact_version_ids)},
        )
        await self._events.append(
            run_id=run.id,
            event_type="analysis_summary",
            payload={
                "summary": summary,
                "artifact_version_ids": list(artifact_version_ids),
            },
        )
        await self._commit_and_notify(run.id)
        return run

    async def branch_plan_for_goal(
        self,
        *,
        plan_version_id: str,
        user: User,
        goal: str,
    ) -> PlanVersion:
        source = await self._db.get(PlanVersion, plan_version_id)
        if source is None or source.conversation_id is None:
            raise HTTPException(status_code=404, detail="项目计划版本不存在")
        await load_project_membership(
            self._db, project_id=source.project_id, user_id=user.id
        )
        content = deepcopy(source.content or {})
        content["goal"] = goal
        content["parent_plan_version_id"] = source.id
        branched = PlanVersion(
            project_id=source.project_id,
            conversation_id=source.conversation_id,
            agent_run_id=source.agent_run_id,
            created_by=user.id,
            version=await self._next_plan_version(source.conversation_id),
            content=content,
            risk_level=source.risk_level,
            status="pending",
        )
        self._db.add(branched)
        await self._db.commit()
        return branched
