# AIDD Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an extensible AIDD agent layer that turns user intent plus protein/pocket inputs into validated tool-task chains using the existing SciTool task system.

**Architecture:** Add a backend agent orchestration layer above existing tools, tasks, files, and executors. Tool chaining is driven by explicit capability configs and semantic artifact types, with first support for protein/pocket to molecule generation and a path for docking, affinity, and property prediction. The frontend adds an agent entry panel to the existing `/workflow` workbench without replacing the current manual tool workflow.

**Tech Stack:** FastAPI, SQLAlchemy async models, SQLite-compatible schema scripts, Pydantic, existing task executor services, Vue 3, Pinia, Ant Design Vue, Node test runner, pytest.

**Project Constraint:** This repository instruction says not to plan or run git commits unless the user explicitly asks. This plan therefore omits commit steps.

---

## References

- Design doc: `docs/plans/2026-06-01-aidd-agent-design.md`
- Existing workbench page: `frontend/src/views/workflow/index.vue`
- Existing workbench runner: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Existing artifact picker: `frontend/src/components/tools/ArtifactFilePicker.vue`
- Existing task API: `backend/app/api/v1/tasks.py`
- Existing file artifact API: `backend/app/api/v1/files.py`
- Existing executor factory: `backend/app/tasks/executor.py`
- Existing task worker output normalization: `backend/app/worker/tasks.py`

---

### Task 1: Add Agent Persistence Models

**Files:**
- Create: `backend/app/models/agent.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/database/session.py`
- Create: `backend/scripts/create_agent_runs.sql`
- Test: `test/test_aidd_agent_models.py`

**Step 1: Write the failing model test**

Create `test/test_aidd_agent_models.py`:

```python
"""AIDD agent model registration tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base
from app.models import agent as _agent_models  # noqa: F401
from app.models import files as _files_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import tools as _tools_models  # noqa: F401
from app.models import users as _users_models  # noqa: F401


@pytest.mark.asyncio
async def test_agent_tables_are_registered() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        table_names = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))

    await engine.dispose()

    assert "agent_runs" in table_names
    assert "agent_run_steps" in table_names
```

**Step 2: Run the failing test**

Run: `pytest "test/test_aidd_agent_models.py" -q`

Expected: FAIL because `app.models.agent` does not exist.

**Step 3: Add models**

Create `backend/app/models/agent.py`:

```python
"""AIDD agent orchestration models."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class AgentRun(Base, UUIDMixin, TimestampMixin):
    """A single user-visible AIDD agent run."""

    __tablename__ = "agent_runs"

    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    intent = Column(String(100), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    input_type = Column(String(64), nullable=False)
    input_file_id = Column(String(36), ForeignKey("files.id"), nullable=True, index=True)
    requested_outputs = Column(JSON, nullable=False, default=list)
    plan = Column(JSON, nullable=False, default=dict)
    summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    user = relationship("User")
    input_file = relationship("File")
    steps = relationship(
        "AgentRunStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentRunStep.sort_order",
    )


class AgentRunStep(Base, UUIDMixin, TimestampMixin):
    """A single tool step inside an agent run."""

    __tablename__ = "agent_run_steps"

    agent_run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=False, index=True)
    step_key = Column(String(100), nullable=False, index=True)
    tool_slug = Column(String(100), nullable=False, index=True)
    tool_id = Column(String(36), ForeignKey("tools.id"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    depends_on_step_ids = Column(JSON, nullable=False, default=list)
    semantic_inputs = Column(JSON, nullable=False, default=dict)
    semantic_outputs = Column(JSON, nullable=False, default=dict)
    params = Column(JSON, nullable=False, default=dict)
    input_file_ids = Column(JSON, nullable=False, default=list)
    output_file_ids = Column(JSON, nullable=False, default=list)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    run = relationship("AgentRun", back_populates="steps")
    tool = relationship("Tool")
    task = relationship("Task")
```

Modify `backend/app/models/__init__.py` to import and export `AgentRun` and `AgentRunStep`.

Modify `backend/app/database/session.py` so `init_db()` imports `agent`:

```python
from app.models import users, tools, tasks, files, agent  # noqa
```

Create `backend/scripts/create_agent_runs.sql` with SQLite-compatible `CREATE TABLE IF NOT EXISTS` statements for `agent_runs` and `agent_run_steps`.

**Step 4: Run the model test**

Run: `pytest "test/test_aidd_agent_models.py" -q`

Expected: PASS.

---

### Task 2: Add Tool Capability Registry

**Files:**
- Create: `backend/app/agents/__init__.py`
- Create: `backend/app/agents/aidd/__init__.py`
- Create: `backend/app/agents/aidd/capabilities.py`
- Test: `test/test_aidd_agent_capabilities.py`

**Step 1: Write failing capability tests**

Create `test/test_aidd_agent_capabilities.py`:

