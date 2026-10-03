"""Open-source protein preparation with PDBFixer, OpenMM and Open Babel."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas.protein_preparation import ProteinPreparationOptions


WATER_RESIDUES = {"HOH", "WAT", "H2O"}
METAL_RESIDUES = {
    "AG", "AL", "AU", "BA", "CA", "CD", "CO", "CR", "CU", "FE", "HG", "K",
    "LI", "MG", "MN", "NA", "NI", "PB", "PT", "ZN",
}
COFACTOR_RESIDUES = {
    "ATP", "ADP", "AMP", "FAD", "FMN", "NAD", "NADH", "NAG", "SAM", "HEM",
    "PLP", "COA", "GDP", "GTP", "UDP", "UTP",
}


class ProteinPreparationError(RuntimeError):
    """Raised when protein preparation cannot produce a requested output."""


class OpenSourcePreparationUnavailable(ProteinPreparationError):
    """Raised when the optional open-source protein repair stack is unavailable."""


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
    advanced_options = advanced_options if isinstance(advanced_options, dict) else {}
    warnings: list[str] = []
    preparation_engine = "pdbfixer-openmm"
    fallback_reason: str | None = None
    executed_steps: dict[str, bool] = {}

    try:
        executed_steps, open_source_warnings = _run_open_source_preparation(
            source_path,
            prepared_pdb,
            options,
            advanced_options=advanced_options,
            output_dir=output_dir,
        )
        warnings.extend(open_source_warnings)
    except OpenSourcePreparationUnavailable as exc:
        preparation_engine = "open-source-basic-fallback"
        fallback_reason = str(exc)
        _write_prepared_pdb(
            source_path,
            prepared_pdb,
            remove_water=options.remove_water,
            keep_metals=options.keep_metals,
            keep_cofactors=options.keep_cofactors,
            remove_non_target_ligands=options.remove_non_target_ligands,
        )
        warnings.extend(_local_preparation_warnings(options))
        warnings.insert(0, fallback_reason)
        executed_steps = {
            "remove_small_molecules": True,
            "fill_missing_side_chains": False,
            "fill_missing_loops": False,
            "add_hydrogens": False,
            "modify_protonation_at_ph": False,
            "optimize_hydrogen_bonding": False,
            "energy_minimization": False,
        }
    except Exception as exc:
        raise ProteinPreparationError(f"开源蛋白预处理失败: {exc}") from exc

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
        "status": "degraded" if fallback_reason else "prepared",
        "engine": preparation_engine,
        "implementation": "open-source",
        "fallback_reason": fallback_reason,
        "source_path": str(source_path),
        "options": options.model_dump(),
        "advanced_options": advanced_options or {},
        "steps": {
            "fill_missing_side_chains": executed_steps.get("fill_missing_side_chains", False),
            "fill_missing_loops": executed_steps.get("fill_missing_loops", False),
            "add_hydrogens": executed_steps.get("add_hydrogens", False),
            "modify_protonation_at_ph": options.ph,
            "optimize_hydrogen_bonding": executed_steps.get("optimize_hydrogen_bonding", False),
            "remove_small_molecules": executed_steps.get("remove_small_molecules", False),
            "energy_minimization": executed_steps.get("energy_minimization", False),
        },
        "requested_steps": {
            "fill_missing_side_chains": options.fill_missing_side_chains,
            "fill_missing_loops": options.fill_missing_loops,
            "add_hydrogens": options.add_hydrogens,
            "modify_protonation_at_ph": options.add_hydrogens,
            "optimize_hydrogen_bonding": options.optimize_hydrogen_bonding,
            "remove_small_molecules": options.remove_non_target_ligands,
            "energy_minimization": options.energy_minimization,
        },
        "warnings": warnings,
        "files": {role: str(file.path) for role, file in files.items()},
    }
    return ProteinPreparationResult(files=files, report=report, warnings=warnings)


def _run_open_source_preparation(
    source_path: Path,
    prepared_pdb: Path,
    options: ProteinPreparationOptions,
    *,
    advanced_options: dict[str, Any],
    output_dir: Path,
) -> None:
    try:
        from pdbfixer import PDBFixer
    except ImportError as exc:
        raise OpenSourcePreparationUnavailable(
            "未安装开源蛋白修复依赖 PDBFixer，请安装 backend/requirements.txt"
        ) from exc

    filtered_source = output_dir / "filtered_input.pdb"
    _write_prepared_pdb(
        source_path,
        filtered_source,
        remove_water=options.remove_water,
        keep_metals=options.keep_metals,
        keep_cofactors=options.keep_cofactors,
        remove_non_target_ligands=options.remove_non_target_ligands,
    )
    fixer = PDBFixer(filename=str(filtered_source))
    fixer.findMissingResidues()
    if not options.fill_missing_loops:
        fixer.missingResidues = {}
    fixer.findNonstandardResidues()
    fixer.replaceNonstandardResidues()
    fixer.findMissingAtoms()
    if options.fill_missing_side_chains or options.fill_missing_loops:
        fixer.addMissingAtoms()

    executed_steps = {
        "fill_missing_side_chains": options.fill_missing_side_chains,
        "fill_missing_loops": options.fill_missing_loops,
        "add_hydrogens": False,
        "modify_protonation_at_ph": False,
        "optimize_hydrogen_bonding": False,
        "remove_small_molecules": True,
        "energy_minimization": False,
    }
    warnings: list[str] = []
    if options.add_hydrogens:
        fixer.addMissingHydrogens(options.ph)
        executed_steps["add_hydrogens"] = True
        executed_steps["modify_protonation_at_ph"] = True
    if options.optimize_hydrogen_bonding:
        warnings.append(
            "PDBFixer/OpenMM 未提供独立的氢键网络重定向步骤，当前通过质子化与能量最小化进行局部优化"
        )

    positions = fixer.positions
    if options.energy_minimization:
        try:
            positions = _minimize_openmm(fixer.topology, positions)
            executed_steps["energy_minimization"] = True
            executed_steps["optimize_hydrogen_bonding"] = options.optimize_hydrogen_bonding
        except OpenSourcePreparationUnavailable as exc:
            warnings.append(str(exc))
        except Exception as exc:
            warnings.append(f"OpenMM 能量最小化未执行: {exc}")

    try:
        from openmm.app import PDBFile
    except ImportError as exc:
        raise OpenSourcePreparationUnavailable(
            "未安装开源结构写出依赖 OpenMM，请安装 backend/requirements.txt"
        ) from exc

    with prepared_pdb.open("w", encoding="utf-8") as handle:
        PDBFile.writeFile(fixer.topology, positions, handle, keepIds=True)
    return executed_steps, warnings


def _minimize_openmm(topology: Any, positions: Any) -> Any:
    try:
        from openmm import LangevinIntegrator, unit
        from openmm.app import ForceField, NoCutoff, Simulation
    except ImportError as exc:
        raise OpenSourcePreparationUnavailable(
            "未安装开源能量优化依赖 OpenMM，请安装 backend/requirements.txt"
        ) from exc

    forcefield = ForceField("amber14-all.xml")
    system = forcefield.createSystem(
        topology,
        nonbondedMethod=NoCutoff,
        constraints=None,
    )
    integrator = LangevinIntegrator(
        300 * unit.kelvin,
        1 / unit.picosecond,
        0.002 * unit.picoseconds,
    )
    simulation = Simulation(topology, system, integrator)
    simulation.context.setPositions(positions)
    simulation.minimizeEnergy(maxIterations=500)
    return simulation.context.getState(getPositions=True).getPositions()


def _local_preparation_warnings(options: ProteinPreparationOptions) -> list[str]:
    warnings: list[str] = []
    if options.fill_missing_side_chains:
        warnings.append("基础清理兜底未执行缺失侧链重建")
    if options.fill_missing_loops:
        warnings.append("基础清理兜底未执行缺失 loop 重建")
    if options.add_hydrogens:
        warnings.append("基础清理兜底未执行氢原子补全")
    if options.optimize_hydrogen_bonding:
        warnings.append("基础清理兜底未执行氢键网络优化")
    if options.energy_minimization:
        warnings.append("基础清理兜底未执行能量最小化")
    return warnings


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


def _write_prepared_pdb(
    source_path: Path,
    target_path: Path,
    *,
    remove_water: bool,
    keep_metals: bool,
    keep_cofactors: bool,
    remove_non_target_ligands: bool,
) -> None:
    source_lines = source_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    kept_lines = [
        line
        for line in source_lines
        if not _is_removed_line(
            line,
            remove_water=remove_water,
            keep_metals=keep_metals,
            keep_cofactors=keep_cofactors,
            remove_non_target_ligands=remove_non_target_ligands,
        )
    ]
    target_path.write_text("\n".join(kept_lines).rstrip() + "\n", encoding="utf-8")


def _is_removed_water_line(line: str, remove_water: bool) -> bool:
    if not remove_water or not line.startswith(("ATOM", "HETATM")):
        return False
    residue_name = line[17:20].strip().upper() if len(line) >= 20 else ""
    return residue_name in WATER_RESIDUES


def _is_removed_line(
    line: str,
    *,
    remove_water: bool,
    keep_metals: bool,
    keep_cofactors: bool,
    remove_non_target_ligands: bool,
) -> bool:
    if _is_removed_water_line(line, remove_water):
        return True
    if not remove_non_target_ligands or not line.startswith("HETATM"):
        return False
    residue_name = line[17:20].strip().upper() if len(line) >= 20 else ""
    if keep_metals and residue_name in METAL_RESIDUES:
        return False
    if keep_cofactors and residue_name in COFACTOR_RESIDUES:
        return False
    return True
