"""Expose drug discovery workflow tools with standard artifact contracts.

Revision ID: 20260821_01
Revises: 20260820_01
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
import yaml
from alembic import op

from app.services.aidd_builtin_tools import _capability_config


revision = "20260821_01"
down_revision = "20260820_01"
branch_labels = None
depends_on = None


GROUPS = (
    {
        "name": "格式转换",
        "slug": "format-conversion",
        "description": "在标准药物研发工作流中转换配体和分子表格式",
        "sort_order": 3,
    },
    {
        "name": "亲和力预测",
        "slug": "affinity-prediction",
        "description": "预测蛋白-配体结合亲和力并生成标准分子表结果",
        "sort_order": 4,
    },
    {
        "name": "ADMET/性质预测",
        "slug": "admet-property",
        "description": "预测分子 ADMET、毒性与理化性质结果",
        "sort_order": 5,
    },
)

MAPPINGS = (
    {
        "tool_slug": "builtin-sdf-to-smiles-csv",
        "group_slug": "format-conversion",
        "sort_order": 1,
    },
    {
        "tool_slug": "builtin-sdf-to-pdb",
        "group_slug": "format-conversion",
        "sort_order": 2,
    },
    {
        "tool_slug": "pocket2mol-pocket-ligand-generation",
        "group_slug": "molecular-generation",
        "sort_order": 2,
    },
    {
        "tool_slug": "msign-affinity-prediction",
        "group_slug": "affinity-prediction",
        "sort_order": 1,
    },
    {
        "tool_slug": "molp-pc-property-prediction",
        "group_slug": "admet-property",
        "sort_order": 1,
    },
)

BUILTIN_TOOLS = (
    {
        "slug": "builtin-sdf-to-smiles-csv",
        "name": "SDF to SMILES CSV",
        "description": "Convert ligand_structure@1 SDF files into molecule_table@1 SMILES CSV artifacts.",
    },
    {
        "slug": "builtin-sdf-to-pdb",
        "name": "SDF to Ligand PDB",
        "description": "Convert ligand_structure@1 SDF files into ligand PDB artifacts for legacy affinity and docking runtimes.",
    },
)

LEGACY_ARTIFACT_CONTRACTS = {
    "lvpocket-pocket-prediction": {
        "inputs": [
            {
                "name": "protein",
                "type": "protein_structure@1",
                "required": True,
                "role_preferences": ["prepared_pdb", "structure_file"],
                "readiness_policy": "prefer_prepared_warn_raw",
                "suggested_preparation_tool": "builtin-protein-preparation",
            }
        ],
        "outputs": [
            {"name": "pocket", "type": "binding_pocket@1", "cardinality": "one", "required": True}
        ],
    }
}

MANIFESTS = {
    "msign-affinity-prediction": yaml.safe_load(
        """
api_version: aidd.sciminer/tool-package.v2
kind: ToolPackage
metadata:
  slug: msign-affinity-prediction
  name: MSIGN Protein-Ligand Affinity Prediction
  version: 0.1.1
  description: Adapt MSIGN protein-ligand affinity predictions to standard molecule_table@1 artifacts.
artifacts:
  inputs:
    - name: protein
      type: protein_structure@1
      required: true
    - name: ligand
      type: ligand_structure@1
      required: true
  outputs:
    - name: affinity
      type: molecule_table@1
      cardinality: one
      required: true
    - name: report
      type: run_report@1
      cardinality: one
      required: false
parameters_schema:
  type: object
  properties:
    complex_id:
      type: string
      description: Optional complex identifier used in output table rows.
    distance:
      type: number
      default: 5.0
      minimum: 0.1
      maximum: 20.0
      description: Pocket cutoff distance in Angstrom used by the legacy MSIGN runtime.
    model_variant:
      type: string
      enum:
        - full_finetune
        - pretrain_general
      default: full_finetune
      description: MSIGN checkpoint family.
  additionalProperties: false
adapter:
  input:
    - input: protein
      method: mount_primary_structure_file
    - input: ligand
      method: mount_ligand_structure_file_or_convert_to_legacy_pdb
  output:
    - output: affinity
      method: collect_msign_prediction_as_molecule_table_v1
      validator_profile: molecule_table_v1_core
    - output: report
      method: collect_adapter_report_json
      validator_profile: run_report_v1_core
exposure:
  agent: true
  workflow: true
  direct_run: true
