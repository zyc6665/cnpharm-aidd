"""Project-scoped AIDD Agent planning, approval, and execution lifecycle."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.aidd.event_publisher import AgentEventPublisher
from app.agents.aidd.graph_nodes import build_project_lvpocket_plan_node
from app.common.time import utcnow
from app.execution.contracts import ExecutionHandle, ExecutionInput, ExecutionRequest
from app.execution.port import ExecutionPort
from app.models.agent import AgentRun
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.conversations import Conversation, PlanDecision, PlanVersion
from app.models.tool_packages import ToolPackage, ToolPackageVersion
from app.models.users import User
from app.services.project_access import load_project_membership, require_project_role


LVPOCKET_SLUG = "lvpocket-pocket-prediction"


@dataclass(frozen=True)
class ProjectPlanResult:
    run: AgentRun
    plan_version: PlanVersion | None


class ProjectAgentService:
    """Own state transitions that prompts and graph nodes must not perform."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        execution_port: ExecutionPort,
        event_publisher: AgentEventPublisher | None = None,
    ) -> None:
        self._db = db
        self._execution_port = execution_port
        self._events = event_publisher or AgentEventPublisher(db)

    async def _commit_and_notify(self, run_id: str) -> None:
        await self._db.commit()
        await self._events.notify(run_id)

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

    async def create_plan(
        self,
        *,
        project_id: str,
        conversation_id: str,
        user: User,
        goal: str,
        protein_artifact_version_id: str | None,
    ) -> ProjectPlanResult:
        await self._load_conversation(
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

    async def _load_lvpocket_package_version(
        self,
    ) -> tuple[ToolPackageVersion, dict[str, Any]]:
        row = (
            await self._db.execute(
                select(ToolPackageVersion, ToolPackage)
                .join(ToolPackage, ToolPackage.id == ToolPackageVersion.package_id)
                .where(
                    ToolPackage.slug == LVPOCKET_SLUG,
                    ToolPackage.current_version_id == ToolPackageVersion.id,
                    ToolPackage.status == "published",
                    ToolPackageVersion.is_signed.is_(True),
                    ToolPackageVersion.validation_status == "valid",
                )
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=409, detail="LVpocket 生产工具包不可用")
        version, _package = row
        variants = (version.manifest or {}).get("variants") or []
        variant = next(
            (
                item
                for item in variants
                if item.get("name") in {"nvidia-cuda", "nvidia_cuda"}
            ),
            None,
        )
        if variant is None:
            raise HTTPException(
                status_code=409, detail="LVpocket NVIDIA 运行变体不可用"
            )
        return version, variant

    async def submit_approved_plan(
        self,
        *,
        plan_version_id: str,
        user: User,
    ) -> ExecutionHandle:
        plan, run = await self._load_executable_plan(
            plan_version_id=plan_version_id,
            user=user,
        )
        package_version, variant = await self._load_lvpocket_package_version()
        protein_version_id = str(plan.content.get("protein_artifact_version_id") or "")
        protein = await self._load_protein_version(
            project_id=plan.project_id,
            version_id=protein_version_id,
        )
        request = ExecutionRequest(
            idempotency_key=f"project-plan:{plan.id}",
            project_id=plan.project_id,
            requested_by=user.id,
            tool_package_version_id=package_version.id,
            variant=str(variant["name"]),
            executor_type=str((variant.get("executor_types") or ["remote_job"])[0]),
            parameters=dict(plan.content.get("parameters") or {}),
            inputs=[
                ExecutionInput(
                    artifact_version_id=protein.id,
                    name="protein_pdb",
                    uri=protein.storage_key,
                    sha256=protein.sha256,
                )
            ],
            resources=dict(variant.get("resources") or {}),
        )
        handle = await self._execution_port.submit(request)
        await self._events.append(
            run_id=run.id,
            event_type="execution_submitted",
            payload={"plan_version_id": plan.id, "tool_slug": LVPOCKET_SLUG},
        )
        run.status = "queued"
        await self._events.append(
            run_id=run.id,
            event_type="execution_queued",
            payload={
                "execution_id": handle.execution_id,
                "state": handle.state.value,
            },
        )
        await self._commit_and_notify(run.id)
        return handle

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
