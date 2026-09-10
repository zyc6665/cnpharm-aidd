"""工具示例服务。

该模块封装工具默认示例解析、示例文件元数据构造、预览与注册逻辑，
避免 API 路由层直接承担文件系统与存储细节。
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundException, ValidationException
from app.files.storage_path import ensure_storage_dir, get_file_path
from app.models.files import File as FileModel, FileSourceType
from app.models.tools import Tool
from app.models.users import User
from app.schemas.files import FileUploadResponse
from app.schemas.tools import (
    ToolExampleApplyResponse,
    ToolExampleFilePreviewResponse,
    ToolExampleFileResponse,
    ToolExampleResponse,
)
from app.tool_packages.config_resolver import tool_package_v2_manifest_data


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEXT_PREVIEW_EXTENSIONS = {
    ".txt",
    ".json",
    ".csv",
    ".fasta",
    ".fa",
    ".pdb",
    ".log",
    ".md",
}
EXAMPLE_PREVIEW_MAX_BYTES = 64 * 1024
_EXAMPLE_BASE_DIR_INDEX: dict[Path, dict[str, Path]] = {}
SCHEMA_FALLBACK_EXAMPLE_VALUES = {
    "builtin-fetch-pdb": {"pdb_id": "1A2B"},
    "builtin-fetch-ligand": {"pubchem_cid": "2244"},
}


def _iter_inline_config_candidates(config: dict[str, Any]) -> list[dict[str, Any]]:
    """返回当前配置及可能存在的嵌套 tool_config，保持优先级。"""
    candidates: list[dict[str, Any]] = []
    if isinstance(config, dict):
        candidates.append(config)
        nested_config = config.get("tool_config")
        if isinstance(nested_config, dict):
            candidates.append(nested_config)
    return candidates


def _dedupe_config_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _load_platform_tool_config(tool: Tool, config: dict[str, Any]) -> Optional[dict[str, Any]]:
    """从 example/ 下的 platform_tool*.json 补充未入库的示例声明。"""
    base_dir = resolve_example_base_dir(tool, config)
    for config_path in sorted(base_dir.glob("platform_tool*.json")):
        try:
            with config_path.open("r", encoding="utf-8") as config_file:
                raw_config = json.load(config_file)
        except (OSError, ValueError):
            continue
        if raw_config.get("slug") == tool.slug:
            return raw_config
    return None


def _collect_tool_example_configs(tool: Tool, config: dict[str, Any]) -> list[dict[str, Any]]:
    """收集可用于默认示例的配置源，显式入库配置优先。"""
    candidates = _iter_inline_config_candidates(config)
    platform_config = _load_platform_tool_config(tool, config)
    if platform_config:
        candidates.extend(_iter_inline_config_candidates(platform_config))
    return _dedupe_config_candidates(candidates)


def _tool_package_parameter_config(config: dict[str, Any]) -> Optional[dict[str, Any]]:
    """提取 Tool Package v2 详情页实际使用的参数 schema。"""
    manifest = tool_package_v2_manifest_data(config)
    if manifest is None:
        return None
    parameter_schema = manifest.get("parameters_schema")
    if not isinstance(parameter_schema, dict):
        return None
    return {"input_schema": parameter_schema}


def _schema_properties(schema: dict[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def _includes_object_type(value: Any) -> bool:
    return "object" in value if isinstance(value, list) else value == "object"


def _is_schema_file_field(field_schema: dict[str, Any], parent_key: Optional[str] = None) -> bool:
    return (
        parent_key == "input_files"
        or field_schema.get("format") in {"file", "uri"}
        or field_schema.get("type") == "file"
    )


def _iter_schema_fields(
    input_schema: dict[str, Any],
) -> list[tuple[str, Optional[str], str, dict[str, Any]]]:
    """遍历工具输入 schema，返回扁平 key、父 key、原始 key 与字段 schema。"""
    fields: list[tuple[str, Optional[str], str, dict[str, Any]]] = []
    for key, raw_schema in _schema_properties(input_schema).items():
        if not isinstance(raw_schema, dict):
            continue
        if key == "task_id" or raw_schema.get("hidden") is True:
            continue
        if _includes_object_type(raw_schema.get("type")) and _schema_properties(raw_schema):
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
    parent_key: Optional[str],
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
        if isinstance(parent_schema, dict) and _includes_object_type(parent_schema.get("type")):
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
    """把示例参数中的文件路径移入 input_files，避免文件字段被当普通文本填入。"""
    input_files: dict[str, str] = {}
    for flat_key, parent_key, original_key, field_schema in _iter_schema_fields(input_schema):
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
    tool_slug: Optional[str],
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
        title = str(field_schema.get("title") or field_schema.get("description") or "").lower()
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
) -> Optional[str]:
    extensions = _schema_file_extensions(field_schema)
    search_dirs = [base_dir / "input", base_dir / "examples" / "input", base_dir / "examples" / "sample_input", base_dir]
    for relative_value in [field_schema.get("default"), field_schema.get("example")]:
        if isinstance(relative_value, str) and relative_value.strip():
            try:
                if resolve_example_file_path(base_dir, relative_value).is_file():
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
    base_dir: Optional[Path],
) -> dict[str, Any]:
    if not base_dir:
        return input_files

    field_schemas = {
        original_key: field_schema
        for _, parent_key, original_key, field_schema in _iter_schema_fields(input_schema)
        if _is_schema_file_field(field_schema, parent_key)
    }
    repaired: dict[str, Any] = {}
    for field, relative_path in input_files.items():
        if isinstance(relative_path, str):
            try:
                if resolve_example_file_path(base_dir, relative_path).is_file():
                    repaired[field] = relative_path
                    continue
            except ValidationException:
                repaired[field] = relative_path
                continue
        inferred_path = _infer_example_file_path(base_dir, str(field), field_schemas.get(str(field), {}))
        repaired[field] = inferred_path or relative_path
    return repaired


def _normalize_tool_example(
    *,
    name: str,
    description: Optional[str],
    params: dict[str, Any],
    input_files: dict[str, Any],
    config: dict[str, Any],
    base_dir: Optional[Path],
) -> dict[str, Any]:
    input_schema = config.get("input_schema") if isinstance(config.get("input_schema"), dict) else {}
    shaped_params = _shape_example_params(dict(params), input_schema)
    file_params = _extract_file_params_from_schema(shaped_params, input_schema)
    normalized_input_files = dict(input_files)
    for field, relative_path in file_params.items():
        normalized_input_files.setdefault(field, relative_path)
    normalized_input_files = _repair_example_file_paths(normalized_input_files, input_schema, base_dir)
    return {
        "name": name,
        "description": description,
        "params": shaped_params,
        "input_files": normalized_input_files,
    }


def _extract_examples_config_example(
    config: dict[str, Any],
    base_dir: Optional[Path],
) -> Optional[dict[str, Any]]:
    examples = config.get("examples")
    if not isinstance(examples, list) or not examples:
        return None
    first_example = examples[0]
    if not isinstance(first_example, dict):
        return None
    return _normalize_tool_example(
        name=str(first_example.get("name") or "默认示例"),
        description=first_example.get("description"),
        params=first_example.get("params") if isinstance(first_example.get("params"), dict) else {},
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
    base_dir: Optional[Path],
) -> Optional[dict[str, Any]]:
    example_params = config.get("example_params")
    if not isinstance(example_params, dict):
        return None

    if "params" in example_params or "input_files" in example_params:
        params = example_params.get("params") if isinstance(example_params.get("params"), dict) else {}
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
    tool_slug: Optional[str],
    base_dir: Optional[Path],
) -> Optional[dict[str, Any]]:
    input_schema = config.get("input_schema") if isinstance(config.get("input_schema"), dict) else {}
    params: dict[str, Any] = {}
    input_files: dict[str, Any] = {}

    for field_key, parent_key, original_key, field_schema in _iter_schema_fields(input_schema):
        if _is_schema_file_field(field_schema, parent_key):
            if base_dir:
                inferred_path = _infer_example_file_path(base_dir, original_key, field_schema)
                if inferred_path:
                    input_files[original_key] = inferred_path
            continue

        example_value = _schema_example_value(tool_slug, field_key, original_key, field_schema)
        if example_value is not None:
            _assign_schema_param(params, parent_key, original_key, example_value)

    if not params and not input_files:
        return None
    return {
        "name": "默认示例",
        "description": "根据工具参数自动生成的示例输入",
        "params": params,
        "input_files": input_files,
    }


def _select_default_tool_example(
    configs: list[dict[str, Any]],
    *,
    tool_slug: Optional[str],
    base_dir: Optional[Path],
) -> Optional[dict[str, Any]]:
    """按显式 examples、旧 example_params、schema fallback 的顺序选择默认示例。"""
    for config in configs:
        example = _extract_examples_config_example(config, base_dir)
        if example:
            return example

    for config in configs:
        example = _extract_example_params_config_example(config, base_dir)
        if example:
            return example

    for config in configs:
        example = _build_schema_default_example(config, tool_slug=tool_slug, base_dir=base_dir)
        if example:
            return example
    return None


def get_default_tool_example(config: dict) -> Optional[dict]:
    """从单个工具配置中提取默认示例，兼容旧调用方。"""
    return _select_default_tool_example(
        _iter_inline_config_candidates(config),
        tool_slug=None,
        base_dir=None,
    )


def get_tool_default_example(tool: Tool) -> Optional[dict[str, Any]]:
    """从工具当前版本与本地示例目录中解析默认示例。"""
    config = tool.current_version.config
    base_dir = resolve_example_base_dir(tool, config)
    parameter_config = _tool_package_parameter_config(config)
    if parameter_config:
        parameter_example = _build_schema_default_example(
            parameter_config,
            tool_slug=tool.slug,
            base_dir=None,
        )
        if parameter_example:
            return parameter_example

    return _select_default_tool_example(
        _collect_tool_example_configs(tool, config),
        tool_slug=tool.slug,
        base_dir=base_dir,
    )


def resolve_example_base_dir(tool: Tool, config: dict) -> Path:
    """解析工具示例文件根目录。"""
    configured_base = config.get("example_base_dir")
    if isinstance(configured_base, str) and configured_base.strip():
        base_path = Path(configured_base)
        if not base_path.is_absolute():
            base_path = PROJECT_ROOT / base_path
        return base_path.resolve()

    example_root = (PROJECT_ROOT / "example").resolve()
    slug_index = _get_example_base_dir_index(example_root)
    if tool.slug in slug_index:
        return slug_index[tool.slug]

    return (example_root / tool.slug).resolve()


def _get_example_base_dir_index(example_root: Path) -> dict[str, Path]:
    """构建并缓存示例配置 slug 到目录的索引。"""
    cached_index = _EXAMPLE_BASE_DIR_INDEX.get(example_root)
    if cached_index is not None:
        return cached_index

    slug_index: dict[str, Path] = {}
    for config_path in example_root.rglob("platform_tool*.json"):
        try:
            with config_path.open("r", encoding="utf-8") as config_file:
                raw_config = json.load(config_file)
        except (OSError, ValueError):
            continue
        slug = raw_config.get("slug")
        if isinstance(slug, str) and slug.strip():
            slug_index.setdefault(slug, config_path.parent.resolve())

    _EXAMPLE_BASE_DIR_INDEX[example_root] = slug_index
    return slug_index


def resolve_example_file_path(base_dir: Path, relative_path: str) -> Path:
    """解析并校验示例文件路径，防止路径穿越。"""
    candidate = (base_dir / relative_path).resolve()
    try:
        candidate.relative_to(base_dir)
    except ValueError as exc:
        raise ValidationException("示例文件路径非法") from exc
    return candidate


def guess_content_type(path: Path) -> Optional[str]:
    """根据文件名推断 content type。"""
    content_type, _ = mimetypes.guess_type(path.name)
    return content_type or "application/octet-stream"


def is_previewable_example_file(path: Path) -> bool:
    """判断示例文件是否支持文本预览。"""
    return path.suffix.lower() in TEXT_PREVIEW_EXTENSIONS


def build_example_file_response(field: str, relative_path: str, base_dir: Path) -> ToolExampleFileResponse:
    """构造示例文件元数据。"""
    file_path = resolve_example_file_path(base_dir, relative_path)
    exists = file_path.is_file()
    return ToolExampleFileResponse(
        field=field,
        path=relative_path,
        filename=file_path.name,
        size_bytes=file_path.stat().st_size if exists else None,
        content_type=guess_content_type(file_path),
        exists=exists,
        previewable=exists and is_previewable_example_file(file_path),
    )


def build_tool_example_response(tool: Tool) -> Optional[ToolExampleResponse]:
    """构造工具默认示例响应。"""
    config = tool.current_version.config
    example = get_tool_default_example(tool)
    if not example:
        return None

    base_dir = resolve_example_base_dir(tool, config)
    input_files = example.get("input_files") or {}
    if not isinstance(input_files, dict):
        raise ValidationException("示例 input_files 必须是对象")

    file_responses = [
        build_example_file_response(str(field), str(relative_path), base_dir)
        for field, relative_path in input_files.items()
    ]
    return ToolExampleResponse(
        name=example["name"],
        description=example.get("description"),
        params=example.get("params") or {},
        input_files=file_responses,
    )


async def register_example_file_for_user(
    db: AsyncSession,
    current_user: User,
    source_path: Path,
) -> FileUploadResponse:
    """将示例文件复制到当前用户文件空间。"""
    ensure_storage_dir()
    content = source_path.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()
    file_id = str(uuid.uuid4())
    target_path = get_file_path(file_id, source_path.name)
    file_record = FileModel(
        id=file_id,
        filename=source_path.name,
        content_type=guess_content_type(source_path),
        size_bytes=len(content),
        sha256=sha256,
        source_type=FileSourceType.UPLOAD.value,
        is_public=False,
        owner_id=current_user.id,
        storage_path=str(target_path),
    )
    db.add(file_record)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, target_path)
    await db.flush()

    return FileUploadResponse(
        id=file_record.id,
        filename=file_record.filename,
        size_bytes=file_record.size_bytes,
        content_type=file_record.content_type,
        sha256=file_record.sha256,
    )


async def apply_tool_example_to_user(
    db: AsyncSession,
    current_user: User,
    tool: Tool,
) -> ToolExampleApplyResponse:
    """将工具默认示例应用到当前用户文件空间。"""
    config = tool.current_version.config
    example = get_tool_default_example(tool)
    if not example:
        raise NotFoundException("工具暂无示例")

    input_files = example.get("input_files") or {}
    if not isinstance(input_files, dict):
        raise ValidationException("示例 input_files 必须是对象")

    base_dir = resolve_example_base_dir(tool, config)
    registered_files: dict[str, FileUploadResponse] = {}
    for field, relative_path in input_files.items():
        source_path = resolve_example_file_path(base_dir, str(relative_path))
        if not source_path.is_file():
            raise NotFoundException(f"示例文件不存在: {relative_path}")
        registered_files[str(field)] = await register_example_file_for_user(
            db,
            current_user,
            source_path,
        )

    return ToolExampleApplyResponse(
        params=example.get("params") or {},
        files=registered_files,
    )


def build_tool_example_file_preview(tool: Tool, field: str) -> ToolExampleFilePreviewResponse:
    """构造工具示例文件预览响应。"""
    config = tool.current_version.config
    example = get_tool_default_example(tool)
    if not example:
        raise NotFoundException("工具暂无示例")

    input_files = example.get("input_files") or {}
    if not isinstance(input_files, dict) or field not in input_files:
        raise NotFoundException("示例文件不存在")

    base_dir = resolve_example_base_dir(tool, config)
    source_path = resolve_example_file_path(base_dir, str(input_files[field]))
    if not source_path.is_file():
        raise NotFoundException("示例文件不存在")

    previewable = is_previewable_example_file(source_path)
    content = None
    truncated = False
    if previewable:
        raw_content = source_path.read_bytes()
        truncated = len(raw_content) > EXAMPLE_PREVIEW_MAX_BYTES
        content = raw_content[:EXAMPLE_PREVIEW_MAX_BYTES].decode("utf-8", errors="replace")

    return ToolExampleFilePreviewResponse(
        field=field,
        filename=source_path.name,
        content_type=guess_content_type(source_path),
        content=content,
        truncated=truncated,
        previewable=previewable,
    )
