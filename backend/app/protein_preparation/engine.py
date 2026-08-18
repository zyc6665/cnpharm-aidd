"""Protein preparation engine.

The first version keeps deterministic, local transformations in this module and
delegates scientific format conversion to an external executable when requested.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas.protein_preparation import ProteinPreparationOptions


WATER_RESIDUES = {"HOH", "WAT", "H2O"}


class ProteinPreparationError(RuntimeError):
    """Raised when protein preparation cannot produce a requested output."""


@dataclass(frozen=True)
class PreparedProteinFile:
    role: str
    path: Path
    content_type: str


@dataclass(frozen=True)
class ProteinPreparationResult:
    files: dict[str, PreparedProteinFile]
    report: dict[str, Any]
    warnings: list[str]


def prepare_protein(
    source_path: Path,
    options: ProteinPreparationOptions,
    *,
    advanced_options: dict[str, Any] | None = None,
    output_dir: Path,
) -> ProteinPreparationResult:
    if not source_path.exists():
        raise ProteinPreparationError(f"蛋白结构文件不存在: {source_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    requested_formats = set(options.output_formats)
    prepared_pdb = output_dir / "prepared.pdb"
    _write_prepared_pdb(source_path, prepared_pdb, remove_water=options.remove_water)

    files: dict[str, PreparedProteinFile] = {}
    if "prepared_pdb" in requested_formats:
        files["prepared_pdb"] = PreparedProteinFile(
            role="prepared_pdb",
            path=prepared_pdb,
            content_type="chemical/x-pdb",
        )

    if "receptor_pdbqt" in requested_formats:
        receptor_pdbqt = output_dir / "receptor.pdbqt"
        convert_prepared_pdb_to_pdbqt(prepared_pdb, receptor_pdbqt, rigid=True)
        files["receptor_pdbqt"] = PreparedProteinFile(
            role="receptor_pdbqt",
            path=receptor_pdbqt,
            content_type="chemical/x-pdbqt",
        )

    report = {
        "status": "prepared",
        "engine": "sciminer-local-v1",
        "source_path": str(source_path),
        "options": options.model_dump(),
        "advanced_options": advanced_options or {},
        "files": {role: str(file.path) for role, file in files.items()},
    }
    return ProteinPreparationResult(files=files, report=report, warnings=[])


def convert_prepared_pdb_to_pdbqt(source_path: Path, target_path: Path, *, rigid: bool) -> None:
    obabel = shutil.which("obabel")
    if not obabel:
        raise ProteinPreparationError("蛋白制备需要 obabel 将 prepared PDB 转为 receptor PDBQT")

    argv = [obabel, "-ipdb", str(source_path), "-opdbqt", "-O", str(target_path)]
    if rigid:
        argv.append("-xr")

    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not target_path.exists():
        detail = (result.stderr or result.stdout or "OpenBabel PDBQT 转换失败").strip()
        raise ProteinPreparationError(f"蛋白 PDBQT 转换失败: {detail}")


def _write_prepared_pdb(source_path: Path, target_path: Path, *, remove_water: bool) -> None:
    source_lines = source_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    kept_lines = [line for line in source_lines if not _is_removed_water_line(line, remove_water)]
    target_path.write_text("\n".join(kept_lines).rstrip() + "\n", encoding="utf-8")


def _is_removed_water_line(line: str, remove_water: bool) -> bool:
    if not remove_water or not line.startswith(("ATOM", "HETATM")):
        return False
    residue_name = line[17:20].strip().upper() if len(line) >= 20 else ""
    return residue_name in WATER_RESIDUES

