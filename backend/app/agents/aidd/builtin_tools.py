"""Built-in AIDD agent tools."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.agents.aidd.outputs import parse_sdf_smiles
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
class BuiltinToolResult:
    artifacts: tuple[BuiltinToolArtifact, ...]


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


def run_builtin_tool(tool_slug: str, files: dict[str, BuiltinToolFile]) -> BuiltinToolResult:
    if tool_slug == "builtin-sdf-to-smiles-csv":
        return _run_sdf_to_smiles_csv_tool(files)
    if tool_slug == "builtin-sdf-to-pdb":
        return _run_sdf_to_pdb_tool(files)
    if tool_slug == "builtin-vina-docking":
        return _run_vina_docking_tool(files)
    raise ValidationException(f"未知内置智能体工具: {tool_slug}")
