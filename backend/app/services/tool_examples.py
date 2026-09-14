"""工具示例服务。

该模块封装工具默认示例解析、示例文件元数据构造、预览与注册逻辑，
避免 API 路由层直接承担文件系统与存储细节。
"""

from __future__ import annotations

import hashlib
import json
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
from app.services.tool_example_defaults import (
    dedupe_config_candidates,
    get_default_tool_example_from_config,
    iter_inline_config_candidates,
    select_default_tool_example,
    tool_package_parameter_config,
)
from app.services.tool_example_paths import (
    EXAMPLE_PREVIEW_MAX_BYTES,
    PROJECT_ROOT as DEFAULT_PROJECT_ROOT,
    guess_tool_example_content_type,
    is_previewable_tool_example_file,
    resolve_tool_example_base_dir,
    resolve_tool_example_file_path,
)


PROJECT_ROOT = DEFAULT_PROJECT_ROOT


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
    candidates = iter_inline_config_candidates(config)
    platform_config = _load_platform_tool_config(tool, config)
    if platform_config:
        candidates.extend(iter_inline_config_candidates(platform_config))
    return dedupe_config_candidates(candidates)


def get_default_tool_example(config: dict) -> Optional[dict]:
    """从单个工具配置中提取默认示例，兼容旧调用方。"""
    return get_default_tool_example_from_config(config)


def get_tool_default_example(tool: Tool) -> Optional[dict[str, Any]]:
    """从工具当前版本与本地示例目录中解析默认示例。"""
    config = tool.current_version.config
    base_dir = resolve_example_base_dir(tool, config)
    parameter_config = tool_package_parameter_config(config)
    if parameter_config:
        parameter_example = select_default_tool_example(
            [parameter_config],
            tool_slug=tool.slug,
            base_dir=None,
        )
        if parameter_example:
            return parameter_example

    return select_default_tool_example(
        _collect_tool_example_configs(tool, config),
        tool_slug=tool.slug,
        base_dir=base_dir,
    )


def resolve_example_base_dir(tool: Tool, config: dict) -> Path:
    """解析工具示例文件根目录。"""
    return resolve_tool_example_base_dir(
        tool,
        config,
        project_root=PROJECT_ROOT,
    )


def resolve_example_file_path(base_dir: Path, relative_path: str) -> Path:
    """解析并校验示例文件路径，防止路径穿越。"""
    return resolve_tool_example_file_path(base_dir, relative_path)


def guess_content_type(path: Path) -> Optional[str]:
    """根据文件名推断 content type。"""
    return guess_tool_example_content_type(path)


def is_previewable_example_file(path: Path) -> bool:
    """判断示例文件是否支持文本预览。"""
    return is_previewable_tool_example_file(path)


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
