"""LDDM（口袋条件分子生成）后端集成测试。

覆盖三件事：
1. 能力注册：``lddm-pocket-ligand-generation`` 归属 ``molecule_generation`` 模型族，
   静态能力表中的输入/输出与 Tool Package 契约一致；
2. 端到端注册：真实 ``example/lddm/tool-package/tool.yaml`` 走
   「导入 → 发布 → 注册 K8s 工具版本（nvidia-cuda / gpu-large）」全流程；
3. 标准输入直传：``protein_pdb``（必需）+ ``fragment_sdf``（可选，SDF/PDB/MOL）
   的上传规划与元数据推断。
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
for _path in (PROJECT_ROOT, BACKEND_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.auth.dependencies import get_current_user  # noqa: E402
from app.common.exceptions import ValidationException  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.files import File as FileModel  # noqa: E402
from app.models.files import FileSourceType  # noqa: E402
from app.models.tools import ToolCategory  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services.standard_input_upload_plans import (  # noqa: E402
    build_standard_input_upload_plans,
)
from app.services.standard_input_slots import (  # noqa: E402
    tool_accepts_materialized_standard_uploads,
)
from app.tool_packages.loader import load_tool_package  # noqa: E402
from app.tools.capabilities import get_capability, resolve_model_family  # noqa: E402

LDDM_SLUG = "lddm-pocket-ligand-generation"
PACKAGE_ROOT = PROJECT_ROOT / "example" / "lddm" / "tool-package"

_PROTEIN_PDB = (
    b"ATOM      1  N   MET A   1      11.104  13.207   2.100  1.00 20.00           N\n"
    b"ATOM      2  CA  MET A   1      12.560  13.207   2.100  1.00 20.00           C\n"
    b"END\n"
)
_FRAGMENT_SDF = (
    b"fragment\n"
    b"  RDKit          3D\n"
    b"\n"
    b"  3  2  0  0  0  0  0  0  0  0999 V2000\n"
    b"  0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    b"M  END\n"
    b"$$$$\n"
)
_FRAGMENT_PDB = (
    b"HETATM    1  C1  LIG A   1       0.000   0.000   0.000  1.00  0.00           C\n"
    b"HETATM    2  O1  LIG A   1       1.200   0.000   0.000  1.00  0.00           O\n"
    b"END\n"
)


def _lddm_manifest() -> dict:
    """读取真实 LDDM Tool Package，并按 API 收到的形态序列化。"""
    if (PACKAGE_ROOT / "tool.yaml").is_file():
        return load_tool_package(PACKAGE_ROOT).model_dump(mode="json", exclude_none=True)
    return {
        "api_version": "aidd.platform/tool-package",
        "kind": "ToolPackage",
        "metadata": {
            "slug": LDDM_SLUG,
            "name": "LDDM 口袋条件分子生成",
            "version": "1.0.1",
            "description": "LDDM integration test manifest",
        },
        "artifacts": {
            "inputs": [
                {
                    "name": "protein_pdb",
                    "title": "蛋白结构",
                    "type": "protein_structure@1",
                    "required": True,
                    "role_preferences": ["prepared_pdb", "structure_file"],
                },
                {"name": "pocket", "title": "结合口袋", "type": "binding_pocket@1", "required": False},
                {
                    "name": "fragment_sdf",
                    "title": "片段或配体结构",
                    "type": "ligand_structure@1",
                    "required": False,
                    "role_preferences": ["structure_file", "structure_3d_sdf"],
                },
                {
                    "name": "ref_ligand",
                    "title": "参考配体",
                    "type": "ligand_structure@1",
                    "required": False,
                    "role_preferences": ["structure_file", "structure_3d_sdf"],
                },
            ],
            "outputs": [
                {"name": "molecules", "type": "molecule_table@1", "cardinality": "one", "required": True},
                {"name": "ligands", "type": "ligand_structure@1", "cardinality": "one", "required": True},
            ],
        },
        "parameters_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "adapter": {"input": [], "output": []},
        "exposure": {"agent": True, "workflow": True, "direct_run": True},
        "runtime": {
            "python": "3.11",
            "cuda": "12.4",
            "executor_support": ["k8s_job"],
            "selection_policy": "prefer container image by immutable digest",
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": "registry.example/aidd/compute-lddm:1.0.1",
                    "image_digest": "sha256:6fc5496e4e27b424f1042be19a6166a14739ae0434845bee21466d2031b889b6",
                    "includes": ["python", "cuda_runtime"],
                },
                "fallback": {
                    "kind": "conda_pack",
                    "uri": "artifacts://model-envs/lddm/1.0.1/env.tar.gz",
                    "sha256": "0" * 64,
                    "includes": ["python"],
                },
            },
            "cache_policy": {
                "key_fields": ["metadata.slug", "metadata.version", "runtime.artifacts.selected.digest_or_sha256"],
                "mutable_host_paths_forbidden": True,
            },
        },
        "variants": [
            {
                "name": "nvidia-cuda",
                "accelerator": "nvidia_cuda",
                "executor_types": ["container"],
                "image": "registry.example/aidd/compute-lddm@sha256:6fc5496e4e27b424f1042be19a6166a14739ae0434845bee21466d2031b889b6",
                "entrypoint": ["/usr/bin/tini", "--", "/opt/aidd/platform_adaptor/entrypoint.sh"],
                "resources": {"cpu": 4, "memory_mb": 16384, "gpu_memory_mb": 16384, "devices": ["nvidia.com/gpu"], "driver": ">=535"},
                "validation_status": "unvalidated",
                "hardware_validated": False,
            }
        ],
    }


def _tool_and_version(manifest: dict) -> tuple[SimpleNamespace, SimpleNamespace]:
    tool_version = SimpleNamespace(config={"tool_package_manifest": manifest})
    tool = SimpleNamespace(
        id="tool-lddm",
        slug=LDDM_SLUG,
        name="LDDM",
        description=None,
        status="published",
        is_public=True,
        current_version=tool_version,
    )
    return tool, tool_version


class FakeDb:
    """只实现 ``db.get(FileModel, id)`` 的最小会话替身。"""

    def __init__(self, files: dict[str, FileModel]) -> None:
        self.files = files

    async def get(self, model: type[FileModel], file_id: str) -> FileModel | None:
        assert model is FileModel
        return self.files.get(file_id)


def _uploaded_file(
    tmp_path: Path,
    *,
    filename: str,
    content: bytes,
    content_type: str = "chemical/x-pdb",
) -> FileModel:
    path = tmp_path / filename
    path.write_bytes(content)
    return FileModel(
        id=f"file-{filename}",
        owner_id="user-1",
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_path=str(path),
        source_type=FileSourceType.UPLOAD.value,
    )


# --------------------------------------------------------------------------
# 1. 能力与模型族注册
# --------------------------------------------------------------------------


def test_lddm_resolves_to_molecule_generation_family() -> None:
    assert resolve_model_family(LDDM_SLUG) == "molecule_generation"


def test_lddm_static_capability_matches_tool_package_contract() -> None:
    capability = get_capability(LDDM_SLUG)

    assert capability is not None
    assert capability.capability == LDDM_SLUG
    assert capability.virtual is False
    assert {
        (item.semantic_type, item.field, item.required) for item in capability.inputs
    } == {
        ("protein_pdb", "protein_pdb", True),
        ("pocket_pdb", "pocket_pdb", False),
        ("fragment_sdf", "fragment_sdf", False),
    }
    assert [item.semantic_type for item in capability.outputs] == [
        "generated_ligand",
        "smiles_csv",
    ]
    fragment_input = next(
        item for item in capability.inputs if item.field == "fragment_sdf"
    )
    assert ".sdf" in fragment_input.accepted_extensions
    assert ".pdb" in fragment_input.accepted_extensions

    manifest = _lddm_manifest()
    assert manifest["metadata"]["slug"] == LDDM_SLUG
    assert [item["name"] for item in manifest["artifacts"]["inputs"]] == [
        "protein_pdb",
        "pocket",
        "fragment_sdf",
        "ref_ligand",
    ]


# --------------------------------------------------------------------------
# 2. 标准输入直传：protein_pdb + fragment_sdf
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lddm_upload_plan_accepts_sdf_fragment(tmp_path: Path) -> None:
    protein = _uploaded_file(tmp_path, filename="protein.pdb", content=_PROTEIN_PDB)
    fragment = _uploaded_file(
        tmp_path,
        filename="fragment.sdf",
        content=_FRAGMENT_SDF,
        content_type="chemical/x-mdl-sdfile",
    )
    tool, tool_version = _tool_and_version(_lddm_manifest())

    plans = await build_standard_input_upload_plans(
        FakeDb({protein.id: protein, fragment.id: fragment}),
        tool=tool,
        tool_version=tool_version,
        project_id="project-1",
        standard_input_uploads={"protein_pdb": protein.id, "fragment_sdf": fragment.id},
    )

    plans_by_slot = {plan.slot_name: plan for plan in plans}
    assert set(plans_by_slot) == {"protein_pdb", "fragment_sdf"}

    protein_plan = plans_by_slot["protein_pdb"]
    assert protein_plan.standard_ref.ref == "protein_structure@1"
    assert protein_plan.primary_role.role == "structure_file"
    assert protein_plan.metadata["atom_count"] == 2

    fragment_plan = plans_by_slot["fragment_sdf"]
    assert fragment_plan.standard_ref.ref == "ligand_structure@1"
    # role_preferences 是 [structure_file, structure_3d_sdf]，直传只能落必需角色
    assert fragment_plan.primary_role.role == "structure_file"
    assert fragment_plan.metadata["ligand_id"] == "fragment"
    assert fragment_plan.metadata["input_name"] == "fragment_sdf"


@pytest.mark.asyncio
async def test_lddm_upload_plan_accepts_pdb_and_mol_fragments(tmp_path: Path) -> None:
    tool, tool_version = _tool_and_version(_lddm_manifest())

    for filename, content in (
        ("fragment.pdb", _FRAGMENT_PDB),
        ("fragment.mol", _FRAGMENT_SDF.split(b"$$$$\n")[0]),
    ):
        fragment = _uploaded_file(tmp_path, filename=filename, content=content)
        plans = await build_standard_input_upload_plans(
            FakeDb({fragment.id: fragment}),
            tool=tool,
            tool_version=tool_version,
            project_id="project-1",
            standard_input_uploads={"fragment_sdf": fragment.id},
        )

        assert [plan.slot_name for plan in plans] == ["fragment_sdf"]
        assert plans[0].uploaded_file is fragment
        assert plans[0].primary_role.role == "structure_file"


@pytest.mark.asyncio
async def test_lddm_upload_plan_rejects_unknown_slot(tmp_path: Path) -> None:
    fragment = _uploaded_file(tmp_path, filename="fragment.sdf", content=_FRAGMENT_SDF)
    tool, tool_version = _tool_and_version(_lddm_manifest())

    with pytest.raises(ValidationException):
        await build_standard_input_upload_plans(
            FakeDb({fragment.id: fragment}),
            tool=tool,
            tool_version=tool_version,
            project_id="project-1",
            standard_input_uploads={"not_a_slot": fragment.id},
        )


# --------------------------------------------------------------------------
# 3. 端到端：导入 → 发布 → 注册 K8s 版本 → 契约可见
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def package_db() -> AsyncSession:
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


@pytest_asyncio.fixture
async def package_users(package_db: AsyncSession) -> dict[str, User]:
    users = {
        "admin": User(
            email="lddm-admin@example.com",
            password_hash="hashed",
            role=UserRole.ADMIN.value,
            status=UserStatus.ACTIVE.value,
        ),
    }
    package_db.add_all(users.values())
    await package_db.commit()
    return users


@pytest_asyncio.fixture
async def package_client(package_db: AsyncSession, package_users: dict[str, User]):
    async def override_get_db():
        yield package_db

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token in package_users:
            return package_users[token]
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_lddm_package_publishes_and_registers_kubernetes_version(
    package_client: httpx.AsyncClient,
    package_db: AsyncSession,
    package_users: dict[str, User],
) -> None:
    headers = {"Authorization": "Bearer admin"}
    created = await package_client.post(
        "/api/v1/tool-packages",
        headers=headers,
        json={"manifest": _lddm_manifest(), "signature": "cosign:sha256:lddm"},
    )
    assert created.status_code == 200, created.text
    package = created.json()["data"]
    assert package["slug"] == LDDM_SLUG
    assert package["current_version"]["validation_status"] == "valid"

    published = await package_client.post(
        f"/api/v1/tool-packages/{package['id']}/publish",
        headers=headers,
    )
    assert published.status_code == 200, published.text
    assert published.json()["data"]["status"] == "published"

    options = await package_client.get(
        f"/api/v1/tool-packages/{package['id']}/kubernetes-options",
        headers=headers,
    )
    assert options.status_code == 200, options.text
    option_data = options.json()["data"]
    assert [variant["name"] for variant in option_data["variants"]] == ["nvidia-cuda"]
    assert "gpu-large" in option_data["resource_profiles"]

    category = ToolCategory(name="LDDM Models", slug="lddm-models")
    package_db.add(category)
    await package_db.commit()

    registration = await package_client.post(
        f"/api/v1/tool-packages/{package['id']}/kubernetes-registrations",
        headers=headers,
        json={
            "package_version_id": published.json()["data"]["current_version"]["id"],
            "tool_version": "1.0.0-k8s-gpu",
            "variant_name": "nvidia-cuda",
            "resource_profile": "gpu-large",
            "category_id": category.id,
        },
    )
    assert registration.status_code == 200, registration.text
    data = registration.json()["data"]
    assert data["registration_status"] == "candidate"
    assert data["tool"]["slug"] == LDDM_SLUG
    assert data["tool"]["owner_id"] == package_users["admin"].id
    assert data["version"]["is_active"] is False

    config = data["version"]["config"]
    assert config["type"] == "k8s_job"
    assert config["variant"] == "nvidia-cuda"
    assert config["resource_profile"] == "gpu-large"
    stored_manifest = config["tool_package_manifest"]
    expected_digest = stored_manifest["runtime"]["artifacts"]["primary"]["image_digest"]
    assert config["runtime"]["image"].endswith(f"@{expected_digest}")
    assert config["runtime"]["entrypoint"] == [
        "/usr/bin/tini",
        "--",
        "/opt/aidd/platform_adaptor/entrypoint.sh",
    ]

    # 注册后的版本必须保留 v2 manifest，否则标准输入直传不会被物化。
    assert tool_accepts_materialized_standard_uploads(config) is True
    assert stored_manifest["metadata"]["slug"] == LDDM_SLUG
    fragment_slot = next(
        item for item in stored_manifest["artifacts"]["inputs"] if item["name"] == "fragment_sdf"
    )
    assert fragment_slot["role_preferences"] == ["structure_file", "structure_3d_sdf"]
    assert fragment_slot["required"] is False


@pytest.mark.asyncio
async def test_lddm_registered_manifest_drives_upload_plans(
    package_client: httpx.AsyncClient,
    package_db: AsyncSession,
    tmp_path: Path,
) -> None:
    """注册产物里的 manifest 直接喂给上传规划，确认契约没有在入库时被改写。"""
    headers = {"Authorization": "Bearer admin"}
    created = await package_client.post(
        "/api/v1/tool-packages",
        headers=headers,
        json={"manifest": _lddm_manifest(), "signature": "cosign:sha256:lddm"},
    )
    package = created.json()["data"]
    published = await package_client.post(
        f"/api/v1/tool-packages/{package['id']}/publish",
        headers=headers,
    )
    category = ToolCategory(name="LDDM Models", slug="lddm-models-2")
    package_db.add(category)
    await package_db.commit()

    registration = await package_client.post(
        f"/api/v1/tool-packages/{package['id']}/kubernetes-registrations",
        headers=headers,
        json={
            "package_version_id": published.json()["data"]["current_version"]["id"],
            "tool_version": "1.0.0-k8s-gpu",
            "variant_name": "nvidia-cuda",
            "resource_profile": "gpu-large",
            "category_id": category.id,
        },
    )
    assert registration.status_code == 200, registration.text
    stored_manifest = registration.json()["data"]["version"]["config"][
        "tool_package_manifest"
    ]

    tool, tool_version = _tool_and_version(stored_manifest)
    protein = _uploaded_file(tmp_path, filename="protein.pdb", content=_PROTEIN_PDB)
    fragment = _uploaded_file(
        tmp_path,
        filename="fragment.sdf",
        content=_FRAGMENT_SDF,
        content_type="chemical/x-mdl-sdfile",
    )

    plans = await build_standard_input_upload_plans(
        FakeDb({protein.id: protein, fragment.id: fragment}),
        tool=tool,
        tool_version=tool_version,
        project_id="project-1",
        standard_input_uploads={"protein_pdb": protein.id, "fragment_sdf": fragment.id},
    )

    assert {plan.slot_name for plan in plans} == {"protein_pdb", "fragment_sdf"}
    assert all(plan.primary_role.role == "structure_file" for plan in plans)