```python
"""AIDD agent tool capability registry tests."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.capabilities import (
    AIDD_TOOL_CAPABILITIES,
    get_capability,
    get_capabilities_by_output,
)


def test_first_wave_capabilities_are_registered() -> None:
    assert get_capability("lvpocket-pocket-prediction").capability == "pocket_prediction"
    assert get_capability("gcdm-pocket-generation").capability == "molecule_generation"
    assert get_capability("molp-pc-property-prediction").capability == "property_prediction"
    assert get_capability("msign-affinity-prediction").capability == "affinity_prediction"


def test_capabilities_advertise_semantic_inputs_and_outputs() -> None:
    lvpocket = get_capability("lvpocket-pocket-prediction")
    assert [item.semantic_type for item in lvpocket.inputs] == ["protein_pdb"]
    assert [item.semantic_type for item in lvpocket.outputs] == ["pocket_pdb"]

    generation = get_capability("gcdm-pocket-generation")
    assert [item.semantic_type for item in generation.inputs] == ["pocket_pdb"]
    assert [item.semantic_type for item in generation.outputs] == ["generated_ligand"]


def test_capability_lookup_by_output() -> None:
    capabilities = get_capabilities_by_output("generated_ligand")
    assert [item.tool_slug for item in capabilities] == ["gcdm-pocket-generation"]
```

**Step 2: Run the failing test**

Run: `pytest "test/test_aidd_agent_capabilities.py" -q`

Expected: FAIL because the package and registry do not exist.

**Step 3: Implement the registry**

Create `backend/app/agents/aidd/capabilities.py` using frozen dataclasses:

```python
"""Static AIDD tool capability registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SemanticType = Literal[
    "protein_pdb",
    "pocket_pdb",
    "generated_ligand",
    "ligand_pdb",
    "smiles_csv",
    "docking_pose",
    "affinity_report",
    "property_report",
    "optimized_lead",
]


@dataclass(frozen=True)
class CapabilityInput:
    semantic_type: SemanticType
    field: str
    required: bool = True
    accepted_extensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutputMatch:
    extension: str | None = None
    filename_contains_any: tuple[str, ...] = ()
    content_type: str | None = None


@dataclass(frozen=True)
class CapabilityOutput:
    semantic_type: SemanticType
    source: Literal["output_files", "output_data"]
    match: OutputMatch | None = None
    path: str | None = None


@dataclass(frozen=True)
class ToolCapability:
    tool_slug: str
    capability: str
    stage: str
    inputs: tuple[CapabilityInput, ...]
    outputs: tuple[CapabilityOutput, ...]
    defaults: dict[str, object] = field(default_factory=dict)


AIDD_TOOL_CAPABILITIES: dict[str, ToolCapability] = {
    "lvpocket-pocket-prediction": ToolCapability(
        tool_slug="lvpocket-pocket-prediction",
        capability="pocket_prediction",
        stage="pocket_exploration",
        inputs=(
            CapabilityInput("protein_pdb", "protein_pdb", accepted_extensions=(".pdb",)),
        ),
        outputs=(
            CapabilityOutput(
                "pocket_pdb",
                "output_files",
                OutputMatch(extension=".pdb", filename_contains_any=("pocket", "Pocket")),
            ),
        ),
        defaults={"model_choice": "auto", "device": "auto"},
    ),
    "gcdm-pocket-generation": ToolCapability(
        tool_slug="gcdm-pocket-generation",
        capability="molecule_generation",
        stage="molecule_generation",
        inputs=(
            CapabilityInput("pocket_pdb", "input_files.pocket_pdb", accepted_extensions=(".pdb",)),
        ),
        outputs=(
            CapabilityOutput("generated_ligand", "output_files", OutputMatch(extension=".sdf")),
        ),
        defaults={"params.n_samples": 8, "params.device": "cuda:0"},
    ),
    "molp-pc-property-prediction": ToolCapability(
        tool_slug="molp-pc-property-prediction",
        capability="property_prediction",
        stage="property_prediction",
        inputs=(
            CapabilityInput("smiles_csv", "smiles_csv", accepted_extensions=(".csv",)),
        ),
        outputs=(
            CapabilityOutput("property_report", "output_files", OutputMatch(extension=".csv")),
        ),
        defaults={"device": "cpu"},
    ),
    "msign-affinity-prediction": ToolCapability(
        tool_slug="msign-affinity-prediction",
        capability="affinity_prediction",
        stage="affinity_prediction",
        inputs=(
            CapabilityInput("protein_pdb", "protein_pdb", accepted_extensions=(".pdb",)),
            CapabilityInput("ligand_pdb", "ligand_pdb", accepted_extensions=(".pdb",)),
        ),
        outputs=(
            CapabilityOutput("affinity_report", "output_data", path="result.outputs.prediction"),
        ),
        defaults={"device": "cpu"},
    ),
}


def get_capability(tool_slug: str) -> ToolCapability:
    return AIDD_TOOL_CAPABILITIES[tool_slug]


def get_capabilities_by_output(semantic_type: SemanticType) -> list[ToolCapability]:
    return [
        capability
        for capability in AIDD_TOOL_CAPABILITIES.values()
        if any(output.semantic_type == semantic_type for output in capability.outputs)
    ]
```

