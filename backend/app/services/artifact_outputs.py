"""解析「某个任务产出了哪些产物」的**唯一定义处**。

为什么不能按 ``Artifact.source_task_id`` 过滤
--------------------------------------------
``Artifact`` 是**跨任务共享的逻辑实体**：同一项目内同一 ``artifact_type`` +
同一标识（见 ``backend/app/services/artifact_writer.py`` 的身份判定）只保留一条
记录，后来的任务在它下面追加版本。因此 ``Artifact.source_task_id`` 记录的是
**首个创建者**，任务 B 追加 ``version=2`` 之后它仍然指向任务 A。

按 ``Artifact.source_task_id`` 过滤会让非首建任务的结果页、追溯包与导出报告
「一条产物都没有」——产物明明入库了、版本级来源也写对了，只是查询问错了列。
真正的产出关系记在 ``ArtifactVersion.source_task_id`` 上（Task 3a 落地），所以
这里以版本为粒度 join 回 ``Artifact`` 取展示所需的元数据。

三个调用方（结果详情、导出报告、追溯包）共用本函数，避免同一条语义在三处
各自实现、各自漂移。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifacts import Artifact, ArtifactVersion

__all__ = ["ArtifactOutput", "artifact_outputs_for_task"]


@dataclass(frozen=True)
class ArtifactOutput:
    """一条「本任务产出的产物版本」及其所属逻辑产物的展示元数据。"""

    artifact_id: str
    version_id: str
    artifact_type: str
    semantic_type: str | None
    standard_type: str | None
    standard_version: int | None
    name: str | None
    version: int | None
    filename: str | None
    size_bytes: int | None
    sha256: str | None
    # 版本上的两段结构化摘要。导出报告要拿它们拼「结论」段，但结果页用不到；
    # 放在这里是为了避免调用方再按 version_id 逐条回查（N+1）。
    metrics_json: dict[str, Any] | None = None
    summary_json: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "semantic_type": self.semantic_type,
            "standard_type": self.standard_type,
            "standard_version": self.standard_version,
            "name": self.name,
            "version_id": self.version_id,
            "version": self.version,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


def _to_output(artifact: Artifact, version: ArtifactVersion) -> ArtifactOutput:
    return ArtifactOutput(
        artifact_id=str(artifact.id),
        version_id=str(version.id),
        artifact_type=artifact.artifact_type,
        semantic_type=artifact.semantic_type,
        standard_type=artifact.standard_type,
        standard_version=artifact.standard_version,
        name=artifact.name,
        version=version.version,
        filename=version.filename,
        size_bytes=version.size_bytes,
        sha256=version.sha256,
        metrics_json=version.metrics_json if isinstance(version.metrics_json, dict) else None,
        summary_json=version.summary_json if isinstance(version.summary_json, dict) else None,
    )


async def artifact_outputs_for_task(
    db: AsyncSession,
    *,
    task_id: str,
) -> list[ArtifactOutput]:
    """返回该任务产出的全部产物版本，按产出时间与版本号升序。

    一个任务可能对同一条 ``Artifact`` 产出多个版本（例如重复回调），这里全部
    返回——调用方若只需要「最新一条」应自行按 ``version`` 取最大值，而不是让
    本函数替它决定，否则导出报告与结果页会出现两套口径。
    """

    rows = (
        await db.execute(
            select(Artifact, ArtifactVersion)
            .join(ArtifactVersion, ArtifactVersion.artifact_id == Artifact.id)
            .where(ArtifactVersion.source_task_id == str(task_id))
            .order_by(ArtifactVersion.created_at, ArtifactVersion.version)
        )
    ).all()
    if rows:
        return [_to_output(artifact, version) for artifact, version in rows]

    # 回退：Task 3a 之前的历史行没有 ``ArtifactVersion.source_task_id``（该列是
    # 后来新增的），只有实体级的 ``Artifact.source_task_id``。此时按实体级取
    # ``latest_version_id``——这是旧的（不精确的）口径，但比「历史任务一条产物都
    # 看不到」好；新数据永远走上面的版本级分支，不受影响。
    legacy = (
        await db.execute(
            select(Artifact, ArtifactVersion)
            .join(ArtifactVersion, ArtifactVersion.id == Artifact.latest_version_id)
            .where(Artifact.source_task_id == str(task_id))
            .order_by(Artifact.created_at)
        )
    ).all()
    return [_to_output(artifact, version) for artifact, version in legacy]
