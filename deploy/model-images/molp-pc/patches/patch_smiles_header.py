"""让 MolP-PC 镜像接受平台规范化的 ``smiles`` 小写表头。

镜像内的 ``/opt/sciminer/MolP-PC/platform_run.sh`` 自带一个内嵌的
``molp_pc_platform_runner.py``（heredoc 生成到工作目录），它对输入 CSV 的要求是
表头里必须有**大写** ``SMILES`` 列：

```python
reader = csv.DictReader(handle)
if not reader.fieldnames or "SMILES" not in reader.fieldnames:
    raise ValueError(f"Input CSV must contain a SMILES column: {csv_path}")
```

而平台从 2026-11-11 起在**落库时**把无表头 SMILES 列表规范成小写 ``smiles`` 表头的
CSV（`backend/app/services/molecule_table_normalization.py`），于是 MolP-C 一接手就
报 `Input CSV must contain a SMILES column`。

本补丁做两件事，都作用在镜像里的 `platform_run.sh` 上：

1. 把表头判据改成大小写不敏感（``smiles`` / ``smile`` / ``smi`` 任一即可）；
2. 在取到输入 CSV 之后，把首行的 smiles 列就地改名为 `SMILES`，让模型内部按原来的
   大写列名取值——不改模型代码，也不改平台对其它工具的下发格式。

用法（在 4090 上，镜像已存在）：

```bash
cd deploy/model-images/molp-pc
python3 patches/patch_smiles_header.py /path/to/platform_run.sh
cat > Dockerfile <<'EOF'
FROM 127.0.0.1:30500/aidd/compute-molp-pc@sha256:c7e5dfdc8ce1f4669aa00faef71a21a9d61c4ab78449293d9dab81c993a5f516
COPY platform_run.sh /opt/sciminer/MolP-PC/platform_run.sh
RUN chmod +x /opt/sciminer/MolP-PC/platform_run.sh
EOF
docker buildx build --push -t 127.0.0.1:30500/aidd/compute-molp-pc:1.1.2 .
```

产出镜像 digest（2026-11-11 实测）：
`sha256:af67484df115437db543f48934d106531dd07c5f319fb0497274b7aa764beb06`
"""

from __future__ import annotations

import sys
from pathlib import Path

OLD_CHECK = '''        reader = csv.DictReader(handle)
        if not reader.fieldnames or "SMILES" not in reader.fieldnames:
            raise ValueError(f"Input CSV must contain a SMILES column: {csv_path}")
        return sum(1 for _ in reader)'''

NEW_CHECK = '''        reader = csv.DictReader(handle)
        names = [name for name in (reader.fieldnames or []) if name]
        lower = [name.strip().lower() for name in names]
        if "smiles" not in lower and "smile" not in lower and "smi" not in lower:
            raise ValueError(f"Input CSV must contain a SMILES column: {csv_path}")
        return sum(1 for _ in reader)'''

HELPER = '''def _normalize_smiles_header(csv_path):
    """平台规范化后的分子表用小写 smiles 表头；本模型内部按大写 SMILES 取列。"""
    path = Path(csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return
    header = rows[0]
    renamed = False
    for index, name in enumerate(header):
        if (name or "").strip().lower() in ("smiles", "smile", "smi"):
            header[index] = "SMILES"
            renamed = True
    if not renamed:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(rows)


def main():'''

CALL_ANCHOR = "    input_csv = resolve_input_path(smiles_entry, input_dir)"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("用法: python patch_smiles_header.py <platform_run.sh>")
    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")
    if "def _normalize_smiles_header" in text:
        raise SystemExit("已经打过补丁，拒绝重复写入")
    assert text.count(OLD_CHECK) == 1, "表头判据与预期的镜像版本不一致"
    assert text.count("def main():") == 1
    assert text.count(CALL_ANCHOR) == 1
    text = text.replace(OLD_CHECK, NEW_CHECK)
    text = text.replace("def main():", HELPER)
    text = text.replace(CALL_ANCHOR, CALL_ANCHOR + "\n    _normalize_smiles_header(input_csv)")
    path.write_text(text, encoding="utf-8")
    print(f"patched {path} ({len(text)} bytes)")


if __name__ == "__main__":
    main()