**Step 4: Run capability tests**

Run: `pytest "test/test_aidd_agent_capabilities.py" -q`

Expected: PASS.

---

### Task 3: Add Plan Builder

**Files:**
- Create: `backend/app/agents/aidd/planner.py`
- Test: `test/test_aidd_agent_planner.py`

**Step 1: Write failing planner tests**

Create `test/test_aidd_agent_planner.py`:

```python
"""AIDD agent plan builder tests."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.planner import build_aidd_plan


def test_protein_input_builds_pocket_then_generation_plan() -> None:
    plan = build_aidd_plan(
        message="上传蛋白后进行口袋探索并生成分子",
        input_type="protein_pdb",
        requested_outputs=["generated_ligand"],
        params={"generation_count": 12},
    )

    assert plan.intent == "generate_molecules_from_protein"
    assert [step.tool_slug for step in plan.steps] == [
        "lvpocket-pocket-prediction",
        "gcdm-pocket-generation",
    ]
    assert plan.steps[1].depends_on == ["pocket_prediction"]
    assert plan.steps[1].params["params.n_samples"] == 12


def test_pocket_input_skips_lvpocket() -> None:
    plan = build_aidd_plan(
        message="基于这个口袋生成分子",
        input_type="pocket_pdb",
        requested_outputs=["generated_ligand"],
        params={},
    )

    assert plan.intent == "generate_molecules_from_pocket"
    assert [step.tool_slug for step in plan.steps] == ["gcdm-pocket-generation"]


def test_property_prediction_can_be_appended_when_requested() -> None:
    plan = build_aidd_plan(
        message="从蛋白生成分子并预测性质",
        input_type="protein_pdb",
        requested_outputs=["generated_ligand", "property_report"],
        params={},
    )

    assert [step.step_key for step in plan.steps] == [
        "pocket_prediction",
        "molecule_generation",
        "property_prediction",
    ]
    assert plan.steps[2].depends_on == ["molecule_generation"]
```

**Step 2: Run failing planner tests**

Run: `pytest "test/test_aidd_agent_planner.py" -q`

Expected: FAIL because `planner.py` does not exist.

**Step 3: Implement minimal deterministic planner**

Create dataclasses in `backend/app/agents/aidd/planner.py`:

```python
"""Deterministic AIDD plan builder."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AIDDPlanStep:
    step_key: str
    tool_slug: str
    depends_on: list[str]
    inputs: dict[str, str]
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIDDPlan:
    intent: str
    requested_outputs: list[str]
    steps: list[AIDDPlanStep]

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def build_aidd_plan(
    *,
    message: str,
    input_type: str,
    requested_outputs: list[str],
    params: dict[str, Any],
) -> AIDDPlan:
    normalized_outputs = requested_outputs or ["generated_ligand"]
    generation_count = params.get("generation_count")

    steps: list[AIDDPlanStep] = []
    if input_type == "protein_pdb":
        intent = "generate_molecules_from_protein"
        steps.append(
            AIDDPlanStep(
                step_key="pocket_prediction",
                tool_slug="lvpocket-pocket-prediction",
                depends_on=[],
                inputs={"protein_pdb": "agent_input"},
                params={"model_choice": "auto", "device": params.get("device", "auto")},
            )
        )
        generation_input = "step:pocket_prediction:pocket_pdb"
        generation_depends = ["pocket_prediction"]
    elif input_type == "pocket_pdb":
        intent = "generate_molecules_from_pocket"
        generation_input = "agent_input"
        generation_depends = []
    else:
        raise ValueError(f"Unsupported AIDD input_type: {input_type}")

    generation_params: dict[str, Any] = {
        "params.device": params.get("device", "cuda:0"),
    }
    if generation_count is not None:
        generation_params["params.n_samples"] = generation_count
    else:
        generation_params["params.n_samples"] = 8

    steps.append(
        AIDDPlanStep(
            step_key="molecule_generation",
            tool_slug="gcdm-pocket-generation",
            depends_on=generation_depends,
            inputs={"pocket_pdb": generation_input},
            params=generation_params,
        )
    )

    wants_property = "property_report" in normalized_outputs or "性质" in message or "property" in message.lower()
    if wants_property:
        steps.append(
            AIDDPlanStep(
                step_key="property_prediction",
                tool_slug="molp-pc-property-prediction",
                depends_on=["molecule_generation"],
                inputs={"smiles_csv": "step:molecule_generation:generated_ligand"},
                params={"device": params.get("property_device", "cpu")},
            )
        )

    return AIDDPlan(intent=intent, requested_outputs=normalized_outputs, steps=steps)
```