runtime:
  python: "3.9"
  cuda: "11.3"
  executor_support:
    - ssh_docker_exec
    - slurm
    - k8s_job
  selection_policy: "prefer container image by immutable digest; fallback to conda_pack only when the executor cannot run containers"
  artifacts:
    primary:
      kind: container
      image: registry.example/sciminer/msign-runtime:0.1.1
      image_digest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      includes:
        - python
        - cuda_runtime
        - dependencies
        - runtime_wrapper
    fallback:
      kind: conda_pack
      uri: artifacts://model-envs/msign-affinity-prediction/0.1.1/conda-env.tar.gz
      sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      includes:
        - python
        - dependencies
  weights:
    manifest_uri: artifacts://model-weights/msign-affinity-prediction/0.1.1/weights.json
    manifest_sha256: "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  cache_policy:
    key_fields:
      - metadata.slug
      - metadata.version
      - runtime.artifacts.selected.digest_or_sha256
      - runtime.weights.manifest_sha256
    mutable_host_paths_forbidden: true
variants:
  - name: cpu
    accelerator: cpu
    executor_types:
      - remote_job
    entrypoint:
      - runner/platform_run_v2.sh
    resources:
      cpu: 8
      memory_mb: 16384
    validation_status: validated
    hardware_validated: true
  - name: nvidia-cuda
    accelerator: nvidia_cuda
    executor_types:
      - remote_job
    entrypoint:
      - runner/platform_run_v2.sh
    resources:
      cpu: 8
      memory_mb: 24576
      gpu_memory_mb: 16384
      devices:
        - nvidia.com/gpu
      driver: ">=535"
    validation_status: unvalidated
    hardware_validated: false
"""
    ),
    "molp-pc-property-prediction": yaml.safe_load(
        """
api_version: aidd.sciminer/tool-package.v2
kind: ToolPackage
metadata:
  slug: molp-pc-property-prediction
  name: MolP-PC Property Prediction
  version: 0.1.1
  description: Adapt MolP-PC ADMET prediction CSV outputs to standard molecule_table@1 artifacts.
artifacts:
  inputs:
    - name: molecules
      type: molecule_table@1
      required: true
  outputs:
    - name: properties
      type: molecule_table@1
      cardinality: one
      required: true
    - name: report
      type: run_report@1
      cardinality: one
      required: false
parameters_schema:
  type: object
  properties:
    task_groups:
      type: array
      items:
        type: string
        enum:
          - Absorption
          - Distribution
          - Excretion
          - Metabolism
          - Toxicology
          - Tox21
          - Ecotoxicity
          - LD50
      default:
        - Absorption
        - Distribution
        - Excretion
        - Metabolism
        - Toxicology
        - Tox21
        - Ecotoxicity
        - LD50
      description: Requested ADMET task groups. Current legacy runtime emits all configured groups.
  additionalProperties: false
adapter:
  input:
    - input: molecules
      method: mount_molecule_table_with_smiles_column
  output:
    - output: properties
      method: collect_molp_pc_predictions_as_molecule_table_v1
      validator_profile: molecule_table_v1_core
    - output: report
      method: collect_adapter_report_json
      validator_profile: run_report_v1_core
exposure:
  agent: true
  workflow: true
  direct_run: true
runtime:
  python: "3.8"
  cuda: "11.3"
  executor_support:
    - ssh_docker_exec
    - slurm
    - k8s_job
  selection_policy: "prefer container image by immutable digest; fallback to conda_pack only when the executor cannot run containers"
  artifacts:
    primary:
      kind: container
      image: registry.example/sciminer/molp-pc-runtime:0.1.1
      image_digest: "sha256:4444444444444444444444444444444444444444444444444444444444444444"
      includes:
        - python
        - cuda_runtime
        - dependencies
        - runtime_wrapper
    fallback:
      kind: conda_pack
      uri: artifacts://model-envs/molp-pc-property-prediction/0.1.1/conda-env.tar.gz
      sha256: "5555555555555555555555555555555555555555555555555555555555555555"
      includes:
        - python
        - dependencies
  weights:
    manifest_uri: artifacts://model-weights/molp-pc-property-prediction/0.1.1/weights.json
    manifest_sha256: "6666666666666666666666666666666666666666666666666666666666666666"
  cache_policy:
    key_fields:
      - metadata.slug
      - metadata.version
      - runtime.artifacts.selected.digest_or_sha256
      - runtime.weights.manifest_sha256
    mutable_host_paths_forbidden: true
