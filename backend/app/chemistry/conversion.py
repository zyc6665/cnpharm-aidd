"""Shared chemistry file conversion helpers."""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.common.exceptions import ValidationException


def normalize_pdb_block(pdb_text: str) -> str:
    """Normalize toolkit-generated PDB text and require atom records."""
    normalized = pdb_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValidationException("SDF 转 PDB 结果为空")
    if "HETATM" not in normalized and "ATOM" not in normalized:
        raise ValidationException("SDF 转 PDB 结果缺少原子记录")
    if not normalized.endswith("END"):
        normalized = f"{normalized}\nEND"
    return f"{normalized}\n"


def first_sdf_record_bytes(sdf_content: bytes) -> bytes:
    """Return the first SDF record with the required three-line header."""
    first_record = sdf_content.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"$$$$", 1)[0]
    if not first_record.strip():
        raise ValidationException("SDF 文件为空")

    lines = first_record.split(b"\n")
    counts_index = next((index for index, line in enumerate(lines) if b"V2000" in line or b"V3000" in line), None)
    if counts_index is None:
        return first_record.rstrip() + b"\n$$$$\n"

    header_lines = lines[:counts_index]
    body_lines = lines[counts_index:]
    if len(header_lines) > 3:
        header_lines = header_lines[-3:]
    elif len(header_lines) < 3:
        header_lines = ([b""] * (3 - len(header_lines))) + header_lines

    return b"\n".join(header_lines + body_lines).rstrip() + b"\n$$$$\n"


def convert_sdf_to_pdb_with_rdkit(sdf_content: bytes) -> str | None:
    """Convert the first valid SDF molecule with RDKit when available."""
    try:
        from rdkit import Chem
    except ImportError:
        return None

    normalized_sdf = first_sdf_record_bytes(sdf_content)
    supplier = Chem.ForwardSDMolSupplier(
        io.BytesIO(normalized_sdf),
        sanitize=False,
        removeHs=False,
        strictParsing=False,
    )
    for mol in supplier:
        if mol is None or mol.GetNumAtoms() == 0:
            continue
        return normalize_pdb_block(Chem.MolToPDBBlock(mol))

    raise ValidationException("RDKit 无法从 SDF 中读取有效分子")


def convert_sdf_to_pdb_with_openbabel(sdf_content: bytes) -> str | None:
    """Convert the first SDF molecule with OpenBabel when available."""
    obabel = shutil.which("obabel")
    if not obabel:
        return None

    with tempfile.TemporaryDirectory(prefix="sdf-to-pdb-") as tmp_dir:
        input_path = Path(tmp_dir) / "ligand.sdf"
        output_path = Path(tmp_dir) / "ligand.pdb"
        input_path.write_bytes(first_sdf_record_bytes(sdf_content))

        result = subprocess.run(
            [obabel, "-isdf", str(input_path), "-opdb", "-O", str(output_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "OpenBabel 转换失败").strip()
            raise ValidationException(f"OpenBabel 转换失败: {detail}")
        if not output_path.exists():
            raise ValidationException("OpenBabel 未生成 PDB 文件")
        return normalize_pdb_block(output_path.read_text(encoding="utf-8", errors="replace"))


def convert_sdf_to_pdb_with_toolkit(sdf_content: bytes) -> tuple[str, str]:
    """Convert the first valid SDF molecule to PDB with RDKit or OpenBabel."""
    rdkit_pdb = convert_sdf_to_pdb_with_rdkit(sdf_content)
    if rdkit_pdb is not None:
        return rdkit_pdb, "rdkit"

    openbabel_pdb = convert_sdf_to_pdb_with_openbabel(sdf_content)
    if openbabel_pdb is not None:
        return openbabel_pdb, "openbabel"

    raise ValidationException("后端未安装 RDKit 或 OpenBabel，无法进行可靠的 SDF 到 PDB 转换")


_TWO_LETTER_SMILES_ATOMS = {
    "Ac",
    "Ag",
    "Al",
    "Am",
    "Ar",
    "As",
    "At",
    "Au",
    "Ba",
    "Be",
    "Bi",
    "Bk",
    "Br",
    "Ca",
    "Cd",
    "Ce",
    "Cf",
    "Cl",
    "Cm",
    "Co",
    "Cr",
    "Cs",
    "Cu",
    "Dy",
    "Er",
    "Eu",
    "Fe",
    "Fm",
    "Fr",
    "Ga",
    "Gd",
    "Ge",
    "He",
    "Hf",
    "Hg",
    "Ho",
    "In",
    "Ir",
    "Kr",
    "La",
    "Li",
    "Lr",
    "Lu",
    "Md",
    "Mg",
    "Mn",
    "Mo",
    "Na",
    "Nb",
    "Nd",
    "Ne",
    "Ni",
    "No",
    "Np",
    "Os",
    "Pa",
    "Pb",
    "Pd",
    "Pm",
    "Po",
    "Pr",
    "Pt",
    "Pu",
    "Ra",
    "Rb",
    "Re",
    "Rh",
    "Rn",
    "Ru",
    "Sb",
    "Sc",
    "Se",
    "Si",
    "Sm",
    "Sn",
    "Sr",
    "Ta",
    "Tb",
    "Tc",
    "Te",
    "Th",
    "Ti",
    "Tl",
    "Tm",
    "Xe",
    "Yb",
    "Zn",
    "Zr",
}
_ONE_LETTER_SMILES_ATOMS = set("BCFHIKNOPSUVWYbcnops")
_SMILES_PUNCTUATION = set("[]()=#-+@\\/.%:$*0123456789")


def canonicalize_smiles(smiles: str) -> str | None:
    """Return canonical SMILES for valid molecules, or None for invalid tokens."""
    token = smiles.strip()
    if not token or token.upper() == "SMILES":
        return None

    try:
        from rdkit import Chem
    except ImportError:
        return token if looks_like_smiles_token(token) else None

    molecule = Chem.MolFromSmiles(token)
    if molecule is None or molecule.GetNumAtoms() == 0:
        return None
    return Chem.MolToSmiles(molecule)


def looks_like_smiles_token(token: str) -> bool:
    """Conservative lexical fallback used when RDKit is unavailable."""
    index = 0
    atom_count = 0
    while index < len(token):
        char = token[index]
        if char == "[":
            end_index = token.find("]", index + 1)
            if end_index == -1:
                return False
            atom_count += 1
            index = end_index + 1
            continue
        pair = token[index : index + 2]
        if pair in _TWO_LETTER_SMILES_ATOMS:
            atom_count += 1
            index += 2
            continue
        if char in _ONE_LETTER_SMILES_ATOMS:
            atom_count += 1
            index += 1
            continue
        if char.isalpha():
            return False
        if char not in _SMILES_PUNCTUATION:
            return False
        index += 1
    return atom_count > 0