**Step 4: Run planner tests**

Run: `pytest "test/test_aidd_agent_planner.py" -q`

Expected: PASS.

---

### Task 4: Add Backend Payload Mapping Helpers

**Files:**
- Create: `backend/app/agents/aidd/payloads.py`
- Test: `test/test_aidd_agent_payloads.py`

**Step 1: Write failing payload tests**

Create tests for dotted assignment and `ssh_job` file mapping:

```python
"""AIDD task payload mapping tests."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.capabilities import get_capability
from app.agents.aidd.payloads import build_agent_task_payload


def test_ssh_job_payload_maps_file_fields_to_runtime_input_paths() -> None:
    capability = get_capability("gcdm-pocket-generation")
    payload = build_agent_task_payload(
        capability=capability,
        executor_type="ssh_job",
        semantic_files={
            "pocket_pdb": {
                "file_id": "file-pocket",
                "filename": "pocket_001.pdb",
                "download_url": "/api/v1/files/file-pocket/download",
            }
        },
        step_params={"params.n_samples": 16},
    )

    assert payload.params["input_files"]["pocket_pdb"] == "input/pocket_001.pdb"
    assert payload.params["params"]["n_samples"] == 16
    assert payload.file_ids == ["file-pocket"]


def test_remote_payload_maps_file_fields_to_download_urls() -> None:
    capability = get_capability("lvpocket-pocket-prediction")
    payload = build_agent_task_payload(
        capability=capability,
        executor_type="remote_api",
        semantic_files={
            "protein_pdb": {
                "file_id": "file-protein",
                "filename": "protein.pdb",
                "download_url": "/api/v1/files/file-protein/download",
            }
        },
        step_params={},
    )

    assert payload.params["protein_pdb"] == "/api/v1/files/file-protein/download"
    assert payload.file_ids == ["file-protein"]
```

**Step 2: Run failing payload tests**

Run: `pytest "test/test_aidd_agent_payloads.py" -q`

Expected: FAIL because `payloads.py` does not exist.

**Step 3: Implement payload helper**

Create `backend/app/agents/aidd/payloads.py`:

```python
"""Build TaskCreate-compatible payloads for agent steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.aidd.capabilities import ToolCapability


@dataclass(frozen=True)
class AgentTaskPayload:
    params: dict[str, Any]
    file_ids: list[str]


def assign_dotted(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = target
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[parts[-1]] = value


def build_agent_task_payload(
    *,
    capability: ToolCapability,
    executor_type: str,
    semantic_files: dict[str, dict[str, str]],
    step_params: dict[str, Any],
) -> AgentTaskPayload:
    params: dict[str, Any] = {}
    file_ids: list[str] = []

    for key, value in {**capability.defaults, **step_params}.items():
        assign_dotted(params, key, value)

    for input_binding in capability.inputs:
        semantic_file = semantic_files.get(input_binding.semantic_type)
        if not semantic_file:
            if input_binding.required:
                raise ValueError(f"Missing required semantic input: {input_binding.semantic_type}")
            continue

        file_ids.append(semantic_file["file_id"])
        if executor_type == "ssh_job":
            field_value = f"input/{semantic_file['filename']}"
        else:
            field_value = semantic_file["download_url"]

        assign_dotted(params, input_binding.field, field_value)

    return AgentTaskPayload(params=params, file_ids=list(dict.fromkeys(file_ids)))
```

**Step 4: Run payload tests**

Run: `pytest "test/test_aidd_agent_payloads.py" -q`

Expected: PASS.

---

### Task 5: Add Semantic Output Extraction

**Files:**
- Create: `backend/app/agents/aidd/outputs.py`
- Test: `test/test_aidd_agent_outputs.py`

**Step 1: Write failing output extraction tests**

Create `test/test_aidd_agent_outputs.py`:

```python
"""AIDD semantic output extraction tests."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.capabilities import get_capability
from app.agents.aidd.outputs import extract_semantic_outputs


def test_extracts_output_file_by_extension_and_filename() -> None:
    outputs = extract_semantic_outputs(
        capability=get_capability("lvpocket-pocket-prediction"),
        task_output_files=[
            {"id": "file-log", "filename": "run.log", "content_type": "text/plain", "url": "/log"},
            {"id": "file-pocket", "filename": "best_pocket.pdb", "content_type": "chemical/x-pdb", "url": "/pdb"},
        ],
        output_data={},
    )

    assert outputs["pocket_pdb"]["file_id"] == "file-pocket"


def test_extracts_output_data_by_path() -> None:
    outputs = extract_semantic_outputs(
        capability=get_capability("msign-affinity-prediction"),
        task_output_files=[],
        output_data={"result": {"outputs": {"prediction": {"predicted_affinity": 7.2}}}},
    )

    assert outputs["affinity_report"]["value"]["predicted_affinity"] == 7.2
```

