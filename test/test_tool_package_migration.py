"""Legacy tool versions migrate into safe, immutable Tool Package versions."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models.tool_packages import ToolPackage, ToolPackageVersion
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def migration_db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _legacy_tool(
    db: AsyncSession,
    *,
    slug: str = "legacy-pocket",
    config: dict | None = None,
) -> ToolVersion:
    user = User(
        email=f"{slug}@example.com",
        password_hash="hashed",
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
    )
    tool = Tool(
        owner=user,
        name="Legacy Pocket",
        slug=slug,
        status=ToolStatus.PUBLISHED.value,
        gpu_required=True,
    )
    version = ToolVersion(
        tool=tool,
        version="1.2.3",
        config=config
        or {
            "type": "docker_image",
            "image": "registry.local/legacy-pocket:1.2.3",
            "command": ["/app/run"],
            "host": "gpu-node.internal",
            "headers": {"Authorization": "Bearer secret-token"},
            "agent_capability": {
                "enabled": True,
                "capability": "pocket_detection",
                "stage": "analysis",
                "inputs": [{"field": "protein", "semantic_type": "protein_structure"}],
                "outputs": [
                    {
                        "semantic_type": "pocket_result",
                        "source": "output_data",
                        "path": "pockets",
                        "match": {"artifact_type": "pocket_result"},
                    }
                ],
            },
        },
    )
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    await db.commit()
    return version


@pytest.mark.asyncio
async def test_dry_run_is_idempotent_and_does_not_write_database(
    migration_db: AsyncSession,
):
    await _legacy_tool(migration_db)

    from app.tool_packages.migration import migrate_tool_packages

    first = await migrate_tool_packages(migration_db, dry_run=True)
    second = await migrate_tool_packages(migration_db, dry_run=True)

    assert first.packages_created == 1
    assert first.versions_created == 1
    assert second.to_dict() == first.to_dict()
    assert (await migration_db.execute(select(ToolPackage))).scalars().all() == []


@pytest.mark.asyncio
async def test_apply_writes_one_immutable_package_version_without_sensitive_legacy_config(
    migration_db: AsyncSession,
):
    await _legacy_tool(migration_db)

    from app.tool_packages.migration import migrate_tool_packages

    first = await migrate_tool_packages(migration_db, dry_run=False)
    await migration_db.commit()
    second = await migrate_tool_packages(migration_db, dry_run=False)

    packages = (await migration_db.execute(select(ToolPackage))).scalars().all()
    versions = (await migration_db.execute(select(ToolPackageVersion))).scalars().all()
    manifest = versions[0].manifest

    assert first.packages_created == 1
    assert first.versions_created == 1
    assert second.packages_created == 0
    assert second.versions_created == 0
    assert len(packages) == 1
    assert len(versions) == 1
    assert packages[0].current_version_id == versions[0].id
    assert manifest["metadata"]["slug"] == "legacy-pocket"
    assert "gpu-node.internal" not in str(manifest)
    assert "secret-token" not in str(manifest)
    assert manifest["variants"][0]["accelerator"] == "cpu"
    assert manifest["variants"][0]["validation_status"] == "unvalidated"
    assert manifest["variants"][1]["accelerator"] == "nvidia_cuda"
    assert manifest["variants"][1]["validation_status"] == "unvalidated"
    assert (
        manifest["variants"][2]["validation_status"]
        == "adapted_pending_hardware_validation"
    )


@pytest.mark.asyncio
async def test_migration_only_marks_nvidia_verified_with_golden_evidence(
    migration_db: AsyncSession,
):
    version = await _legacy_tool(migration_db)
    version.config["golden_validation"] = {"nvidia_cuda": {"passed": True}}
    await migration_db.commit()

    from app.tool_packages.migration import migrate_tool_packages

    await migrate_tool_packages(migration_db, dry_run=False)
    await migration_db.commit()
    package_version = (
        await migration_db.execute(select(ToolPackageVersion))
    ).scalar_one()
    variants = {
        item["accelerator"]: item for item in package_version.manifest["variants"]
    }

    assert variants["nvidia_cuda"]["validation_status"] == "validated"
    assert variants["nvidia_cuda"]["hardware_validated"] is True
    assert (
        variants["haiguang_dcu"]["validation_status"]
        == "adapted_pending_hardware_validation"
    )


@pytest.mark.asyncio
async def test_missing_contract_fields_are_reported_with_specific_reasons(
    migration_db: AsyncSession,
):
    await _legacy_tool(
        migration_db,
        slug="incomplete-tool",
        config={"type": "ssh_job", "agent_capability": {"enabled": True, "inputs": []}},
    )

    from app.tool_packages.migration import migrate_tool_packages

    summary = await migrate_tool_packages(migration_db, dry_run=True)

    assert summary.invalid == 1
    assert any(
        "agent_capability.capability" in error for error in summary.records[0].errors
    )
    assert any(
        "agent_capability.outputs" in error for error in summary.records[0].errors
    )


@pytest.mark.asyncio
async def test_tool_response_embeds_migrated_package_manifest_for_validation_ui(
    migration_db: AsyncSession,
):
    await _legacy_tool(migration_db)

    from app.api.v1.tool_route_utils import load_tool_packages_for_tools, serialize_tool
    from app.tool_packages.migration import migrate_tool_packages

    await migrate_tool_packages(migration_db, dry_run=False)
    await migration_db.commit()
    tool = (
        (
            await migration_db.execute(
                select(Tool)
                .options(
                    selectinload(Tool.current_version),
                    selectinload(Tool.tags),
                    selectinload(Tool.tool_category),
                    joinedload(Tool.statistics),
                )
                .where(Tool.slug == "legacy-pocket")
            )
        )
        .scalars()
        .one()
    )
    package_by_slug = await load_tool_packages_for_tools(migration_db, [tool])

    payload = serialize_tool(tool, tool_package=package_by_slug[tool.slug])
    package_config = payload["current_version"]["config"]["tool_package"]

    assert package_config["slug"] == "legacy-pocket"
    assert package_config["validation_status"] == "valid"
    assert package_config["manifest"]["variants"][1]["accelerator"] == "nvidia_cuda"
    assert package_config["manifest"]["variants"][2]["validation_status"] == (
        "adapted_pending_hardware_validation"
    )
    assert "secret-token" not in str(package_config)
