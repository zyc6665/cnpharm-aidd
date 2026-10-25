"""RDKit-backed molecule identity, descriptors and fingerprints (docs/04 §7.1, §5.7).

单一真值源约定：

* **身份**用 InChIKey（``inchikey_of``），不用 SMILES —— 同一分子的 SMILES 可以有
  多种写法（芳香性、互变异构、质子化态），InChIKey 是标准化后的结构标识。
* **性质**（logP/TPSA/HBD/HBA/RotB/QED）是派生数据，允许重算覆盖。
* **指纹**只存 ``molecule_fingerprints``（docs/04 §7.1 v1.2 已废弃
  ``compound.fingerprint``），本模块只负责计算，不负责落库。

RDKit 是 ``backend/requirements.txt`` 的硬依赖（``rdkit==2024.9.6``），但为了让
「没有 RDKit 的开发机」仍能启动平台，本模块全部采用延迟导入并在缺失时抛
``ValidationException``，由 API 层转成 503 语义的可读错误。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.common.exceptions import ValidationException

#: ECFP4 位宽。2048 bit = 256 字节，与 docs/04 §5.7 一致。
ECFP4_BITS = 2048
#: ECFP4 半径（Morgan 算法的 radius=2）。
ECFP4_RADIUS = 2

#: ``props`` 里落库的性质键，与 docs/04 §7.1 一一对应。
DESCRIPTOR_KEYS = ("logP", "TPSA", "HBD", "HBA", "RotB", "QED")


@dataclass(frozen=True)
class MoleculeDescriptor:
    """一次解析得到的分子身份与性质快照。"""

    canonical_smiles: str
    inchikey: str
    mol_formula: str | None
    mol_weight: float | None
    props: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FingerprintPayload:
    """指纹字节串与生成它的 RDKit 版本。"""

    fp_ecfp4: bytes
    fp_maccs: bytes
    fp_ecfp4_bits: int
    rdkit_version: str


def _require_rdkit() -> tuple[Any, Any, Any, Any]:
    """Return ``(Chem, Descriptors, AllChem, rdBase)`` or fail with a readable error."""
    try:
        from rdkit import Chem, rdBase
        from rdkit.Chem import AllChem, Descriptors
    except Exception as exc:  # pragma: no cover - 依赖缺失路径
        raise ValidationException("服务器未安装 RDKit，无法解析分子结构") from exc
    return Chem, Descriptors, AllChem, rdBase


def _molecule_from_smiles(smiles: str) -> Any:
    Chem, _, _, _ = _require_rdkit()
    text = (smiles or "").strip()
    if not text:
        raise ValidationException("SMILES 不能为空")
    molecule = Chem.MolFromSmiles(text)
    if molecule is None:
        raise ValidationException(f"SMILES 无法解析: {text[:80]}")
    return molecule


def inchikey_of(smiles: str) -> str:
    """Compute the InChIKey for a SMILES string (raises ``ValidationException``)."""
    Chem, _, _, _ = _require_rdkit()
    molecule = _molecule_from_smiles(smiles)
    try:
        from rdkit.Chem import inchi

        key = str(inchi.MolToInchiKey(molecule) or "").strip()
    except Exception as exc:  # pragma: no cover - InChI 后端异常
        raise ValidationException("InChIKey 计算失败，请检查分子结构是否完整") from exc
    if not key:
        raise ValidationException("InChIKey 计算为空，分子结构可能不完整")
    return key


def describe_smiles(smiles: str) -> MoleculeDescriptor:
    """Parse a SMILES once and return identity + the six LR properties."""
    Chem, Descriptors, _, _ = _require_rdkit()
    molecule = _molecule_from_smiles(smiles)
    try:
        from rdkit.Chem import inchi
        from rdkit.Chem import QED

        inchikey = str(inchi.MolToInchiKey(molecule) or "").strip()
    except Exception as exc:  # pragma: no cover
        raise ValidationException("InChIKey 计算失败，请检查分子结构是否完整") from exc
    if not inchikey:
        raise ValidationException("InChIKey 计算为空，分子结构可能不完整")

    props: dict[str, Any] = {}
    try:
        props["logP"] = round(float(Descriptors.MolLogP(molecule)), 4)
        props["TPSA"] = round(float(Descriptors.TPSA(molecule)), 4)
        props["HBD"] = int(Descriptors.NumHDonors(molecule))
        props["HBA"] = int(Descriptors.NumHAcceptors(molecule))
        props["RotB"] = int(Descriptors.NumRotatableBonds(molecule))
        props["QED"] = round(float(QED.qed(molecule)), 4)
    except Exception:  # pragma: no cover - 个别结构会让某个描述符失败
        # 性质是派生数据，单项失败不该让整个导入失败；缺的键留空由前端显示「—」。
        pass

    try:
        mol_formula = str(Descriptors.rdMolDescriptors.CalcMolFormula(molecule))
    except Exception:  # pragma: no cover
        mol_formula = None
    try:
        mol_weight = round(float(Descriptors.MolWt(molecule)), 3)
    except Exception:  # pragma: no cover
        mol_weight = None

    return MoleculeDescriptor(
        canonical_smiles=str(Chem.MolToSmiles(molecule, canonical=True)),
        inchikey=inchikey,
        mol_formula=mol_formula,
        mol_weight=mol_weight,
        props=props,
    )


def fingerprints_of(smiles: str) -> FingerprintPayload:
    """Compute ECFP4 (2048 bit) and MACCS (167 bit) fingerprints."""
    _, _, AllChem, rdBase = _require_rdkit()
    molecule = _molecule_from_smiles(smiles)

    try:
        ecfp4 = AllChem.GetMorganFingerprintAsBitVect(
            molecule, ECFP4_RADIUS, nBits=ECFP4_BITS
        )
        maccs = AllChem.GetMACCSKeysFingerprint(molecule)
    except Exception as exc:  # pragma: no cover
        raise ValidationException("分子指纹计算失败") from exc

    return FingerprintPayload(
        fp_ecfp4=_pack_bits(ecfp4),
        fp_maccs=_pack_bits(maccs),
        fp_ecfp4_bits=ECFP4_BITS,
        rdkit_version=str(rdBase.rdkitVersion),
    )


def _pack_bits(fingerprint: Any) -> bytes:
    """Pack an ``ExplicitBitVect`` into the on-disk byte representation.

    ``ToBitString()`` 返回 ``"0101..."`` 字符串，每 8 个字符打包成 1 字节，与
    docs/04 §5.7 的 ``bytea``（ECFP4 256 字节 / MACCS 21 字节）一致。用位串打包
    而不是 ``ToBitString()`` 直接存字符串，是为了省 7/8 的存储并让 Tanimoto 可以
    直接对字节做 popcount。
    """
    bit_string = fingerprint.ToBitString()
    packed = bytearray()
    for index in range(0, len(bit_string), 8):
        chunk = bit_string[index : index + 8].ljust(8, "0")
        packed.append(int(chunk, 2))
    return bytes(packed)


def tanimoto_from_bytes(left: bytes, right: bytes) -> float:
    """Tanimoto similarity between two packed fingerprints (docs/04 §5.7 step 3)."""
    if not left or not right:
        return 0.0
    length = min(len(left), len(right))
    intersection = 0
    union = 0
    for index in range(length):
        a = left[index]
        b = right[index]
        intersection += bin(a & b).count("1")
        union += bin(a | b).count("1")
    for index in range(length, len(left)):
        union += bin(left[index]).count("1")
    for index in range(length, len(right)):
        union += bin(right[index]).count("1")
    if union == 0:
        return 0.0
    return round(intersection / union, 6)
