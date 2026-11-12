"""把 legacy 镜像产出的分子表规范成下游可读的 CSV。

背景（`docs/26`）：Pocket2Mol 等早期镜像把 `artifacts/SMILES.txt` 原样当作
`molecule_table` 的 `table_file` 上报——没有表头、后缀是 `.txt`。平台自己的
下游工具（RDKit 性质、MSIGN 亲和力、AutoDock Vina 对接）都按「CSV 且有
`smiles` 列」读取，于是同一份生成结果到了第二个环节就断掉。

规范化的位置选在**标准产物落库时**而不是各消费方：
- 消费方是 N 个镜像，改 N 处，而且每加一个模型就要再改一次；
- 落库只有一处，产物一经写入就是下游看到的唯一形态。

规范化只做「补表头 + 转 CSV」，不改分子内容、不丢行。
"""

from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.artifact_standards.registry import (
    StandardArtifactRegistryError,
    get_standard_artifact_spec,
    parse_standard_ref,
)
from app.execution.result_parser import ParsedStandardArtifact
from app.files.content import read_file_bytes
from app.files.writer import store_file_bytes
from app.models.files import File as FileModel, FileSourceType
from app.models.tasks import Task

MOLECULE_TABLE_REF = "molecule_table"
SMILES_COLUMN = "smiles"

# 首行出现这些词就认为「已经有表头」，原样放行。
_SMILES_HEADER_TOKENS = frozenset(
    {"smiles", "smile", "smi", "canonical_smiles", "isomeric_smiles"}
)


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def is_headerless_smiles_table(text: str) -> bool:
    """判断一份表格内容是不是「无表头的 SMILES 列表」。

    判据只有一条：首行既没有分隔符（`,` / `\\t` / `;`），本身也不是列名。
    有表头的表格必然含分隔符，因此不会误判；后缀不参与判断，因为
    `SMILES.txt` 与 `molecules.csv` 都可能是无表头的。
    """

    head = _first_line(text)
    if not head:
        return False
    if any(sep in head for sep in (",", "\t", ";")):
        return False
    return head.lower() not in _SMILES_HEADER_TOKENS


def smiles_rows(text: str) -> list[str]:
    """从无表头内容里取每行的 SMILES（首列），跳过空行与注释行。"""

    rows: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        rows.append(stripped.split()[0])
    return rows


def to_smiles_csv(text: str) -> str:
    """把无表头的 SMILES 列表转成带 `smiles` 列的 CSV 文本。"""

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([SMILES_COLUMN])
    for smiles in smiles_rows(text):
        writer.writerow([smiles])
    return buffer.getvalue()


def csv_filename(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return f"{stem}.csv"


def is_molecule_table(artifact: ParsedStandardArtifact) -> bool:
    try:
        return parse_standard_ref(artifact.type).type == MOLECULE_TABLE_REF
    except StandardArtifactRegistryError:
        return False


def primary_role_of(artifact: ParsedStandardArtifact) -> str | None:
    try:
        spec = get_standard_artifact_spec(parse_standard_ref(artifact.type).ref)
    except StandardArtifactRegistryError:
        return None
    return next((role.role for role in spec.file_roles if role.primary), None)


async def normalize_molecule_table_files(
    db: AsyncSession,
    *,
    task: Task,
    project_id: str,
    artifact: ParsedStandardArtifact,
    resolved_files: list[tuple[str, FileModel]],
) -> list[tuple[str, FileModel]]:
    """把 `molecule_table` 主文件的 legacy 形态规范成 CSV。

    只处理主角色（`table_file`），其它角色（`metadata_json`、结构文件）原样返回。
    原文件仍留在存储里（便于追溯），但版本只挂规范后的那一份。
    """

    if not is_molecule_table(artifact):
        return resolved_files
    primary_role = primary_role_of(artifact)
    if primary_role is None:
        return resolved_files

    updated: list[tuple[str, FileModel]] = []
    for role, file_record in resolved_files:
        if role != primary_role:
            updated.append((role, file_record))
            continue
        normalized = await _normalize_record(
            db,
            task=task,
            project_id=project_id,
            file_record=file_record,
        )
        updated.append((role, normalized if normalized is not None else file_record))
    return updated


async def _normalize_record(
    db: AsyncSession,
    *,
    task: Task,
    project_id: str,
    file_record: FileModel,
) -> FileModel | None:
    try:
        content = await read_file_bytes(file_record)
    except Exception:  # noqa: BLE001 - 读不到就保持原样；规范化不能让落库失败
        return None
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    if not is_headerless_smiles_table(text):
        return None
    if not smiles_rows(text):
        return None

    file_meta: dict[str, Any] = dict(file_record.file_meta or {})
    file_meta.update(
        {
            "normalized_from_file_id": str(file_record.id),
            "normalized_from_filename": file_record.filename,
            "normalization": "headerless-smiles-to-csv",
        }
    )
    return await store_file_bytes(
        db,
        content=to_smiles_csv(text).encode("utf-8"),
        filename=csv_filename(file_record.filename),
        content_type="text/csv",
        source_type=FileSourceType.TOOL_OUTPUT,
        owner_id=file_record.owner_id or task.user_id,
        project_id=project_id,
        file_meta=file_meta,
    )
