#!/usr/bin/env python3
"""Translate a platform request.v2 payload into the legacy fields research models read.

The platform passes a standard ``aidd.sciminer/request`` document with grouped
``inputs`` (per-slot ``files`` keyed by standard role) and ``parameters``.  The
upstream model entry scripts in these images predate that contract and expect a
flat ``input_files`` mapping plus ``params``.  This adapter bridges the two
without touching model code.

Usage:
    python request_to_legacy.py --params-json /workspace/input/request.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PRIMARY_ROLE_BY_TYPE = {
    "protein_structure@1": ("prepared_pdb", "structure_file", "raw_structure_file"),
    "ligand_structure@1": ("structure_3d_sdf", "structure_file", "structure_2d_sdf"),
    "binding_pocket@1": ("residue_pocket_pdb", "pocket_file"),
    "molecule_table@1": ("table_file",),
    "run_report@1": ("report_json",),
}


def choose_file(files: dict, artifact_type: str) -> str | None:
    for role in PRIMARY_ROLE_BY_TYPE.get(artifact_type, ()):
        entry = files.get(role)
        if isinstance(entry, dict) and entry.get("path"):
            return str(entry["path"])
    for entry in files.values():
        if isinstance(entry, dict) and entry.get("path"):
            return str(entry["path"])
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--params-json", required=True)
    args = parser.parse_args()

    path = Path(args.params_json)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("request.json must contain an object")

    input_files: dict[str, str] = {}
    for name, artifact in (payload.get("inputs") or {}).items():
        if not isinstance(artifact, dict):
            continue
        chosen = choose_file(artifact.get("files") or {}, str(artifact.get("type") or ""))
        if chosen is None:
            continue
        # file refs are relative to the job work dir (``input/<slot>/<file>``);
        # the legacy scripts resolve them relative to ``--input-dir``.
        if chosen.startswith("input/"):
            chosen = chosen[len("input/") :]
        input_files[name] = chosen

    # Platform requests may carry an empty legacy ``params`` alongside the v2
    # ``parameters``. Some executors also double-wrap: parameters={"params": {...}}.
    # Normalise all shapes into a flat legacy ``params`` mapping.
    raw_parameters = payload.get("parameters") or {}
    if isinstance(raw_parameters, dict) and isinstance(raw_parameters.get("params"), dict):
        legacy_params = raw_parameters["params"]
        extra_files = raw_parameters.get("input_files") or {}
    else:
        legacy_params = raw_parameters
        extra_files = {}
    payload["params"] = {
        **(payload.get("params") or {}),
        **(legacy_params if isinstance(legacy_params, dict) else {}),
    }
    for key, value in (extra_files or {}).items():
        input_files.setdefault(key, value)
    payload["input_files"] = input_files
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