**Step 2: Run failing output tests**

Run: `pytest "test/test_aidd_agent_outputs.py" -q`

Expected: FAIL because `outputs.py` does not exist.

**Step 3: Implement extractor**

Create `backend/app/agents/aidd/outputs.py`:

```python
"""Extract semantic artifacts from completed task results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.aidd.capabilities import CapabilityOutput, ToolCapability


def read_path(data: Any, path: str | None) -> Any:
    if not path:
        return None
    current = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def file_matches(file_data: dict[str, Any], output: CapabilityOutput) -> bool:
    if not output.match:
        return False
    filename = str(file_data.get("original_name") or file_data.get("filename") or "")
    content_type = str(file_data.get("content_type") or "")
    if output.match.extension and Path(filename).suffix.lower() != output.match.extension.lower():
        return False
    if output.match.filename_contains_any:
        lowered = filename.lower()
        if not any(token.lower() in lowered for token in output.match.filename_contains_any):
            return False
    if output.match.content_type and output.match.content_type != content_type:
        return False
    return True


def extract_semantic_outputs(
    *,
    capability: ToolCapability,
    task_output_files: list[dict[str, Any]],
    output_data: Any,
) -> dict[str, dict[str, Any]]:
    semantic_outputs: dict[str, dict[str, Any]] = {}
    for output in capability.outputs:
        if output.source == "output_files":
            matched_file = next((file for file in task_output_files if file_matches(file, output)), None)
            if matched_file:
                semantic_outputs[output.semantic_type] = {
                    "source": "output_files",
                    "file_id": str(matched_file.get("id")),
                    "filename": matched_file.get("filename") or matched_file.get("original_name"),
                    "url": matched_file.get("url"),
                    "content_type": matched_file.get("content_type"),
                }
            continue

        value = read_path(output_data, output.path)
        if value is not None:
            semantic_outputs[output.semantic_type] = {
                "source": "output_data",
                "path": output.path,
                "value": value,
            }
    return semantic_outputs
```

**Step 4: Run output tests**

Run: `pytest "test/test_aidd_agent_outputs.py" -q`

Expected: PASS.

---

### Task 6: Extract Reusable Task Creation Service

**Files:**
- Create: `backend/app/tasks/service.py`
- Modify: `backend/app/api/v1/tasks.py`
- Test: `test/test_task_direct_execution.py`

**Step 1: Add a regression test**

Append to `test/test_task_direct_execution.py`:

```python
@pytest.mark.asyncio
async def test_create_task_api_uses_shared_task_creation_service(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    monkeypatch: pytest.MonkeyPatch,
):
    """任务 API 应保持现有行为，后续 agent 可以复用同一任务创建服务。"""
    runner = RecordingDirectRunner()
    monkeypatch.setattr(tasks_api.settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)

    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "params": {"alpha": 1},
            "file_ids": [],
        },
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["id"]
    assert runner.scheduled == [(task_id, published_tool.current_version_id)]
```

**Step 2: Run the regression test**

Run: `pytest "test/test_task_direct_execution.py::test_create_task_api_uses_shared_task_creation_service" -q`

Expected: PASS before refactor.

**Step 3: Move task creation logic into service**

Create `backend/app/tasks/service.py` with:

- `create_and_schedule_tool_task(db, current_user, task_data) -> Task`
- Internal helper to load tool/current version.
- Internal helper to record usage.
- Same direct/Celery scheduling behavior currently in `tasks.py`.

Keep `tasks.py` as the API layer:

```python
task = await create_and_schedule_tool_task(db, current_user, task_data)
return success_response(data=serialize_created_task(task), message="任务创建成功")
```

Move only reusable creation/scheduling logic. Keep route-specific permission and response code simple.

**Step 4: Run task tests**

Run:

- `pytest "test/test_task_direct_execution.py" -q`
- `pytest "test/test_task_naming.py" -q`

Expected: PASS.

---

### Task 7: Add Agent Schemas and API Surface

**Files:**
- Create: `backend/app/schemas/agent.py`
- Create: `backend/app/api/v1/agents.py`
- Modify: `backend/app/api/v1/__init__.py`
- Modify: `backend/app/schemas/__init__.py`
- Test: `test/test_aidd_agent_api.py`

**Step 1: Write failing API tests**

Create `test/test_aidd_agent_api.py` with an in-memory DB fixture similar to existing API tests. Cover:

