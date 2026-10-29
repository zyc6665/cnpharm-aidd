#!/usr/bin/env python3
"""把模型源目录里 ``platform_run.sh`` 产出的结果从 v1 形状改成 ``result.v2``。

为什么要这个 patch
------------------
LVpocket-2 的包装脚本产出的是 v1 形状 ``result.json``::

    {"success": true, "message": "...", "outputs": {...},
     "artifacts": [{name, path, content_type}], "metrics": {...}, "error": null}

而平台的 ``StandardExecutionResult``（``backend/app/execution/standard_contracts.py``）
是 ``model_config = ConfigDict(extra="forbid")``，只接受五个顶层键::

    result_version / artifacts / relations / summary / metrics

``artifacts`` 还必须是按产物名分键的 object，每个产物是
``StandardOutputArtifact``::

    {"<name>": {"type": "<semantic_type>@<version>",
                "files": {"<role>": {"path": "<相对路径>", "sha256": "<64 hex>"}}}}

真集群上一路跑下来依次撞到四个报错::

    result.v2 artifacts must be an object
    Extra inputs are not permitted                       (success)
    artifacts.<name>.StandardOutputArtifact  Input should be a valid dictionary
    artifacts.<name>.type  Field required

本脚本把整段 ``payload = {...}`` 换成 v2 形状，一次到位：

* 顶层加 ``result_version``，去掉 ``success`` / ``message`` / ``error``。
* ``artifacts`` 从 list 改成 object；每个产物补 ``type`` 与
  ``files{role:{path,sha256}}``，sha256 现场算。
* ``outputs`` 的内容并进 ``metrics``（这些观测值有用，只是 v2 没有 ``outputs`` 这个键）。

用法::

    python3 patches/patch_result_v2.py model/platform_run.sh

幂等：已改过的文件直接返回 0。原文对不上则 fail fast —— 宁可报错，
也不要产出一个"看起来改了其实没改"的包。

关于 ``type``：本包未在 ToolVersion 里声明 ``artifacts.outputs``，
平台不会按名字校验产物，统一用 ``run_report@1`` 只为让产物流转时有合法语义类型。
若要按 ``binding_pocket@1`` 落库，还需补齐该标准要求的三个 file role
（``residue_pocket_pdb`` / ``atom_pocket_pdb`` / ``pocket_metadata_json``），另议。
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = '"result_version": "aidd.sciminer/result.v2"'

OLD_BLOCK = '''payload = {
    "success": True,
    "message": "LVpocket pocket prediction completed",
    "outputs": {
        "selected_model": prediction.get("selected_model"),
        "model_choice": prediction.get("model_choice"),
        "classification": prediction.get("classification"),
        "pocket_count": prediction.get("pocket_count"),
        "pockets": prediction.get("pockets", []),
        "protein_pocket_residues": prediction.get("protein_pocket_residues"),
        "protein_pocket_residues_list": prediction.get("protein_pocket_residues_list", []),
        "device": prediction.get("device"),
    },
    "artifacts": artifacts,
    "metrics": {
        "duration_sec": duration_sec,
        "model_duration_sec": prediction.get("metrics", {}).get("duration_sec"),
    },
    "error": None,
}'''

NEW_BLOCK = '''import hashlib

artifact_map = {}
for _a in artifacts:
    _rel = str(_a["path"])
    _h = hashlib.sha256()
    _h.update((result_json.parent / _rel).read_bytes())
    artifact_map[str(_a["name"])] = {
        "type": "run_report@1",
        "files": {"report_json": {"path": _rel, "sha256": _h.hexdigest()}},
    }

payload = {
    "result_version": "aidd.sciminer/result.v2",
    "artifacts": artifact_map,
    "metrics": {
        "message": "LVpocket pocket prediction completed",
        "duration_sec": duration_sec,
        "model_duration_sec": prediction.get("metrics", {}).get("duration_sec"),
        "selected_model": prediction.get("selected_model"),
        "model_choice": prediction.get("model_choice"),
        "classification": prediction.get("classification"),
        "pocket_count": prediction.get("pocket_count"),
        "pockets": prediction.get("pockets", []),
        "protein_pocket_residues": prediction.get("protein_pocket_residues"),
        "protein_pocket_residues_list": prediction.get("protein_pocket_residues_list", []),
        "device": prediction.get("device"),
    },
}'''


def patch(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    if MARKER in source:
        print(f"[patch_result_v2] 已应用，跳过: {path}")
        return 0
    if OLD_BLOCK not in source:
        raise SystemExit(
            f"[patch_result_v2] 失败：在 {path} 中找不到预期的 v1 payload 段。\n"
            "源目录的 platform_run.sh 与本 patch 不匹配（上游可能已改动），"
            "请人工核对后再更新 patches/patch_result_v2.py 的 OLD_BLOCK。"
        )
    path.write_text(source.replace(OLD_BLOCK, NEW_BLOCK, 1), encoding="utf-8")
    print(f"[patch_result_v2] 已应用: {path}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法: patch_result_v2.py <platform_run.sh>", file=sys.stderr)
        return 2
    return patch(Path(argv[1]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
