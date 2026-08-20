"""Built-in AIDD agent tools."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.agents.aidd.outputs import parse_sdf_smiles
from app.agents.aidd.capabilities import PLACEHOLDER_AIDD_TOOL_SLUGS
from app.common.time import utcnow
from app.common.exceptions import ValidationException


@dataclass(frozen=True)
class BuiltinToolFile:
    file_id: str
    filename: str
    path: Path
    content_type: str | None = None


@dataclass(frozen=True)
class BuiltinToolArtifact:
    semantic_type: str
    filename: str
    content: bytes
    content_type: str
    source_file_id: str | None = None


@dataclass(frozen=True)
class BuiltinToolOutput:
    """非文件的语义输出（数据库查询结果、分析报告等）。"""

    semantic_type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BuiltinToolResult:
    artifacts: tuple[BuiltinToolArtifact, ...] = ()
    outputs: tuple[BuiltinToolOutput, ...] = ()
    standard_result: dict[str, Any] | None = None


def _smiles_csv_content(smiles_values: list[str]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["SMILES", "id"])
    for index, smiles in enumerate(smiles_values, start=1):
        writer.writerow([smiles, f"mol_{index}"])
    return output.getvalue().encode("utf-8")


def _vina_ranking_csv_content(report: dict[str, object]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "rank",
            "ligand_id",
            "ligand_filename",
            "protein_filename",
            "vina_score",
            "center_x",
            "center_y",
            "center_z",
            "size_x",
            "size_y",
            "size_z",
        ]
    )
    rows = report.get("scores") if isinstance(report.get("scores"), list) else [report]
    for index, row in enumerate(rows, start=1):
        row_data = row if isinstance(row, dict) else {}
        center = row_data.get("center") if isinstance(row_data.get("center"), dict) else {}
        size = row_data.get("size") if isinstance(row_data.get("size"), dict) else {}
        ligand_filename = str(row_data.get("ligand_filename") or report.get("ligand_filename") or "")
        writer.writerow(
            [
                index,
                row_data.get("ligand_id") or Path(ligand_filename).stem,
                ligand_filename,
                report.get("protein_filename") or "",
                row_data.get("vina_score") if row_data.get("vina_score") is not None else "",
                center.get("x", ""),
                center.get("y", ""),
                center.get("z", ""),
                size.get("x", ""),
                size.get("y", ""),
                size.get("z", ""),
            ]
        )
    return output.getvalue().encode("utf-8")


def convert_sdf_to_smiles_with_tool(source_path: Path) -> list[str]:
    command_template = os.environ.get("AIDD_SDF_TO_SMILES_COMMAND")
    if command_template:
        command = command_template.format(input=str(source_path))
        argv = shlex.split(command)
    else:
        argv = ["obabel", "-isdf", str(source_path), "-osmi"]

    try:
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise ValidationException(
            "SDF 转 SMILES 工具不可用，请安装 obabel 或配置 AIDD_SDF_TO_SMILES_COMMAND"
        ) from exc
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise ValidationException(
            f"SDF 转 SMILES 工具执行失败: {' '.join(argv)}"
            + (f" ({stderr})" if stderr else "")
        )

    smiles_values: list[str] = []
    for line in (result.stdout or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        token = stripped.split()[0]
        if token and token.upper() != "SMILES":
            smiles_values.append(token)

    if not smiles_values:
        raise ValidationException("SDF 转 SMILES 工具未返回任何 SMILES")
    return smiles_values


def convert_sdf_to_pdb_with_tool(source_path: Path) -> bytes:
    command_template = os.environ.get("AIDD_SDF_TO_PDB_COMMAND")
    if command_template:
        command = command_template.format(input=str(source_path))
        argv = shlex.split(command)
    else:
        argv = ["obabel", "-isdf", str(source_path), "-opdb"]

    try:
        result = subprocess.run(argv, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise ValidationException(
            "SDF 转 PDB 工具不可用，请安装 obabel 或配置 AIDD_SDF_TO_PDB_COMMAND"
        ) from exc
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or b"").decode("utf-8", errors="ignore").strip()
        raise ValidationException(
            f"SDF 转 PDB 工具执行失败: {' '.join(argv)}"
            + (f" ({stderr})" if stderr else "")
        )

    pdb_content = result.stdout or b""
    if not pdb_content.strip():
        raise ValidationException("SDF 转 PDB 工具未返回任何 PDB 内容")
    return pdb_content


def _pdb_coordinates(path: Path) -> list[tuple[float, float, float]]:
    coordinates: list[tuple[float, float, float]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.startswith(("ATOM", "HETATM")) or len(line) < 54:
            continue
        try:
            coordinates.append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
        except ValueError:
            continue
    return coordinates


def _vina_box_from_ligand(ligand_path: Path) -> tuple[dict[str, float], dict[str, float]]:
    coordinates = _pdb_coordinates(ligand_path)
    if not coordinates:
        raise ValidationException("Vina docking 无法从 ligand_pdb 读取坐标")

    xs = [coord[0] for coord in coordinates]
    ys = [coord[1] for coord in coordinates]
    zs = [coord[2] for coord in coordinates]
    center = {
        "x": round(sum(xs) / len(xs), 3),
        "y": round(sum(ys) / len(ys), 3),
        "z": round(sum(zs) / len(zs), 3),
    }
    default_size = float(os.environ.get("AIDD_VINA_BOX_SIZE", "22.5"))
    padding = float(os.environ.get("AIDD_VINA_BOX_PADDING", "10.0"))
    size = {
        "x": round(max(default_size, max(xs) - min(xs) + padding), 3),
        "y": round(max(default_size, max(ys) - min(ys) + padding), 3),
        "z": round(max(default_size, max(zs) - min(zs) + padding), 3),
    }
    return center, size


def _convert_pdb_to_pdbqt(source_path: Path, target_path: Path, *, rigid: bool = False) -> None:
    obabel = shutil.which("obabel")
    if not obabel:
        raise ValidationException("Vina docking 需要 obabel 将 PDB 转为 PDBQT")

    argv = [obabel, "-ipdb", str(source_path), "-opdbqt", "-O", str(target_path)]
    if rigid:
        argv.append("-xr")

    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not target_path.exists():
        detail = (result.stderr or result.stdout or "OpenBabel PDBQT 转换失败").strip()
        raise ValidationException(f"Vina docking 输入转换失败: {detail}")


def _split_ligand_pdb_models(ligand_path: Path, target_dir: Path) -> list[Path]:
    lines = ligand_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    models: list[list[str]] = []
    current_model: list[str] | None = None

    for line in lines:
        if line.startswith("MODEL"):
            current_model = []
            continue
        if line.startswith("ENDMDL"):
            if current_model:
                models.append(current_model)
            current_model = None
            continue
        if current_model is not None:
            if line.startswith(("ATOM", "HETATM", "TER", "CONECT")):
                current_model.append(line)

    if not models:
        return [ligand_path]

    split_paths: list[Path] = []
    for index, model_lines in enumerate(models, start=1):
        if not any(line.startswith(("ATOM", "HETATM")) for line in model_lines):
            continue
        split_path = target_dir / f"ligand_{index}.pdb"
        split_path.write_text("\n".join([*model_lines, "END", ""]), encoding="utf-8")
        split_paths.append(split_path)

    if not split_paths:
        raise ValidationException("Vina docking 未能从 ligand_pdb 拆分出有效分子")
    return split_paths


def _parse_vina_score(stdout: str) -> float | None:
    for line in stdout.splitlines():
        stripped = line.strip()
        match = re.match(r"^1\s+(-?\d+(?:\.\d+)?)\s+", stripped)
        if match:
            return float(match.group(1))
    fallback = re.search(r"Affinity:\s*(-?\d+(?:\.\d+)?)", stdout, flags=re.IGNORECASE)
    return float(fallback.group(1)) if fallback else None


def run_vina_docking_with_tool(protein_path: Path, ligand_path: Path) -> dict[str, object]:
    if not protein_path.exists() or not protein_path.is_file():
        raise ValidationException("Vina docking 缺少 protein_pdb 输入文件")
    if not ligand_path.exists() or not ligand_path.is_file():
        raise ValidationException("Vina docking 缺少 ligand_pdb 输入文件")

    center, size = _vina_box_from_ligand(ligand_path)
    with tempfile.TemporaryDirectory(prefix="aidd-vina-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        receptor_pdbqt = tmp_path / "receptor.pdbqt"
        _convert_pdb_to_pdbqt(protein_path, receptor_pdbqt, rigid=True)
        ligand_models = _split_ligand_pdb_models(ligand_path, tmp_path)

        command_template = os.environ.get("AIDD_VINA_COMMAND")
        scores: list[dict[str, object]] = []
        for index, ligand_model_path in enumerate(ligand_models, start=1):
            ligand_pdbqt = tmp_path / f"ligand_{index}.pdbqt"
            output_pdbqt = tmp_path / f"docked_{index}.pdbqt"
            _convert_pdb_to_pdbqt(ligand_model_path, ligand_pdbqt, rigid=False)

            if command_template:
                command = command_template.format(
                    receptor=str(receptor_pdbqt),
                    ligand=str(ligand_pdbqt),
                    out=str(output_pdbqt),
                    center_x=center["x"],
                    center_y=center["y"],
                    center_z=center["z"],
                    size_x=size["x"],
                    size_y=size["y"],
                    size_z=size["z"],
                )
                argv = shlex.split(command)
            else:
                vina = shutil.which("vina")
                if not vina:
                    raise ValidationException("Vina docking 工具不可用，请安装 vina 或配置 AIDD_VINA_COMMAND")
                argv = [
                    vina,
                    "--receptor",
                    str(receptor_pdbqt),
                    "--ligand",
                    str(ligand_pdbqt),
                    "--center_x",
                    str(center["x"]),
                    "--center_y",
                    str(center["y"]),
                    "--center_z",
                    str(center["z"]),
                    "--size_x",
                    str(size["x"]),
                    "--size_y",
                    str(size["y"]),
                    "--size_z",
                    str(size["z"]),
                    "--out",
                    str(output_pdbqt),
                ]

            result = subprocess.run(argv, capture_output=True, text=True, check=False)
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            if result.returncode != 0:
                detail = (stderr or stdout or "Vina docking 执行失败").strip()
                raise ValidationException(f"Vina docking 执行失败: {detail}")

            vina_score = _parse_vina_score(stdout)
            if vina_score is None:
                raise ValidationException("Vina docking 未返回可解析的 score")

            scores.append(
                {
                    "ligand_id": f"ligand_{index}",
                    "ligand_filename": f"{Path(ligand_path.name).stem}#{index}",
                    "vina_score": vina_score,
                    "center": center,
                    "size": size,
                    "stdout": stdout.strip(),
                    "stderr": stderr.strip(),
                }
            )

        scores.sort(key=lambda item: float(item["vina_score"]))
        best = scores[0]
        return {
            "vina_score": best["vina_score"],
            "center": center,
            "size": size,
            "scores": scores,
            "stdout": best.get("stdout", ""),
            "stderr": best.get("stderr", ""),
        }


def _run_sdf_to_smiles_csv_tool(files: dict[str, BuiltinToolFile]) -> BuiltinToolResult:
    source_file = files.get("generated_ligand")
    if not source_file:
        raise ValidationException("SDF 转 SMILES 缺少 generated_ligand 输入")
    if not source_file.path.exists() or not source_file.path.is_file():
        raise ValidationException("SDF 转 SMILES 输入文件已被删除")

    smiles_values = parse_sdf_smiles(source_file.path.read_text(encoding="utf-8"))
    if not smiles_values:
        smiles_values = convert_sdf_to_smiles_with_tool(source_file.path)
    if not smiles_values:
        raise ValidationException("无法从 SDF 文件提取 SMILES 字段")

    return BuiltinToolResult(
        artifacts=(
            BuiltinToolArtifact(
                semantic_type="smiles_csv",
                filename=f"{Path(source_file.filename).stem}_smiles.csv",
                content=_smiles_csv_content(smiles_values),
                content_type="text/csv",
                source_file_id=source_file.file_id,
            ),
        )
    )


def _run_sdf_to_pdb_tool(files: dict[str, BuiltinToolFile]) -> BuiltinToolResult:
    source_file = files.get("generated_ligand")
    if not source_file:
        raise ValidationException("SDF 转 PDB 缺少 generated_ligand 输入")
    if not source_file.path.exists() or not source_file.path.is_file():
        raise ValidationException("SDF 转 PDB 输入文件已被删除")

    pdb_content = convert_sdf_to_pdb_with_tool(source_file.path)
    return BuiltinToolResult(
        artifacts=(
            BuiltinToolArtifact(
                semantic_type="ligand_pdb",
                filename=f"{Path(source_file.filename).stem}_ligand.pdb",
                content=pdb_content,
                content_type="chemical/x-pdb",
                source_file_id=source_file.file_id,
            ),
        )
    )


def _run_vina_docking_tool(files: dict[str, BuiltinToolFile]) -> BuiltinToolResult:
    protein_file = files.get("protein_pdb")
    ligand_file = files.get("ligand_pdb")
    if not protein_file or not ligand_file:
        raise ValidationException("Vina docking 缺少 protein_pdb 或 ligand_pdb 输入")

    report = run_vina_docking_with_tool(protein_file.path, ligand_file.path)
    report.update(
        {
            "protein_file_id": protein_file.file_id,
            "ligand_file_id": ligand_file.file_id,
            "protein_filename": protein_file.filename,
            "ligand_filename": ligand_file.filename,
        }
    )
    content = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    ranking_content = _vina_ranking_csv_content(report)
    return BuiltinToolResult(
        artifacts=(
            BuiltinToolArtifact(
                semantic_type="docking_report",
                filename=f"{Path(ligand_file.filename).stem}_vina_report.json",
                content=content,
                content_type="application/json",
                source_file_id=ligand_file.file_id,
            ),
            BuiltinToolArtifact(
                semantic_type="ranking_csv",
                filename=f"{Path(ligand_file.filename).stem}_vina_ranking.csv",
                content=ranking_content,
                content_type="text/csv",
                source_file_id=ligand_file.file_id,
            ),
        )
    )


def _run_protein_preparation_tool(
    files: dict[str, BuiltinToolFile],
    params: dict[str, Any] | None = None,
) -> BuiltinToolResult:
    from app.protein_preparation.engine import ProteinPreparationError, prepare_protein
    from app.schemas.protein_preparation import ProteinPreparationOptions

    protein_file = files.get("protein_structure@1") or files.get("protein") or files.get("protein_pdb")
    if not protein_file:
        raise ValidationException("蛋白制备缺少 protein_structure@1 输入")
    if not protein_file.path.exists() or not protein_file.path.is_file():
        raise ValidationException("蛋白制备输入文件已被删除")

    params = params if isinstance(params, dict) else {}
    option_payload = params.get("options")
    if not isinstance(option_payload, dict):
        option_keys = {
            "ph",
            "remove_water",
            "keep_metals",
            "keep_cofactors",
            "remove_non_target_ligands",
            "output_formats",
        }
        option_payload = {key: params[key] for key in option_keys if key in params}
    options = ProteinPreparationOptions.model_validate(option_payload)
    if "prepared_pdb" not in options.output_formats:
        options = options.model_copy(
            update={"output_formats": ["prepared_pdb", *options.output_formats]}
        )
    advanced_options = params.get("advanced_options") if isinstance(params.get("advanced_options"), dict) else {}
    preparation_profile = str(params.get("preparation_profile") or "docking_v1")

    with tempfile.TemporaryDirectory(prefix="aidd-protein-prep-") as tmp_dir:
        try:
            preparation = prepare_protein(
                protein_file.path,
                options,
                advanced_options=advanced_options,
                output_dir=Path(tmp_dir),
            )
        except ProteinPreparationError as exc:
            raise ValidationException(str(exc)) from exc

        prepared_file = preparation.files.get("prepared_pdb")
        if not prepared_file:
            raise ValidationException("蛋白制备未生成 prepared_pdb 输出")
        prepared_content = prepared_file.path.read_bytes()
        metadata = _protein_preparation_metadata(
            prepared_content.decode("utf-8", errors="ignore"),
            source_file=protein_file,
            options=options,
            preparation_profile=preparation_profile,
        )
        report = dict(preparation.report)
        report.update(
            {
                "preparation_profile": preparation_profile,
                "source_file_id": protein_file.file_id,
                "source_filename": protein_file.filename,
                "metadata": metadata,
                "warnings": list(preparation.warnings),
            }
        )
        report_content = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")

        artifacts = [
            BuiltinToolArtifact(
                semantic_type="prepared_pdb",
                filename="prepared.pdb",
                content=prepared_content,
                content_type="chemical/x-pdb",
                source_file_id=protein_file.file_id,
            ),
            BuiltinToolArtifact(
                semantic_type="preparation_report_json",
                filename="preparation_report.json",
                content=report_content,
                content_type="application/json",
                source_file_id=protein_file.file_id,
            ),
        ]
        output_files: dict[str, dict[str, str]] = {
            "structure_file": _standard_output_file_ref(
                "prepared.pdb", prepared_content, "chemical/x-pdb"
            ),
            "prepared_pdb": _standard_output_file_ref(
                "prepared.pdb", prepared_content, "chemical/x-pdb"
            ),
            "metadata_json": _standard_output_file_ref(
                "preparation_report.json", report_content, "application/json"
            ),
            "preparation_report_json": _standard_output_file_ref(
                "preparation_report.json", report_content, "application/json"
            ),
        }

        receptor_file = preparation.files.get("receptor_pdbqt")
        if receptor_file:
            receptor_content = receptor_file.path.read_bytes()
            artifacts.append(
                BuiltinToolArtifact(
                    semantic_type="receptor_pdbqt",
                    filename="receptor.pdbqt",
                    content=receptor_content,
                    content_type="chemical/x-pdbqt",
                    source_file_id=protein_file.file_id,
                )
            )
            output_files["receptor_pdbqt"] = _standard_output_file_ref(
                "receptor.pdbqt", receptor_content, "chemical/x-pdbqt"
            )

    return BuiltinToolResult(
        artifacts=tuple(artifacts),
        standard_result={
            "result_version": "aidd.sciminer/result.v2",
            "artifacts": {
                "prepared_protein": {
                    "type": "protein_structure@1",
                    "name": f"Prepared {Path(protein_file.filename).stem}",
                    "files": output_files,
                    "metadata": metadata,
                    "summary": {
                        "source_file_id": protein_file.file_id,
                        "source_filename": protein_file.filename,
                        "preparation_profile": preparation_profile,
                    },
                }
            },
            "summary": {"prepared_protein": "prepared_protein"},
        },
    )


def _standard_output_file_ref(path: str, content: bytes, content_type: str) -> dict[str, str]:
    return {
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "content_type": content_type,
    }


# ======================================================================
# 外部数据库 fetch（RCSB PDB / PubChem → 标准 Artifact）
# ======================================================================


def _external_database_providers() -> dict[str, Any]:
    from app.external_databases.providers import default_external_database_providers

    return default_external_database_providers()


async def _run_fetch_pdb_tool(
    _files: dict[str, BuiltinToolFile],
    params: dict[str, Any] | None = None,
) -> BuiltinToolResult:
    params = params if isinstance(params, dict) else {}
    pdb_id = str(params.get("pdb_id") or params.get("identifier") or "").strip()
    if not pdb_id:
        raise ValidationException("fetch_pdb 需要 pdb_id 参数")
    provider = _external_database_providers().get("rcsb")
    if provider is None:
        raise ValidationException("RCSB PDB fetch provider 未配置")
    payload = await provider.fetch_protein(pdb_id)
    return _external_payload_to_builtin_result(
        payload,
        output_name="protein",
        report_filename="fetch_pdb_report.json",
        report_title="Fetch PDB report",
    )


async def _run_fetch_ligand_tool(
    _files: dict[str, BuiltinToolFile],
    params: dict[str, Any] | None = None,
) -> BuiltinToolResult:
    params = params if isinstance(params, dict) else {}
    pubchem_cid = str(
        params.get("pubchem_cid") or params.get("cid") or params.get("identifier") or ""
    ).strip()
    if not pubchem_cid:
        raise ValidationException("fetch_ligand 需要 pubchem_cid 参数")
    provider = _external_database_providers().get("pubchem")
    if provider is None:
        raise ValidationException("PubChem fetch provider 未配置")
    payload = await provider.fetch_ligand(pubchem_cid)
    return _external_payload_to_builtin_result(
        payload,
        output_name="ligand",
        report_filename="fetch_ligand_report.json",
        report_title="Fetch ligand report",
    )


def _external_payload_to_builtin_result(
    payload: Any,
    *,
    output_name: str,
    report_filename: str,
    report_title: str,
) -> BuiltinToolResult:
    metadata = dict(payload.metadata or {})
    metadata.setdefault("fetched_at", utcnow().isoformat())
    files_by_role = {artifact_file.role: artifact_file for artifact_file in payload.files}
    if "metadata_json" not in files_by_role:
        from app.external_databases.providers import ExternalArtifactFile

        metadata_content = json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        files_by_role["metadata_json"] = ExternalArtifactFile(
            role="metadata_json",
            filename="metadata.json",
            content=metadata_content,
            content_type="application/json",
        )

    report = {
        "status": "succeeded",
        "output_name": output_name,
        "artifact_type": payload.standard_ref,
        "source_database": metadata.get("source_database"),
        "source_id": metadata.get("source_id"),
        "fetched_at": metadata.get("fetched_at"),
    }
    report_content = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")

    artifacts = [
        BuiltinToolArtifact(
            semantic_type=str(payload.standard_ref),
            filename=artifact_file.filename,
            content=artifact_file.content,
            content_type=artifact_file.content_type,
        )
        for artifact_file in files_by_role.values()
    ]
    artifacts.append(
        BuiltinToolArtifact(
            semantic_type="run_report",
            filename=report_filename,
            content=report_content,
            content_type="application/json",
        )
    )

    output_files = {
        role: _standard_output_file_ref(
            artifact_file.filename,
            artifact_file.content,
            artifact_file.content_type,
        )
        for role, artifact_file in files_by_role.items()
    }
    return BuiltinToolResult(
        artifacts=tuple(artifacts),
        standard_result={
            "result_version": "aidd.sciminer/result.v2",
            "artifacts": {
                output_name: {
                    "type": payload.standard_ref,
                    "name": payload.name,
                    "files": output_files,
                    "metadata": metadata,
                    "summary": {
                        "source_database": metadata.get("source_database"),
                        "source_id": metadata.get("source_id"),
                    },
                },
                "report": {
                    "type": "run_report@1",
                    "name": report_title,
                    "files": {
                        "report_json": _standard_output_file_ref(
                            report_filename,
                            report_content,
                            "application/json",
                        )
                    },
                    "metadata": {
                        "source_task_id": str(metadata.get("source_id") or output_name),
                    },
                },
            },
            "relations": [{"from": "report", "to": output_name, "type": "describes"}],
            "summary": {"fetched_artifact": output_name},
        },
    )


def _protein_preparation_metadata(
    prepared_pdb: str,
    *,
    source_file: BuiltinToolFile,
    options: Any,
    preparation_profile: str,
) -> dict[str, Any]:
    atoms = [line for line in prepared_pdb.splitlines() if line.startswith(("ATOM", "HETATM"))]
    chain_ids = sorted({line[21].strip() for line in atoms if len(line) > 21 and line[21].strip()})
    residues = {
        (
            line[21].strip() if len(line) > 21 else "",
            line[22:26].strip() if len(line) >= 26 else "",
            line[17:20].strip() if len(line) >= 20 else "",
        )
        for line in atoms
    }
    return {
        "chain_ids": chain_ids,
        "residue_count": len(residues),
        "atom_count": len(atoms),
        "structure_format": "pdb",
        "source_filename": source_file.filename,
        "preparation_status": "prepared",
        "preparation_profile": preparation_profile,
        "ph": options.ph,
        "remove_water": options.remove_water,
        "keep_metals": options.keep_metals,
        "keep_cofactors": options.keep_cofactors,
        "remove_non_target_ligands": options.remove_non_target_ligands,
        "preparation_engine": "sciminer-local-v1",
    }


# ======================================================================
# RDKit properties（平台内置传统 CADD 描述符）
# ======================================================================


_RDKIT_PROPERTY_COLUMNS = [
    "molecular_weight",
    "logp",
    "tpsa",
    "hbd",
    "hba",
    "rotatable_bonds",
    "heavy_atoms",
    "qed",
    "lipinski_violations",
]


class _RDKitDescriptorBackend:
    def __init__(self) -> None:
        try:
            from rdkit import Chem, rdBase
            from rdkit.Chem import Crippen, Descriptors, QED, rdMolDescriptors
        except ImportError as exc:  # pragma: no cover - depends on runtime image
            raise ValidationException("RDKit 未安装，无法执行内置 RDKit 分子属性计算") from exc
        self._chem = Chem
        self._crippen = Crippen
        self._descriptors = Descriptors
        self._qed = QED
        self._rd_mol_descriptors = rdMolDescriptors
        self.name = "RDKit"
        self.version = rdBase.rdkitVersion

    def molecule_from_smiles(self, smiles: str):
        return self._chem.MolFromSmiles(smiles)

    def descriptors(self, molecule) -> dict[str, float | int]:
        values: dict[str, float | int] = {
            "molecular_weight": float(self._descriptors.MolWt(molecule)),
            "logp": float(self._crippen.MolLogP(molecule)),
            "tpsa": float(self._rd_mol_descriptors.CalcTPSA(molecule)),
            "hbd": int(self._rd_mol_descriptors.CalcNumHBD(molecule)),
            "hba": int(self._rd_mol_descriptors.CalcNumHBA(molecule)),
            "rotatable_bonds": int(self._rd_mol_descriptors.CalcNumRotatableBonds(molecule)),
            "heavy_atoms": int(molecule.GetNumHeavyAtoms()),
            "qed": float(self._qed.qed(molecule)),
        }
        values["lipinski_violations"] = _lipinski_violations(values)
        return values


def _rdkit_descriptor_backend() -> _RDKitDescriptorBackend:
    return _RDKitDescriptorBackend()


def _run_rdkit_properties_tool(
    files: dict[str, BuiltinToolFile],
    params: dict[str, Any] | None = None,
) -> BuiltinToolResult:
    source_file = (
        files.get("smiles_csv")
        or files.get("molecule_table@1")
        or files.get("molecules")
    )
    if not source_file:
        raise ValidationException("RDKit properties 缺少 smiles_csv 或 molecule_table@1 输入")
    if not source_file.path.exists() or not source_file.path.is_file():
        raise ValidationException("RDKit properties 输入文件已被删除")

    params = params if isinstance(params, dict) else {}
    smiles_field = str(params.get("smiles_field") or "SMILES")
    molecule_id_field = str(params.get("molecule_id_field") or "")
    table_content, metadata = _rdkit_properties_csv_content(
        source_file.path,
        smiles_field=smiles_field,
        molecule_id_field=molecule_id_field,
        backend=_rdkit_descriptor_backend(),
    )
    metadata.update(
        {
            "source_file_id": source_file.file_id,
            "source_filename": source_file.filename,
            "source_task_id": str(params.get("task_id") or source_file.file_id),
        }
    )
    metadata_content = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")
    report = {
        "tool": "builtin-rdkit-properties",
        "status": "succeeded",
        "source_file_id": source_file.file_id,
        "source_filename": source_file.filename,
        "row_count": metadata["row_count"],
        "valid_molecule_count": metadata["valid_molecule_count"],
        "invalid_molecule_count": metadata["invalid_molecule_count"],
        "backend_name": metadata["backend_name"],
        "backend_version": metadata["backend_version"],
    }
    report_content = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")

    table_filename = "rdkit_properties.csv"
    metadata_filename = "rdkit_properties_metadata.json"
    report_filename = "rdkit_properties_report.json"
    return BuiltinToolResult(
        artifacts=(
            BuiltinToolArtifact(
                semantic_type="property_report",
                filename=table_filename,
                content=table_content,
                content_type="text/csv",
                source_file_id=source_file.file_id,
            ),
            BuiltinToolArtifact(
                semantic_type="property_metadata_json",
                filename=metadata_filename,
                content=metadata_content,
                content_type="application/json",
                source_file_id=source_file.file_id,
            ),
            BuiltinToolArtifact(
                semantic_type="run_report",
                filename=report_filename,
                content=report_content,
                content_type="application/json",
                source_file_id=source_file.file_id,
            ),
        ),
        standard_result={
            "result_version": "aidd.sciminer/result.v2",
            "artifacts": {
                "properties": {
                    "type": "molecule_table@1",
                    "name": "RDKit molecular properties",
                    "files": {
                        "table_file": _standard_output_file_ref(
                            table_filename,
                            table_content,
                            "text/csv",
                        ),
                        "metadata_json": _standard_output_file_ref(
                            metadata_filename,
                            metadata_content,
                            "application/json",
                        ),
                    },
                    "metadata": metadata,
                },
                "report": {
                    "type": "run_report@1",
                    "name": "RDKit properties report",
                    "files": {
                        "report_json": _standard_output_file_ref(
                            report_filename,
                            report_content,
                            "application/json",
                        )
                    },
                    "metadata": {"source_task_id": metadata["source_task_id"]},
                },
            },
            "relations": [{"from": "report", "to": "properties", "type": "describes"}],
            "summary": {
                "property_table": "properties",
                "row_count": metadata["row_count"],
                "valid_molecule_count": metadata["valid_molecule_count"],
                "invalid_molecule_count": metadata["invalid_molecule_count"],
            },
        },
    )


def _rdkit_properties_csv_content(
    csv_path: Path,
    *,
    smiles_field: str,
    molecule_id_field: str,
    backend: Any,
) -> tuple[bytes, dict[str, Any]]:
    text = csv_path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValidationException("RDKit properties 输入 CSV 缺少表头")
    fieldnames = list(reader.fieldnames)
    smiles_column = _resolve_csv_column(fieldnames, smiles_field, fallback="smiles")
    if smiles_column is None:
        raise ValidationException("RDKit properties 输入 CSV 缺少 SMILES 列")
    molecule_id_column = _resolve_molecule_id_column(fieldnames, molecule_id_field)
    output_fieldnames = [
        *fieldnames,
        *[column for column in _RDKIT_PROPERTY_COLUMNS if column not in fieldnames],
        "rdkit_status",
    ]
    rows = list(reader)
    valid_count = 0
    invalid_count = 0
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=output_fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        output_row = dict(row)
        smiles = str(row.get(smiles_column) or "").strip()
        molecule = backend.molecule_from_smiles(smiles) if smiles else None
        if molecule is None:
            invalid_count += 1
            for column in _RDKIT_PROPERTY_COLUMNS:
                output_row[column] = ""
            output_row["rdkit_status"] = "invalid_smiles"
            writer.writerow(output_row)
            continue
        descriptors = backend.descriptors(molecule)
        valid_count += 1
        for column in _RDKIT_PROPERTY_COLUMNS:
            output_row[column] = _format_rdkit_property(descriptors[column])
        output_row["rdkit_status"] = "ok"
        writer.writerow(output_row)

    metadata = {
        "molecule_id_field": molecule_id_column,
        "smiles_field": smiles_column,
        "row_count": len(rows),
        "valid_molecule_count": valid_count,
        "invalid_molecule_count": invalid_count,
        "property_columns": list(_RDKIT_PROPERTY_COLUMNS),
        "backend_name": str(backend.name),
        "backend_version": str(backend.version),
    }
    return output.getvalue().encode("utf-8"), metadata


def _resolve_csv_column(fieldnames: list[str], preferred: str, *, fallback: str) -> str | None:
    if preferred and preferred in fieldnames:
        return preferred
    lowered = {field.lower(): field for field in fieldnames}
    return lowered.get(preferred.lower()) or lowered.get(fallback.lower())


def _resolve_molecule_id_column(fieldnames: list[str], preferred: str) -> str:
    if preferred and preferred in fieldnames:
        return preferred
    lowered = {field.lower(): field for field in fieldnames}
    for candidate in ("molecule_id", "id", "name", "smiles"):
        if candidate in lowered:
            return lowered[candidate]
    return fieldnames[0]


def _format_rdkit_property(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{value:.4f}"


def _lipinski_violations(values: dict[str, float | int]) -> int:
    checks = (
        values["molecular_weight"] > 500,
        values["logp"] > 5,
        values["hbd"] > 5,
        values["hba"] > 10,
    )
    return sum(1 for failed in checks if failed)


# ======================================================================
# 数据库查询工具（从 CSV / PDB 输入提取参数，调用 database_tools）
# ======================================================================


def _read_smiles_from_csv(csv_path: Path) -> list[str]:
    """从 SMILES CSV 文件中提取 SMILES 列表。"""
    text = csv_path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    smiles_values: list[str] = []
    for row in reader:
        smiles = (row.get("SMILES") or row.get("smiles") or "").strip()
        if smiles:
            smiles_values.append(smiles)
    return smiles_values


async def _run_query_chembl_tool(files: dict[str, BuiltinToolFile]) -> BuiltinToolResult:
    """builtin-query-chembl: 从 SMILES CSV 提取分子，查询 ChEMBL。"""
    from app.agents.aidd.database_tools import query_chembl as _query_chembl
    from app.config import settings as _settings

    if not _settings.ENABLE_DATABASE_TOOLS:
        raise ValidationException("数据库查询工具已禁用")

    csv_file = files.get("smiles_csv")
    smiles_list = _read_smiles_from_csv(csv_file.path) if csv_file else []
    if not smiles_list:
        raise ValidationException("query_chembl 需要 smiles_csv 输入文件")

    result = await _query_chembl(smiles=smiles_list[0])
    return BuiltinToolResult(
        outputs=(
            BuiltinToolOutput(semantic_type="database_query_result", data=result),
        )
    )


async def _run_query_pubchem_tool(files: dict[str, BuiltinToolFile]) -> BuiltinToolResult:
    """builtin-query-pubchem: 从 SMILES CSV 提取分子，查询 PubChem。"""
    from app.agents.aidd.database_tools import query_pubchem as _query_pubchem
    from app.config import settings as _settings

    if not _settings.ENABLE_DATABASE_TOOLS:
        raise ValidationException("数据库查询工具已禁用")

    csv_file = files.get("smiles_csv")
    smiles_list = _read_smiles_from_csv(csv_file.path) if csv_file else []
    if not smiles_list:
        raise ValidationException("query_pubchem 需要 smiles_csv 输入文件")

    result = await _query_pubchem(smiles=smiles_list[0])
    return BuiltinToolResult(
        outputs=(
            BuiltinToolOutput(semantic_type="database_query_result", data=result),
        )
    )


async def _run_query_pdbbind_tool(files: dict[str, BuiltinToolFile]) -> BuiltinToolResult:
    """builtin-query-pdbbind: 从 PDB 文件名提取 PDB ID，查询 PDBbind。"""
    from app.agents.aidd.database_tools import query_pdbbind as _query_pdbbind
    from app.config import settings as _settings

    if not _settings.ENABLE_DATABASE_TOOLS:
        raise ValidationException("数据库查询工具已禁用")

    protein_file = files.get("protein_pdb")
    ligand_file = files.get("ligand_pdb")

    pdb_id: str | None = None
    if protein_file:
        stem = Path(protein_file.filename).stem
        # 尝试提取 4 字符 PDB ID
        match = re.search(r"(\d[A-Za-z\d]{3})", stem)
        pdb_id = match.group(1) if match else stem[:4]

    ligand_name: str | None = None
    if ligand_file:
        ligand_name = Path(ligand_file.filename).stem

    result = await _query_pdbbind(protein_pdb_id=pdb_id, ligand_name=ligand_name)
    return BuiltinToolResult(
        outputs=(
            BuiltinToolOutput(semantic_type="database_query_result", data=result),
        )
    )


# ======================================================================
# ADMET / Toxicity / SA（SMILES CSV → 结构化报告）
# ======================================================================


def _run_admet_prediction_tool(files: dict[str, BuiltinToolFile]) -> BuiltinToolResult:
    """builtin-admet-prediction: 对 SMILES CSV 执行 ADMET 预测。"""
    csv_file = files.get("smiles_csv")
    smiles_list = _read_smiles_from_csv(csv_file.path) if csv_file else []
    if not smiles_list:
        raise ValidationException("admet_prediction 需要 smiles_csv 输入文件")

    records: list[dict[str, Any]] = []
    for smiles in smiles_list:
        records.append({
            "smiles": smiles,
            "note": "ADMET prediction via builtin tool (configure external ADMET service for real predictions)",
        })

    return BuiltinToolResult(
        artifacts=(
            BuiltinToolArtifact(
                semantic_type="admet_report",
                filename=f"{csv_file.filename.rsplit('.', 1)[0]}_admet.csv" if csv_file else "admet_report.csv",
                content=_dicts_to_csv_bytes(records),
                content_type="text/csv",
                source_file_id=csv_file.file_id if csv_file else None,
            ),
        )
    )


def _run_toxicity_prediction_tool(files: dict[str, BuiltinToolFile]) -> BuiltinToolResult:
    """builtin-toxicity-prediction: 对 SMILES CSV 执行毒性预测。"""
    csv_file = files.get("smiles_csv")
    smiles_list = _read_smiles_from_csv(csv_file.path) if csv_file else []
    if not smiles_list:
        raise ValidationException("toxicity_prediction 需要 smiles_csv 输入文件")

    records: list[dict[str, Any]] = []
    for smiles in smiles_list:
        records.append({
            "smiles": smiles,
            "note": "Toxicity prediction via builtin tool (configure external toxicity service for real predictions)",
        })

    return BuiltinToolResult(
        artifacts=(
            BuiltinToolArtifact(
                semantic_type="toxicity_report",
                filename=f"{csv_file.filename.rsplit('.', 1)[0]}_toxicity.csv" if csv_file else "toxicity_report.csv",
                content=_dicts_to_csv_bytes(records),
                content_type="text/csv",
                source_file_id=csv_file.file_id if csv_file else None,
            ),
        )
    )


def _run_synthetic_accessibility_tool(files: dict[str, BuiltinToolFile]) -> BuiltinToolResult:
    """builtin-synthetic-accessibility: 对 SMILES CSV 计算合成可及性分数。"""
    csv_file = files.get("smiles_csv")
    smiles_list = _read_smiles_from_csv(csv_file.path) if csv_file else []
    if not smiles_list:
        raise ValidationException("synthetic_accessibility 需要 smiles_csv 输入文件")

    records: list[dict[str, Any]] = []
    for smiles in smiles_list:
        records.append({
            "smiles": smiles,
            "sa_score": None,
            "note": "Synthetic accessibility via builtin tool (configure external SA predictor for real scores)",
        })

    return BuiltinToolResult(
        artifacts=(
            BuiltinToolArtifact(
                semantic_type="synthetic_accessibility",
                filename=f"{csv_file.filename.rsplit('.', 1)[0]}_sa.csv" if csv_file else "synthetic_accessibility.csv",
                content=_dicts_to_csv_bytes(records),
                content_type="text/csv",
                source_file_id=csv_file.file_id if csv_file else None,
            ),
        )
    )


# ======================================================================
# MD / Interaction（占位实现，等待对接外部服务）
# ======================================================================


def _run_molecular_dynamics_tool(files: dict[str, BuiltinToolFile]) -> BuiltinToolResult:
    """builtin-molecular-dynamics: 对蛋白-配体复合物运行分子动力学模拟。"""
    protein_file = files.get("protein_pdb")
    ligand_file = files.get("ligand_pdb")
    if not protein_file or not ligand_file:
        raise ValidationException("molecular_dynamics 需要 protein_pdb 和 ligand_pdb 输入")

    report = {
        "protein_file_id": protein_file.file_id,
        "protein_filename": protein_file.filename,
        "ligand_file_id": ligand_file.file_id,
        "ligand_filename": ligand_file.filename,
        "note": "Molecular dynamics simulation via builtin tool (configure external MD engine for real simulations)",
    }
    return BuiltinToolResult(
        outputs=(
            BuiltinToolOutput(
                semantic_type="molecular_dynamics_trajectory",
                data=report,
            ),
        )
    )


def _run_interaction_analysis_tool(files: dict[str, BuiltinToolFile]) -> BuiltinToolResult:
    """builtin-interaction-analysis: 分析蛋白-配体相互作用。"""
    protein_file = files.get("protein_pdb")
    ligand_file = files.get("ligand_pdb")
    if not protein_file or not ligand_file:
        raise ValidationException("interaction_analysis 需要 protein_pdb 和 ligand_pdb 输入")

    report = {
        "protein_file_id": protein_file.file_id,
        "protein_filename": protein_file.filename,
        "ligand_file_id": ligand_file.file_id,
        "ligand_filename": ligand_file.filename,
        "interactions": [],
        "note": "Interaction analysis via builtin tool (configure external analysis service for real predictions)",
    }
    content = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    return BuiltinToolResult(
        artifacts=(
            BuiltinToolArtifact(
                semantic_type="interaction_report",
                filename=f"{Path(ligand_file.filename).stem}_interaction.json",
                content=content,
                content_type="application/json",
                source_file_id=ligand_file.file_id,
            ),
        )
    )


# ======================================================================
# 辅助函数
# ======================================================================


def _dicts_to_csv_bytes(records: list[dict[str, Any]]) -> bytes:
    """将字典列表转换为 CSV 字节流。"""
    if not records:
        return b""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(records[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue().encode("utf-8")


# ======================================================================
# 统一分发入口
# ======================================================================


_BUILTIN_TOOL_REGISTRY: dict[str, str] = {
    "builtin-sdf-to-smiles-csv": "sdf_to_smiles_csv",
    "builtin-sdf-to-pdb": "sdf_to_pdb",
    "builtin-fetch-pdb": "fetch_pdb",
    "builtin-fetch-ligand": "fetch_ligand",
    "builtin-vina-docking": "vina_docking",
    "builtin-protein-preparation": "protein_preparation",
    "builtin-rdkit-properties": "rdkit_properties",
    "builtin-query-chembl": "query_chembl",
    "builtin-query-pubchem": "query_pubchem",
    "builtin-query-pdbbind": "query_pdbbind",
}


async def _run_sync_builtin_handler(
    handler: Callable[[dict[str, BuiltinToolFile]], BuiltinToolResult],
    files: dict[str, BuiltinToolFile],
) -> BuiltinToolResult:
    """在线程中执行同步内置工具，避免阻塞异步任务执行器。"""
    return await asyncio.to_thread(handler, files)


async def run_builtin_tool(
    tool_slug: str,
    files: dict[str, BuiltinToolFile],
    params: dict[str, Any] | None = None,
) -> BuiltinToolResult:
    if tool_slug in PLACEHOLDER_AIDD_TOOL_SLUGS:
        raise ValidationException(f"内置能力尚未接入真实执行引擎: {tool_slug}")

    handler_key = _BUILTIN_TOOL_REGISTRY.get(tool_slug)
    if handler_key is None:
        raise ValidationException(f"未知内置智能体工具: {tool_slug}")

    if handler_key == "sdf_to_smiles_csv":
        return await _run_sync_builtin_handler(_run_sdf_to_smiles_csv_tool, files)
    if handler_key == "sdf_to_pdb":
        return await _run_sync_builtin_handler(_run_sdf_to_pdb_tool, files)
    if handler_key == "fetch_pdb":
        return await _run_fetch_pdb_tool(files, params)
    if handler_key == "fetch_ligand":
        return await _run_fetch_ligand_tool(files, params)
    if handler_key == "vina_docking":
        return await _run_sync_builtin_handler(_run_vina_docking_tool, files)
    if handler_key == "protein_preparation":
        return await asyncio.to_thread(_run_protein_preparation_tool, files, params)
    if handler_key == "rdkit_properties":
        return await asyncio.to_thread(_run_rdkit_properties_tool, files, params)
    if handler_key == "query_chembl":
        return await _run_query_chembl_tool(files)
    if handler_key == "query_pubchem":
        return await _run_query_pubchem_tool(files)
    if handler_key == "query_pdbbind":
        return await _run_query_pdbbind_tool(files)
    if handler_key == "admet_prediction":
        return await _run_sync_builtin_handler(_run_admet_prediction_tool, files)
    if handler_key == "toxicity_prediction":
        return await _run_sync_builtin_handler(_run_toxicity_prediction_tool, files)
    if handler_key == "synthetic_accessibility":
        return await _run_sync_builtin_handler(_run_synthetic_accessibility_tool, files)
    if handler_key == "molecular_dynamics":
        return await _run_sync_builtin_handler(_run_molecular_dynamics_tool, files)
    if handler_key == "interaction_analysis":
        return await _run_sync_builtin_handler(_run_interaction_analysis_tool, files)

    raise ValidationException(f"未实现的内置工具处理器: {tool_slug}")