```python
async def test_create_agent_run_from_protein_creates_run_and_first_step(...):
    response = await api_client.post(
        "/api/v1/agents/aidd/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "message": "上传蛋白后探索口袋并生成分子",
            "input_file_id": protein_file.id,
            "input_type": "protein_pdb",
            "requested_outputs": ["generated_ligand"],
            "params": {"generation_count": 8},
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["intent"] == "generate_molecules_from_protein"
    assert data["steps"][0]["tool_slug"] == "lvpocket-pocket-prediction"
```

Also cover:

- `GET /api/v1/agents/aidd/runs/{run_id}`
- Other user cannot read run.
- Unsupported `input_type` returns 422 or app validation error.

**Step 2: Run failing API tests**

Run: `pytest "test/test_aidd_agent_api.py" -q`

Expected: FAIL because API does not exist.

**Step 3: Add schemas**

Create `backend/app/schemas/agent.py`:

```python
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AIDDRunCreate(BaseModel):
    message: str = Field(..., min_length=1)
    input_file_id: str
    input_type: str
    requested_outputs: list[str] = Field(default_factory=lambda: ["generated_ligand"])
    params: dict[str, Any] = Field(default_factory=dict)


class AIDDRunStepResponse(BaseModel):
    id: str
    step_key: str
    tool_slug: str
    tool_id: Optional[str] = None
    task_id: Optional[str] = None
    status: str
    sort_order: int
    depends_on_step_ids: list[str] = Field(default_factory=list)
    semantic_inputs: dict[str, Any] = Field(default_factory=dict)
    semantic_outputs: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class AIDDRunResponse(BaseModel):
    id: str
    message: str
    intent: str
    status: str
    input_type: str
    input_file_id: Optional[str]
    requested_outputs: list[str]
    plan: dict[str, Any]
    summary: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    finished_at: Optional[datetime] = None
    steps: list[AIDDRunStepResponse] = Field(default_factory=list)
```

**Step 4: Add API router**

Create `backend/app/api/v1/agents.py` with:

- `POST /agents/aidd/runs`
- `GET /agents/aidd/runs`
- `GET /agents/aidd/runs/{run_id}`
- `POST /agents/aidd/runs/{run_id}/cancel`

For the first API implementation:

- Validate file belongs to current user.
- Build plan with `build_aidd_plan`.
- Create `AgentRun` and `AgentRunStep` records.
- Mark first dependency-free step as `ready` or `pending`.
- Do not execute tools yet; execution is Task 8.

Modify `backend/app/api/v1/__init__.py`:

```python
from app.api.v1 import auth, tools, tasks, files, websocket, users, system, verification, agents
api_router.include_router(agents.router, prefix="/agents", tags=["智能体"])
```

**Step 5: Run API tests**

Run: `pytest "test/test_aidd_agent_api.py" -q`

Expected: PASS for create/list/detail/cancel shape without actual task execution.

---

### Task 8: Add Agent Execution Service

**Files:**
- Create: `backend/app/agents/aidd/service.py`
- Modify: `backend/app/api/v1/agents.py`
- Test: `test/test_aidd_agent_execution.py`

**Step 1: Write failing execution tests**

Create tests that monkeypatch the shared task creation service:

```python
async def test_agent_run_schedules_first_ready_step(..., monkeypatch):
    created_tasks = []

    async def fake_create_task(db, current_user, task_data):
        created_tasks.append(task_data)
        return SimpleNamespace(id="task-pocket", tool_id=task_data.tool_id, status="PENDING", progress=0)

    monkeypatch.setattr("app.agents.aidd.service.create_and_schedule_tool_task", fake_create_task)

    response = await api_client.post(...)
    assert response.status_code == 200
    assert created_tasks[0].params["protein_pdb"] == "input/protein.pdb"
```

Cover:

- Protein input schedules LVPocket first.
- Pocket input schedules GCDM first.
- Missing tool causes run `failure` with error.

**Step 2: Run failing execution tests**

Run: `pytest "test/test_aidd_agent_execution.py" -q`

Expected: FAIL because execution service does not exist.

**Step 3: Implement execution service**

Create `backend/app/agents/aidd/service.py` with:

- `create_agent_run(db, current_user, request)`.
- `start_ready_steps(db, run_id)`.
- `schedule_step(db, current_user, run, step)`.
- `resolve_tool_by_slug(db, slug)`.
- `resolve_semantic_file(...)`.

Scheduling rules:

- Only schedule steps with all dependencies satisfied.
- First dependency-free step uses `agent_run.input_file_id`.
- Tool must be published and public.
- Use `build_agent_task_payload`.
- Use shared `create_and_schedule_tool_task`.
- Store `task_id`, `tool_id`, `params`, `input_file_ids`.
- Step status becomes `waiting_task`.
- Run status becomes `waiting_task`.

**Step 4: Run execution tests**

Run: `pytest "test/test_aidd_agent_execution.py" -q`

Expected: PASS.

---

### Task 9: Add Task Result Reconciliation

**Files:**
- Modify: `backend/app/agents/aidd/service.py`
- Create: `test/test_aidd_agent_reconcile.py`

