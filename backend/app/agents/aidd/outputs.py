"""Extract semantic artifacts from completed task results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.aidd.capabilities import CapabilityOutput, ToolCapability


def read_path(data: Any, path: str | None) -> Any:
    if not path:
        return None

    current = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def read_output_data_path(data: Any, path: str | None) -> Any:
    value = read_path(data, path)
    if value is not None:
        return value
    if isinstance(data, dict) and isinstance(data.get("result"), dict):
        return read_path(data["result"], path)
    return None


def file_matches(file_data: dict[str, Any], output: CapabilityOutput) -> bool:
    return file_match_score(file_data, output) is not None


def file_match_score(file_data: dict[str, Any], output: CapabilityOutput) -> int | None:
    if not output.match:
        return None

    filename = str(file_data.get("original_name") or file_data.get("filename") or "")
    content_type = str(file_data.get("content_type") or "")

    if output.match.extension and Path(filename).suffix.lower() != output.match.extension.lower():
        return None

    score = 0
    if output.match.filename_contains_any:
        lowered = filename.lower()
        matched_index = next(
            (
                index
                for index, token in enumerate(output.match.filename_contains_any)
                if token.lower() in lowered
            ),
            None,
        )
        if matched_index is None:
            return None
        score = matched_index

    if output.match.content_type and output.match.content_type != content_type:
        return None

    return score


def parse_sdf_smiles(content: str) -> list[str]:
    smiles_values: list[str] = []
    for block in content.split("$$$$"):
        lines = [line.rstrip() for line in block.splitlines()]
        for index, line in enumerate(lines):
            normalized = line.strip().lower()
            if not normalized.startswith("> <"):
                continue
            field_name = normalized[3:].strip(" <>").lower()
            if field_name not in {"smiles", "canonical_smiles"}:
                continue
            for value_line in lines[index + 1 :]:
                value = value_line.strip()
                if value:
                    smiles_values.append(value)
                    break
            break
    return smiles_values


def extract_semantic_outputs(
    *,
    capability: ToolCapability,
    task_output_files: list[dict[str, Any]],
    output_data: Any,
) -> dict[str, dict[str, Any]]:
    semantic_outputs: dict[str, dict[str, Any]] = {}

    for output in capability.outputs:
        if output.source == "output_files":
            matched_files = [
                (file, score)
                for file in task_output_files
                if (score := file_match_score(file, output)) is not None
            ]
            matched_file = min(matched_files, key=lambda item: item[1])[0] if matched_files else None
            if matched_file:
                semantic_outputs[output.semantic_type] = {
                    "source": "output_files",
                    "file_id": str(matched_file.get("id")),
                    "filename": matched_file.get("filename") or matched_file.get("original_name"),
                    "url": matched_file.get("url"),
                    "content_type": matched_file.get("content_type"),
                }
                if (
                    output.semantic_type == "generated_ligand"
                    and str(matched_file.get("content_type") or "").startswith("chemical/x-mdl-sdfile")
                ):
                    smiles_candidates = parse_sdf_smiles(Path(str(matched_file.get("path") or "")).read_text(encoding="utf-8")) if matched_file.get("path") else []
                    if smiles_candidates:
                        semantic_outputs["smiles_csv"] = {
                            "source": "output_data",
                            "path": "generated_smiles.csv",
                            "value": "\n".join(["SMILES,id", *[f"{smiles},mol_{index + 1}" for index, smiles in enumerate(smiles_candidates)]]),
                        }
            continue

        value = read_output_data_path(output_data, output.path)
        if value is not None:
            semantic_outputs[output.semantic_type] = {
                "source": "output_data",
                "path": output.path,
                "value": value,
            }

    return semantic_outputs