variants:
  - name: cpu
    accelerator: cpu
    executor_types:
      - remote_job
    entrypoint:
      - runner/platform_run_v2.sh
    resources:
      cpu: 8
      memory_mb: 16384
    validation_status: validated
    hardware_validated: true
  - name: nvidia-cuda
    accelerator: nvidia_cuda
    executor_types:
      - remote_job
    entrypoint:
      - runner/platform_run_v2.sh
    resources:
      cpu: 8
      memory_mb: 24576
      gpu_memory_mb: 16384
      devices:
        - nvidia.com/gpu
      driver: ">=535"
    validation_status: unvalidated
    hardware_validated: false
"""
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.utcnow()

    group_ids = {group["slug"]: _ensure_workbench_group(bind, now, group) for group in GROUPS}
    _ensure_existing_group_ids(bind, group_ids, ["molecular-generation"])

    owner_id = _resolve_owner_id(bind)
    if owner_id:
        for item in BUILTIN_TOOLS:
            _ensure_builtin_tool(bind, now, owner_id=owner_id, item=item)

    for slug, contract in LEGACY_ARTIFACT_CONTRACTS.items():
        _inject_artifact_contract(bind, now, slug=slug, contract=contract)

    for slug, manifest in MANIFESTS.items():
        _inject_tool_package_manifest(bind, now, slug=slug, manifest=manifest)

    for mapping in MAPPINGS:
        group_id = group_ids.get(mapping["group_slug"])
        tool_id = _tool_id(bind, str(mapping["tool_slug"]))
        if group_id and tool_id:
            _ensure_group_mapping(
                bind,
                now,
                group_id=group_id,
                tool_id=tool_id,
                sort_order=int(mapping["sort_order"]),
            )


def downgrade() -> None:
    bind = op.get_bind()

    for mapping in MAPPINGS:
        group_id = _group_id(bind, str(mapping["group_slug"]))
        tool_id = _tool_id(bind, str(mapping["tool_slug"]))
        if group_id and tool_id:
            bind.execute(
                sa.text(
                    "DELETE FROM tool_workbench_group_mappings "
                    "WHERE group_id = :group_id AND tool_id = :tool_id"
                ),
                {"group_id": group_id, "tool_id": tool_id},
            )

    for slug in MANIFESTS:
        _remove_tool_package_manifest(bind, slug=slug)

    for slug, contract in LEGACY_ARTIFACT_CONTRACTS.items():
        _remove_artifact_contract(bind, slug=slug, contract=contract)

    for group in GROUPS:
        bind.execute(
            sa.text(
                "DELETE FROM tool_workbench_groups WHERE slug = :slug "
                "AND NOT EXISTS ("
                "SELECT 1 FROM tool_workbench_group_mappings "
                "WHERE group_id = tool_workbench_groups.id)"
            ),
            {"slug": group["slug"]},
        )


def _ensure_workbench_group(bind, now: datetime, group: dict[str, Any]) -> str:
    row = bind.execute(
        sa.text("SELECT id FROM tool_workbench_groups WHERE slug = :slug"),
        {"slug": group["slug"]},
    ).first()
    if row:
        bind.execute(
            sa.text(
                "UPDATE tool_workbench_groups SET name = :name, description = :description, "
                "sort_order = :sort_order, is_enabled = true, updated_at = :now WHERE id = :id"
            ),
            {**group, "id": row[0], "now": now},
        )
        return str(row[0])

    group_id = str(uuid.uuid4())
    bind.execute(
        sa.text(
            "INSERT INTO tool_workbench_groups "
            "(id, created_at, updated_at, name, slug, description, sort_order, is_enabled) "
            "VALUES (:id, :now, :now, :name, :slug, :description, :sort_order, true)"
        ),
        {**group, "id": group_id, "now": now},
    )
    return group_id


def _ensure_existing_group_ids(bind, group_ids: dict[str, str], slugs: list[str]) -> None:
    for slug in slugs:
        existing = _group_id(bind, slug)
        if existing:
            group_ids[slug] = existing


def _resolve_owner_id(bind) -> str | None:
    configured = os.getenv("AIDD_SYSTEM_USER_ID")
    if configured:
        row = bind.execute(sa.text("SELECT id FROM users WHERE id = :id"), {"id": configured}).first()
        if row:
            return str(row[0])

    row = bind.execute(
        sa.text(
            "SELECT id FROM users WHERE role = 'admin' AND status = 'active' "
            "ORDER BY created_at ASC LIMIT 1"
        )
    ).first()
    if row:
        return str(row[0])

    row = bind.execute(sa.text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")).first()
    return str(row[0]) if row else None


def _ensure_builtin_tool(bind, now: datetime, *, owner_id: str, item: dict[str, Any]) -> str:
    slug = str(item["slug"])
    config = json.dumps(_capability_config(slug))
    row = bind.execute(
        sa.text("SELECT id, current_version_id FROM tools WHERE slug = :slug"),
        {"slug": slug},
    ).first()
    if row:
        tool_id = str(row[0])
        version_id = str(row[1]) if row[1] else str(uuid.uuid4())
        bind.execute(
            sa.text(
                "UPDATE tools SET owner_id = :owner_id, name = :name, description = :description, "
                "category = 'artifact-conversion', status = 'published', is_public = true, "
                "provider_type = 'platform', review_status = 'not_required', current_version_id = :version_id, "
                "gpu_required = false, gpu_memory_mb = 0, timeout_sec = 120, updated_at = :now "
                "WHERE id = :tool_id"
            ),
            {
                "owner_id": owner_id,
                "name": item["name"],
                "description": item["description"],
                "version_id": version_id,
                "now": now,
                "tool_id": tool_id,
            },
        )
        version_exists = bind.execute(
            sa.text("SELECT 1 FROM tool_versions WHERE id = :id"), {"id": version_id}
        ).first()
        if version_exists:
            bind.execute(
                sa.text(
                    "UPDATE tool_versions SET version = '1.0.0', changelog = :changelog, "
                    "config = :config, is_active = true, deprecated = false, updated_at = :now "
                    "WHERE id = :id"
                ),
                {
                    "id": version_id,
                    "now": now,
                    "config": config,
                    "changelog": "Workflow format conversion built-in",
                },
            )
        else:
            _insert_builtin_tool_version(bind, now, version_id=version_id, tool_id=tool_id, config=config)
        return tool_id

    tool_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    bind.execute(
        sa.text(
            "INSERT INTO tools (id, created_at, updated_at, owner_id, name, slug, description, "
            "category, status, is_public, provider_type, review_status, current_version_id, "
            "gpu_required, gpu_memory_mb, timeout_sec) "
            "VALUES (:id, :now, :now, :owner_id, :name, :slug, :description, "
            "'artifact-conversion', 'published', true, 'platform', 'not_required', :version_id, "
            "false, 0, 120)"
        ),
        {
            "id": tool_id,
            "now": now,
            "owner_id": owner_id,
            "name": item["name"],
            "slug": slug,
            "description": item["description"],
            "version_id": version_id,
        },
    )
    _insert_builtin_tool_version(bind, now, version_id=version_id, tool_id=tool_id, config=config)
    return tool_id


def _insert_builtin_tool_version(bind, now: datetime, *, version_id: str, tool_id: str, config: str) -> None:
    bind.execute(
        sa.text(
            "INSERT INTO tool_versions (id, created_at, updated_at, tool_id, version, changelog, "
            "config, is_active, deprecated) VALUES (:id, :now, :now, :tool_id, '1.0.0', "
            ":changelog, :config, true, false)"
        ),
        {
            "id": version_id,
            "now": now,
            "tool_id": tool_id,
            "changelog": "Workflow format conversion built-in",
            "config": config,
        },
    )


def _inject_tool_package_manifest(
    bind,
    now: datetime,
    *,
    slug: str,
    manifest: dict[str, Any],
) -> None:
    row = bind.execute(
        sa.text(
            "SELECT t.id, tv.id, tv.config FROM tools t "
            "JOIN tool_versions tv ON tv.id = t.current_version_id "
            "WHERE t.slug = :slug"
        ),
        {"slug": slug},
    ).first()
    if not row:
        return

    tool_id, version_id, raw_config = row
    config = _load_config(raw_config)
    config["tool_package_manifest"] = manifest
    metadata = manifest.get("metadata") or {}
    bind.execute(
        sa.text(
            "UPDATE tool_versions SET config = :config, is_active = true, "
            "deprecated = false, updated_at = :now WHERE id = :version_id"
        ),
        {
            "config": json.dumps(config),
            "now": now,
            "version_id": version_id,
        },
    )
    bind.execute(
        sa.text(
            "UPDATE tools SET name = :name, description = :description, status = 'published', "
            "is_public = true, provider_type = 'platform', review_status = 'not_required', "
            "updated_at = :now WHERE id = :tool_id"
        ),
        {
            "name": metadata.get("name") or slug,
            "description": metadata.get("description"),
            "now": now,
            "tool_id": tool_id,
        },
    )


def _remove_tool_package_manifest(bind, *, slug: str) -> None:
    row = bind.execute(
        sa.text(
            "SELECT tv.id, tv.config FROM tools t "
            "JOIN tool_versions tv ON tv.id = t.current_version_id "
            "WHERE t.slug = :slug"
        ),
        {"slug": slug},
    ).first()
    if not row:
        return
    version_id, raw_config = row
    config = _load_config(raw_config)
    manifest = config.get("tool_package_manifest")
    metadata = manifest.get("metadata") if isinstance(manifest, dict) else {}
    if isinstance(metadata, dict) and metadata.get("slug") == slug:
        config.pop("tool_package_manifest", None)
        bind.execute(
            sa.text("UPDATE tool_versions SET config = :config WHERE id = :version_id"),
            {"config": json.dumps(config), "version_id": version_id},
        )


def _inject_artifact_contract(
    bind,
    now: datetime,
    *,
    slug: str,
    contract: dict[str, Any],
) -> None:
    row = bind.execute(
        sa.text(
            "SELECT tv.id, tv.config FROM tools t "
            "JOIN tool_versions tv ON tv.id = t.current_version_id "
            "WHERE t.slug = :slug"
        ),
        {"slug": slug},
    ).first()
    if not row:
        return
    version_id, raw_config = row
    config = _load_config(raw_config)
    config["artifacts"] = contract
    bind.execute(
        sa.text("UPDATE tool_versions SET config = :config, updated_at = :now WHERE id = :version_id"),
        {"config": json.dumps(config), "now": now, "version_id": version_id},
    )


def _remove_artifact_contract(bind, *, slug: str, contract: dict[str, Any]) -> None:
    row = bind.execute(
        sa.text(
            "SELECT tv.id, tv.config FROM tools t "
            "JOIN tool_versions tv ON tv.id = t.current_version_id "
            "WHERE t.slug = :slug"
        ),
        {"slug": slug},
    ).first()
    if not row:
        return
    version_id, raw_config = row
    config = _load_config(raw_config)
    if config.get("artifacts") == contract:
        config.pop("artifacts", None)
        bind.execute(
            sa.text("UPDATE tool_versions SET config = :config WHERE id = :version_id"),
            {"config": json.dumps(config), "version_id": version_id},
        )


def _ensure_group_mapping(
    bind,
    now: datetime,
    *,
    group_id: str,
    tool_id: str,
    sort_order: int,
) -> None:
    row = bind.execute(
        sa.text(
            "SELECT id FROM tool_workbench_group_mappings "
            "WHERE group_id = :group_id AND tool_id = :tool_id"
        ),
        {"group_id": group_id, "tool_id": tool_id},
    ).first()
    if row:
        bind.execute(
            sa.text(
                "UPDATE tool_workbench_group_mappings SET sort_order = :sort_order, "
                "is_recommended = true, is_enabled = true, updated_at = :now WHERE id = :id"
            ),
            {"id": row[0], "sort_order": sort_order, "now": now},
        )
        return

    bind.execute(
        sa.text(
            "INSERT INTO tool_workbench_group_mappings "
            "(id, created_at, updated_at, tool_id, group_id, sort_order, is_recommended, is_enabled) "
            "VALUES (:id, :now, :now, :tool_id, :group_id, :sort_order, true, true)"
        ),
        {
            "id": str(uuid.uuid4()),
            "now": now,
            "tool_id": tool_id,
            "group_id": group_id,
            "sort_order": sort_order,
        },
    )


def _group_id(bind, slug: str) -> str | None:
    row = bind.execute(
        sa.text("SELECT id FROM tool_workbench_groups WHERE slug = :slug"),
        {"slug": slug},
    ).first()
    return str(row[0]) if row else None


def _tool_id(bind, slug: str) -> str | None:
    row = bind.execute(sa.text("SELECT id FROM tools WHERE slug = :slug"), {"slug": slug}).first()
    return str(row[0]) if row else None


def _load_config(raw_config: Any) -> dict[str, Any]:
    if isinstance(raw_config, dict):
        return dict(raw_config)
    if isinstance(raw_config, str):
        try:
            parsed = json.loads(raw_config)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}
