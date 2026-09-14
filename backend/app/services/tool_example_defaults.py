"""Default example resolution for tool detail pages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.common.exceptions import ValidationException
from app.services.tool_example_paths import resolve_tool_example_file_path
from app.tool_packages.config_resolver import tool_package_v2_manifest_data


SCHEMA_FALLBACK_EXAMPLE_VALUES = {
    "builtin-fetch-pdb": {"pdb_id": "1A2B"},
    "builtin-fetch-ligand": {"pubchem_cid": "2244"},
}
SchemaField = tuple[str, str | None, str, dict[str, Any]]


def iter_inline_config_candidates(
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """返回当前配置及可能存在的嵌套 tool_config，保持优先级。"""
    candidates: list[dict[str, Any]] = []
    if isinstance(config, dict):
        candidates.append(config)
        nested_config = config.get("tool_config")
        if isinstance(nested_config, dict):
            candidates.append(nested_config)
    return candidates


def dedupe_config_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按对象身份去重，避免同一配置重复解析。"""
    seen: set[int] = set()
    deduped: list[dict[str, Any]] = []
    for candidate in candidates:
        marker = id(candidate)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(candidate)
    return deduped


def tool_package_parameter_config(
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """提取 Tool Package v2 详情页实际使用的参数 schema。"""
    manifest = tool_package_v2_manifest_data(config)
    if manifest is None:
        return None
    parameter_schema = manifest.get("parameters_schema")
    if not isinstance(parameter_schema, dict):
        return None
    return {"input_schema": parameter_schema}


def select_default_tool_example(
    configs: list[dict[str, Any]],
    *,
    tool_slug: str | None,
    base_dir: Path | None,
) -> dict[str, Any] | None:
    """按显式 examples、旧 example_params、schema fallback 选择默认示例。"""
    for config in configs:
        example = _extract_examples_config_example(config, base_dir)
        if example:
            return example

    for config in configs:
        example = _extract_example_params_config_example(config, base_dir)
        if example:
            return example

    for config in configs:
        example = _build_schema_default_example(
            config,
            tool_slug=tool_slug,
            base_dir=base_dir,
        )
        if example:
            return example
    return None


def get_default_tool_example_from_config(
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """从单个工具配置中提取默认示例，兼容旧调用方。"""
    return select_default_tool_example(
        iter_inline_config_candidates(config),
        tool_slug=None,
        base_dir=None,
    )


def _schema_properties(schema: dict[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def _includes_object_type(value: Any) -> bool:
    return "object" in value if isinstance(value, list) else value == "object"


def _is_schema_file_field(
    field_schema: dict[str, Any],
    parent_key: str | None = None,
) -> bool:
    return (
        parent_key == "input_files"
        or field_schema.get("format") in {"file", "uri"}
        or field_schema.get("type") == "file"
    )


def _iter_schema_fields(
    input_schema: dict[str, Any],
) -> list[SchemaField]:
    """遍历工具输入 schema，返回扁平 key、父 key、原始 key 与字段 schema。"""
    fields: list[SchemaField] = []
    for key, raw_schema in _schema_properties(input_schema).items():
        if not isinstance(raw_schema, dict):
            continue
        if key == "task_id" or raw_schema.get("hidden") is True:
            continue
        is_object_field = _includes_object_type(raw_schema.get("type"))
        if is_object_field and _schema_properties(raw_schema):
            for sub_key, sub_schema in _schema_properties(raw_schema).items():
                if not isinstance(sub_schema, dict):
                    continue
                if sub_schema.get("hidden") is True:
                    continue
                fields.append((f"{key}.{sub_key}", key, sub_key, sub_schema))
            continue
        fields.append((key, None, key, raw_schema))
    return fields


def _assign_schema_param(
    params: dict[str, Any],
    parent_key: str | None,
    original_key: str,
    value: Any,
) -> None:
    if parent_key:
        parent_value = params.get(parent_key)
        parent_params = parent_value if isinstance(parent_value, dict) else {}
        parent_params[original_key] = value
        params[parent_key] = parent_params
        return
    params[original_key] = value


def _shape_example_params(
    raw_params: dict[str, Any],
    input_schema: dict[str, Any],
) -> dict[str, Any]:
    """把旧示例参数映射回 input_schema 期望的嵌套形状。"""
    properties = _schema_properties(input_schema)
    if not properties:
        return dict(raw_params)

    nested_field_to_parent: dict[str, str] = {}
    for parent_key, parent_schema in properties.items():
        if not isinstance(parent_schema, dict):
            continue
        if not _includes_object_type(parent_schema.get("type")):
            continue
        for sub_key in _schema_properties(parent_schema):
            nested_field_to_parent.setdefault(sub_key, parent_key)

    shaped: dict[str, Any] = {}
    for key, value in raw_params.items():
        if key in properties:
            shaped[key] = value
            continue
        parent_key = nested_field_to_parent.get(key)
        if parent_key:
            _assign_schema_param(shaped, parent_key, key, value)
            continue
        shaped[key] = value
    return shaped


def _extract_file_params_from_schema(
    params: dict[str, Any],
    input_schema: dict[str, Any],
) -> dict[str, str]:
    """把示例参数中的文件路径移入 input_files，避免文件字段当作普通文本。"""
    input_files: dict[str, str] = {}
    for schema_field in _iter_schema_fields(input_schema):
        flat_key, parent_key, original_key, field_schema = schema_field
        if not _is_schema_file_field(field_schema, parent_key):
            continue
        if parent_key:
            parent_value = params.get(parent_key)
            if isinstance(parent_value, dict):
                file_value = parent_value.pop(original_key, None)
                if not parent_value:
                    params.pop(parent_key, None)
                if isinstance(file_value, str) and file_value.strip():
                    input_files[original_key] = file_value
            continue
        file_value = params.pop(flat_key, None)
        if isinstance(file_value, str) and file_value.strip():
            input_files[original_key] = file_value
    return input_files


def _schema_example_value(
    tool_slug: str | None,
    field_key: str,
    original_key: str,
    field_schema: dict[str, Any],
) -> Any:
    if field_schema.get("default") is not None:
        return field_schema["default"]
    if field_schema.get("example") is not None:
        return field_schema["example"]
    examples = field_schema.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]
    fallback_values = SCHEMA_FALLBACK_EXAMPLE_VALUES.get(tool_slug or "", {})
    if field_key in fallback_values:
        return fallback_values[field_key]
    if original_key in fallback_values:
        return fallback_values[original_key]
    enum_values = field_schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]
    return None


def _schema_file_extensions(field_schema: dict[str, Any]) -> list[str]:
    accept_value = field_schema.get("ui:accept") or field_schema.get("accept")
    extensions: list[str] = []
    if isinstance(accept_value, str):
        for item in accept_value.split(","):
            candidate = item.strip().lower()
            if candidate.startswith("."):
                extensions.append(candidate)
    if field_schema.get("format") == "file" and not extensions:
        title = str(
            field_schema.get("title") or field_schema.get("description") or ""
        ).lower()
        for extension in [".pdb", ".sdf", ".mol2", ".csv", ".txt", ".json"]:
            if extension.removeprefix(".") in title:
                extensions.append(extension)
    return list(dict.fromkeys(extensions))


def _candidate_file_names(field_name: str, extensions: list[str]) -> list[str]:
    names: list[str] = []
    for extension in extensions:
        suffix = f"_{extension.removeprefix('.')}"
        if field_name.endswith(suffix):
            names.append(f"{field_name[: -len(suffix)]}{extension}")
        names.append(f"{field_name}{extension}")
    return list(dict.fromkeys(names))


def _to_relative_example_path(base_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(base_dir).as_posix()


def _infer_example_file_path(
    base_dir: Path,
    field_name: str,
    field_schema: dict[str, Any],
) -> str | None:
    extensions = _schema_file_extensions(field_schema)
    search_dirs = [
        base_dir / "input",
        base_dir / "examples" / "input",
        base_dir / "examples" / "sample_input",
        base_dir,
    ]
    for relative_value in [
        field_schema.get("default"),
        field_schema.get("example"),
    ]:
        if isinstance(relative_value, str) and relative_value.strip():
            try:
                candidate_path = resolve_tool_example_file_path(
                    base_dir,
                    relative_value,
                )
                if candidate_path.is_file():
                    return relative_value
            except ValidationException:
                continue

    for directory in search_dirs:
        for file_name in _candidate_file_names(field_name, extensions):
            candidate = directory / file_name
            if candidate.is_file():
                return _to_relative_example_path(base_dir, candidate)

    if extensions:
        matches: list[Path] = []
        for directory in search_dirs:
            if not directory.is_dir():
                continue
            for extension in extensions:
                matches.extend(sorted(directory.glob(f"*{extension}")))
        unique_matches = list(dict.fromkeys(matches))
        if len(unique_matches) == 1:
            return _to_relative_example_path(base_dir, unique_matches[0])
    return None


def _repair_example_file_paths(
    input_files: dict[str, Any],
    input_schema: dict[str, Any],
    base_dir: Path | None,
) -> dict[str, Any]:
    if not base_dir:
        return input_files

    field_schemas = {
        original_key: field_schema
        for _, parent_key, original_key, field_schema in _iter_schema_fields(
            input_schema
        )
        if _is_schema_file_field(field_schema, parent_key)
    }
    repaired: dict[str, Any] = {}
    for field, relative_path in input_files.items():
        if isinstance(relative_path, str):
            try:
                candidate_path = resolve_tool_example_file_path(
                    base_dir,
                    relative_path,
                )
                if candidate_path.is_file():
                    repaired[field] = relative_path
                    continue
            except ValidationException:
                repaired[field] = relative_path
                continue
        inferred_path = _infer_example_file_path(
            base_dir,
            str(field),
            field_schemas.get(str(field), {}),
        )
        repaired[field] = inferred_path or relative_path
    return repaired


def _normalize_tool_example(
    *,
    name: str,
    description: str | None,
    params: dict[str, Any],
    input_files: dict[str, Any],
    config: dict[str, Any],
    base_dir: Path | None,
) -> dict[str, Any]:
    input_schema = config.get("input_schema")
    if not isinstance(input_schema, dict):
        input_schema = {}
    shaped_params = _shape_example_params(dict(params), input_schema)
    file_params = _extract_file_params_from_schema(shaped_params, input_schema)
    normalized_input_files = dict(input_files)
    for field, relative_path in file_params.items():
        normalized_input_files.setdefault(field, relative_path)
    normalized_input_files = _repair_example_file_paths(
        normalized_input_files,
        input_schema,
        base_dir,
    )
    return {
        "name": name,
        "description": description,
        "params": shaped_params,
        "input_files": normalized_input_files,
    }


def _extract_examples_config_example(
    config: dict[str, Any],
    base_dir: Path | None,
) -> dict[str, Any] | None:
    examples = config.get("examples")
    if not isinstance(examples, list) or not examples:
        return None
    first_example = examples[0]
    if not isinstance(first_example, dict):
        return None
    return _normalize_tool_example(
        name=str(first_example.get("name") or "默认示例"),
        description=first_example.get("description"),
        params=(
            first_example.get("params")
            if isinstance(first_example.get("params"), dict)
            else {}
        ),
        input_files=(
            first_example.get("input_files")
            if isinstance(first_example.get("input_files"), dict)
            else {}
        ),
        config=config,
        base_dir=base_dir,
    )


def _extract_example_params_config_example(
    config: dict[str, Any],
    base_dir: Path | None,
) -> dict[str, Any] | None:
    example_params = config.get("example_params")
    if not isinstance(example_params, dict):
        return None

    if "params" in example_params or "input_files" in example_params:
        params = (
            example_params.get("params")
            if isinstance(example_params.get("params"), dict)
            else {}
        )
        extra_params = {
            key: value
            for key, value in example_params.items()
            if key not in {"params", "input_files"}
        }
        params = {**params, **extra_params}
        input_files = (
            example_params.get("input_files")
            if isinstance(example_params.get("input_files"), dict)
            else {}
        )
    else:
        params = example_params
        input_files = {}

    return _normalize_tool_example(
        name="默认示例",
        description=None,
        params=params,
        input_files=input_files,
        config=config,
        base_dir=base_dir,
    )


def _build_schema_default_example(
    config: dict[str, Any],
    *,
    tool_slug: str | None,
    base_dir: Path | None,
) -> dict[str, Any] | None:
    input_schema = config.get("input_schema")
    if not isinstance(input_schema, dict):
        input_schema = {}
    params: dict[str, Any] = {}
    input_files: dict[str, Any] = {}

    for schema_field in _iter_schema_fields(input_schema):
        field_key, parent_key, original_key, field_schema = schema_field
        if _is_schema_file_field(field_schema, parent_key):
            if base_dir:
                inferred_path = _infer_example_file_path(
                    base_dir,
                    original_key,
                    field_schema,
                )
                if inferred_path:
                    input_files[original_key] = inferred_path
            continue

        example_value = _schema_example_value(
            tool_slug,
            field_key,
            original_key,
            field_schema,
        )
        if example_value is not None:
            _assign_schema_param(
                params,
                parent_key,
                original_key,
                example_value,
            )

    if not params and not input_files:
        return None
    return {
        "name": "默认示例",
        "description": "根据工具参数自动生成的示例输入",
        "params": params,
        "input_files": input_files,
    }
