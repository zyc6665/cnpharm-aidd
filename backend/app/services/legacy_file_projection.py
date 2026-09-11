"""Project standard Artifact inputs into legacy file fields."""

from __future__ import annotations

from typing import Any, Mapping


def legacy_file_fields(config: Mapping[str, Any]) -> list[str]:
    input_schema = (
        config.get("input_schema")
        if isinstance(config.get("input_schema"), dict)
        else {}
    )
    properties = (
        input_schema.get("properties")
        if isinstance(input_schema.get("properties"), dict)
        else {}
    )
    return [
        str(name)
        for name, schema in properties.items()
        if isinstance(schema, dict)
        and (schema.get("format") == "file" or schema.get("type") == "file")
    ]


def select_legacy_file_field(
    *,
    input_name: str,
    standard_type: str,
    file_fields: list[str],
    used_fields: set[str] | None = None,
) -> str | None:
    used = used_fields or set()
    unused_fields = [field for field in file_fields if field not in used]
    if input_name in unused_fields:
        return input_name
    if not unused_fields:
        return None
    if len(unused_fields) == 1:
        return unused_fields[0]

    input_name_match = _first_matching_field(unused_fields, (input_name,))
    if input_name_match:
        return input_name_match

    tokens = {
        "protein_structure@1": ("protein", "receptor"),
        "ligand_structure@1": ("ligand",),
        "molecule_table@1": ("smiles", "molecule", "csv"),
        "binding_pocket@1": ("pocket",),
    }.get(str(standard_type or ""), ())
    return _first_matching_field(unused_fields, tokens) or unused_fields[0]


def standard_input_file_path(standard_input: dict[str, Any], standard_type: str) -> str | None:
    files = standard_input.get("files")
    if not isinstance(files, dict):
        return None
    for role in preferred_standard_file_roles(standard_type):
        file_ref = files.get(role)
        if isinstance(file_ref, dict) and file_ref.get("path"):
            return str(file_ref["path"])
    for file_ref in files.values():
        if isinstance(file_ref, dict) and file_ref.get("path"):
            return str(file_ref["path"])
    return None


def preferred_standard_file_roles(standard_type: str) -> tuple[str, ...]:
    return {
        "protein_structure@1": ("prepared_pdb", "structure_file", "raw_structure_file"),
        "ligand_structure@1": ("structure_3d_sdf", "structure_file", "structure_2d_sdf"),
        "molecule_table@1": ("table_file",),
        "binding_pocket@1": ("residue_pocket_pdb", "atom_pocket_pdb"),
        "run_report@1": ("report_json", "report_markdown"),
    }.get(str(standard_type or ""), ())


def _first_matching_field(fields: list[str], tokens: tuple[str, ...]) -> str | None:
    lowered = [(field, field.lower()) for field in fields]
    for token in tokens:
        token = token.lower()
        match = next((field for field, lower in lowered if token and token in lower), None)
        if match:
            return match
    return None