**Step 1: Write failing reconciliation tests**

Create tests for:

- Completed LVPocket task extracts `pocket_pdb`.
- Completed first step schedules GCDM.
- Failed task marks step and run failure.
- Successful final step marks run success.

**Step 2: Add reconciliation service**

Add:

```python
async def reconcile_waiting_agent_steps(db: AsyncSession, run_id: str | None = None) -> int:
    ...
```

Rules:

- Query `AgentRunStep.status == "waiting_task"`.
- Load linked task with outputs and output files.
- If task pending/running, leave unchanged.
- If task failure/canceled, step failure and run failure.
- If task success, call `extract_semantic_outputs`.
- Persist semantic outputs and output file ids.
- Mark step success.
- Schedule downstream ready steps.
- If all steps success, mark run success.

**Step 3: Expose reconciliation endpoint for development**

Optional first version:

```text
POST /api/v1/agents/aidd/runs/{run_id}/sync
```

This endpoint lets the frontend or tests force status refresh before a proper background scheduler exists.

**Step 4: Run reconciliation tests**

Run: `pytest "test/test_aidd_agent_reconcile.py" -q`

Expected: PASS.

---

### Task 10: Add Frontend Types, API, and Store

**Files:**
- Modify: `frontend/src/types/models.d.ts`
- Create: `frontend/src/api/agents.ts`
- Modify: `frontend/src/api/index.ts`
- Create: `frontend/src/stores/agents.ts`
- Modify: `frontend/src/stores/index.ts`
- Test: `frontend/test/aidd-agent-surface.test.ts`

**Step 1: Write failing frontend surface test**

Create `frontend/test/aidd-agent-surface.test.ts`:

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const rootDir = resolve(import.meta.dirname, '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('前端应存在 AIDD agent API 和 store', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/api/agents.ts')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/stores/agents.ts')), true)

  const apiSource = readSource('src/api/agents.ts')
  const storeSource = readSource('src/stores/agents.ts')
  const indexSource = readSource('src/stores/index.ts')

  assert.equal(apiSource.includes('createAiddAgentRun'), true)
  assert.equal(apiSource.includes('getAiddAgentRun'), true)
  assert.equal(apiSource.includes('syncAiddAgentRun'), true)
  assert.equal(storeSource.includes('useAgentsStore'), true)
  assert.equal(indexSource.includes('useAgentsStore'), true)
})
```

**Step 2: Run failing frontend test**

Run: `node --test "frontend/test/aidd-agent-surface.test.ts"`

Expected: FAIL.

**Step 3: Add types and API**

Modify `frontend/src/types/models.d.ts` to add:

- `AiddAgentRunStatus`
- `AiddAgentStepStatus`
- `AiddAgentRun`
- `AiddAgentRunStep`
- `AiddAgentRunCreateParams`

Create `frontend/src/api/agents.ts`:

```ts
import { get, post } from './request'
import type { ApiResponse } from '@/types/api'
import type { AiddAgentRun, AiddAgentRunCreateParams, PaginatedResponse } from '@/types/models'

export const createAiddAgentRun = (data: AiddAgentRunCreateParams): Promise<ApiResponse<AiddAgentRun>> => {
  return post<AiddAgentRun>('/agents/aidd/runs', data)
}

export const getAiddAgentRun = (id: string): Promise<ApiResponse<AiddAgentRun>> => {
  return get<AiddAgentRun>(`/agents/aidd/runs/${id}`)
}

export const getAiddAgentRuns = (): Promise<ApiResponse<PaginatedResponse<AiddAgentRun>>> => {
  return get<PaginatedResponse<AiddAgentRun>>('/agents/aidd/runs')
}

export const cancelAiddAgentRun = (id: string): Promise<ApiResponse<AiddAgentRun>> => {
  return post<AiddAgentRun>(`/agents/aidd/runs/${id}/cancel`)
}

export const syncAiddAgentRun = (id: string): Promise<ApiResponse<AiddAgentRun>> => {
  return post<AiddAgentRun>(`/agents/aidd/runs/${id}/sync`)
}
```

Create `frontend/src/stores/agents.ts` with:

- `currentRun`
- `runs`
- `loading`
- `createRun`
- `fetchRun`
- `syncRun`
- `cancelRun`
- polling helper for non-terminal status

Export it from `frontend/src/stores/index.ts` and `frontend/src/api/index.ts`.

**Step 4: Run frontend surface test**

Run: `node --test "frontend/test/aidd-agent-surface.test.ts"`

Expected: PASS.

---

### Task 11: Add AIDD Agent Panel to Workflow Page

**Files:**
- Create: `frontend/src/components/workflow/AiddAgentPanel.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Test: `frontend/test/aidd-agent-surface.test.ts`

**Step 1: Extend frontend surface test**

