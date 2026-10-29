"""Artifact lineage integrity tests."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models.projects import Organization, Project, ProjectMember
from app.models.users import User, UserRole, UserStatus
@pytest.mark.asyncio
async def test_lineage_accepts_same_project_and_rejects_cross_project_reference(
    monkeypatch, tmp_path
):
    from app.files import storage_path

    monkeypatch.setattr(storage_path, "STORAGE_PATH", tmp_path)
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as db:
        from app.services.artifacts import create_artifact, link_artifact_lineage

        user = User(
            email="lineage@example.com",
            password_hash="hashed",
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        organization = Organization(name="Lineage Lab", slug="lineage-lab")
        db.add_all([user, organization])
        await db.flush()
        projects = [
            Project(
                organization_id=organization.id,
                created_by=user.id,
                name=f"Project {index}",
                status="active",
            )
            for index in (1, 2)
        ]
        db.add_all(projects)
        await db.flush()
        db.add_all(
            [ProjectMember(project_id=project.id, user_id=user.id, role="owner") for project in projects]
        )
        await db.commit()

        source = await create_artifact(
            db,
            project=projects[0],
            user=user,
            filename="protein.pdb",
            content=b"protein",
            content_type="chemical/x-pdb",
            artifact_type="protein_structure",
            semantic_type="protein_structure",
        )
        output = await create_artifact(
            db,
            project=projects[0],
            user=user,
            filename="pockets.json",
            content=b"{}",
            content_type="application/json",
            # 资产类型收敛为受控枚举：此夹具历史上用 pocket_result（旧渲染别名），
            # 现已归一为 binding_pocket，保留注释以免后来者误判语义。
            artifact_type="binding_pocket",
            semantic_type="binding_pocket",
        )
        foreign = await create_artifact(
            db,
            project=projects[1],
            user=user,
            filename="foreign.json",
            content=b'{"foreign":true}',
            content_type="application/json",
            # 资产类型收敛为受控枚举：此夹具历史上用 pocket_result（旧渲染别名），
            # 现已归一为 binding_pocket，保留注释以免后来者误判语义。
            artifact_type="binding_pocket",
            semantic_type="binding_pocket",
        )

        edge = await link_artifact_lineage(
            db,
            project_id=projects[0].id,
            input_version_id=source.latest_version.id,
            output_version_id=output.latest_version.id,
            user_id=user.id,
        )
        assert edge.project_id == projects[0].id

        with pytest.raises(HTTPException) as exc_info:
            await link_artifact_lineage(
                db,
                project_id=projects[0].id,
                input_version_id=source.latest_version.id,
                output_version_id=foreign.latest_version.id,
                user_id=user.id,
            )
        assert exc_info.value.status_code == 403

    await engine.dispose()
