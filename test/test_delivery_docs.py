from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DELIVERY_INDEX = PROJECT_ROOT / "docs/delivery/04-V1交付验收索引.md"
DEPLOYMENT_GUIDE = PROJECT_ROOT / "docs/delivery/03-企业交付部署运维说明书.md"
PLATFORM_SMOKE = PROJECT_ROOT / "docs/verification/at003-platform-tool-smoke.md"
LOCAL_RUNTIME_NOTE = PROJECT_ROOT / "docs/verification/at003-direct-smoke.md"
PLATFORM_RECORD_TEMPLATE = PROJECT_ROOT / "docs/verification/templates/at003-platform-tool-run-record.md"
PLATFORM_EVIDENCE_SCRIPT = PROJECT_ROOT / "backend/scripts/collect_at003_platform_evidence.py"


def test_at003_acceptance_uses_platform_tool_invocation_as_primary_path() -> None:
    index_text = DELIVERY_INDEX.read_text(encoding="utf-8")
    deployment_text = DEPLOYMENT_GUIDE.read_text(encoding="utf-8")
    platform_text = PLATFORM_SMOKE.read_text(encoding="utf-8")
    local_text = LOCAL_RUNTIME_NOTE.read_text(encoding="utf-8")

    assert "AT-003 平台工具调用 smoke" in index_text
    assert "../verification/at003-platform-tool-smoke.md" in index_text
    assert "AT-003 平台工具调用 smoke" in deployment_text
    assert "../verification/at003-platform-tool-smoke.md" in deployment_text

    assert "平台工具调用" in platform_text
    assert "molp-pc-property-prediction" in platform_text
    assert "ToolVersion" in platform_text
    assert "create_and_schedule_tool_task" in platform_text
    assert "不得以 `model/MolP-PC/platform_run.sh` 作为平台验收主路径" in platform_text

    assert "模型包本地调试" in local_text
    assert "不是 AT-003 平台验收主路径" in local_text


def test_at003_platform_run_record_template_tracks_required_evidence() -> None:
    template_text = PLATFORM_RECORD_TEMPLATE.read_text(encoding="utf-8")

    required_terms = [
        "task_id",
        "ToolVersion",
        "tool_version_id",
        "molp-pc-property-prediction",
        "input_sha256",
        "ArtifactVersion",
        "artifact_version_id",
        "run_report@1",
        "molecule_table@1",
    ]
    for term in required_terms:
        assert term in template_text

    assert "不得记录 `model/MolP-PC/platform_run.sh`" in template_text


def test_at003_platform_smoke_documents_api_evidence_script() -> None:
    platform_text = PLATFORM_SMOKE.read_text(encoding="utf-8")
    script_text = PLATFORM_EVIDENCE_SCRIPT.read_text(encoding="utf-8")

    assert "backend/scripts/collect_at003_platform_evidence.py" in platform_text
    assert "--base-url" in platform_text
    assert "--task-id" in platform_text
    assert "--workflow-run-id" in platform_text
    assert "--workflow-node-id" in platform_text
    assert "--token" in platform_text
    assert "不得记录 `model/MolP-PC/platform_run.sh`" in script_text
    assert "subprocess" not in script_text