Append assertions:

```ts
test('工作台应挂载 AIDD agent 入口组件', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/workflow/AiddAgentPanel.vue')), true)
  const workflowSource = readSource('src/views/workflow/index.vue')
  const panelSource = readSource('src/components/workflow/AiddAgentPanel.vue')

  assert.equal(workflowSource.includes('AiddAgentPanel'), true)
  assert.equal(panelSource.includes('createRun'), true)
  assert.equal(panelSource.includes('a-timeline'), true)
  assert.equal(panelSource.includes('input_type'), true)
})
```

Run: `node --test "frontend/test/aidd-agent-surface.test.ts"`

Expected: FAIL.

**Step 2: Build `AiddAgentPanel.vue`**

Component responsibilities:

- Message textarea.
- Input type segmented selection: `protein_pdb` / `pocket_pdb`.
- Upload control for one PDB file.
- Optional generation count input.
- Submit button.
- Timeline of current run steps.
- Links to task detail and output files when available.

Use existing `uploadFile` from `frontend/src/api/files.ts`.

Do not build a full chat UI in first version.

**Step 3: Mount in `/workflow`**

Modify `frontend/src/views/workflow/index.vue`:

- Import `AiddAgentPanel`.
- Render it above `.workflow-layout`.
- Keep existing workbench layout unchanged.

**Step 4: Add locale strings**

Add Chinese and English keys under `workflow.agent`.

**Step 5: Run frontend test**

Run: `node --test "frontend/test/aidd-agent-surface.test.ts"`

Expected: PASS.

---

### Task 12: Add Agent Polling and Result Refresh

**Files:**
- Modify: `frontend/src/components/workflow/AiddAgentPanel.vue`
- Modify: `frontend/src/stores/agents.ts`
- Test: `frontend/test/aidd-agent-surface.test.ts`

**Step 1: Add static assertions**

Extend surface test to assert:

- Store has `pollRunUntilTerminal`.
- Component calls `syncRun`.
- Component links to `/tasks/`.

**Step 2: Implement polling**

In `useAgentsStore`:

- Poll `getAiddAgentRun(runId)` every 3 seconds.
- Also call `syncAiddAgentRun(runId)` while status is `waiting_task` or `running`.
- Stop on `success`, `failure`, or `canceled`.

In `AiddAgentPanel.vue`:

- Start polling after `createRun`.
- Clear timer on unmount.

**Step 3: Run frontend tests**

Run: `node --test "frontend/test/aidd-agent-surface.test.ts"`

Expected: PASS.

---

### Task 13: Full Verification

**Files:**
- No new files.

**Step 1: Run focused backend tests**

Run:

- `pytest "test/test_aidd_agent_models.py" -q`
- `pytest "test/test_aidd_agent_capabilities.py" -q`
- `pytest "test/test_aidd_agent_planner.py" -q`
- `pytest "test/test_aidd_agent_payloads.py" -q`
- `pytest "test/test_aidd_agent_outputs.py" -q`
- `pytest "test/test_aidd_agent_api.py" -q`
- `pytest "test/test_aidd_agent_execution.py" -q`
- `pytest "test/test_aidd_agent_reconcile.py" -q`

Expected: PASS.

**Step 2: Run existing backend regression tests**

Run:

- `pytest "test/test_task_direct_execution.py" -q`
- `pytest "test/test_file_artifacts_api.py" -q`
- `pytest "test/test_tool_workbench_public_api.py" -q`

Expected: PASS.

**Step 3: Run focused frontend tests**

Run:

- `node --test "frontend/test/aidd-agent-surface.test.ts"`
- `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`
- `node --test "frontend/test/task-name-surface.test.ts"`

Expected: PASS.

**Step 4: Run build checks**

Run from `frontend/`:

- `npm run build`

Expected: PASS.

**Step 5: Manual smoke path**

With backend and frontend running:

1. Log in as a normal user.
2. Open `/workflow`.
3. Upload a protein `.pdb`.
4. Enter: `上传蛋白后进行口袋探索并生成分子`.
5. Submit agent run.
6. Confirm the first timeline step creates an LVPocket task.
7. After LVPocket succeeds, click sync or wait for polling.
8. Confirm GCDM task is created using the pocket output.
9. Confirm final generated ligand output appears in the run timeline and in “我的产物”.

---

## Implementation Notes

- Keep all agent tool execution through existing task creation and executor paths.
- Do not let client requests provide raw paths or arbitrary tool chains.
- The first version can use deterministic intent parsing. Leave an interface boundary so an LLM parser can be added later.
- Keep capability config explicit. Avoid filename-only guesses except inside declared output extractors.
- If a generated ligand is `.sdf` but a downstream tool requires `.pdb` or `.csv`, do not silently convert. Add a real conversion tool capability later.
- Preserve current `/workflow` manual workbench behavior.
