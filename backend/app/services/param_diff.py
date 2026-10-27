"""运行参数 diff（docs/12 TC-M7-07，docs/05 §「POST /results:compare」）。

为什么是「以字段为行、任务为列」的矩阵
--------------------------------------
TC-M7-07 要的是「参数差异可见（diff 视图）」，且要能对比 2~6 个任务。若按
两两 pairwise diff 返回，调用方要自己拼出「谁跟谁不同」；矩阵形态天然回答
两个问题：这一行有几个任务取值不同（``changed``），每个任务的具体值是多少。

为什么必须递归摊平
------------------
任务参数是嵌套 JSON（``params.box.center_x``）。若只对顶层 key 做比较，
``box`` 内改一个数就会把整块标成「不同」，读者看不到差在哪，diff 也就
失去了意义。摊平成点分路径后，差异定位到叶子，``unchanged`` 也能精确到叶子。

不可变性怎么落实
----------------
TC-M7-07 要求「历史任务参数不可被修改」。本模块**只读**参数（绝不写
``TaskInput.params``），并用 :func:`param_fingerprint` 为每个任务的参数算一个
规范化指纹：同一任务连续两次 diff 必然得到相同 fingerprint，这条写进测试。
指纹也让「参数被偷偷改过」可被事后发现——把两次 diff 的 fingerprint 一对
就知道。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tasks import Task, TaskInput

#: 一次比较的任务数下限/上限（TC-M7-07 + 接口预算：6 列仍可读）。
MIN_TASKS = 2
MAX_TASKS = 6

#: 单值渲染上限，避免一整个 PDB 头进 JSON。超限给「已截断」标记。
MAX_VALUE_CHARS = 2000

_CELL_TRUNCATED_SUFFIX = "…"


def flatten_params(value: Any, *, prefix: str = "") -> dict[str, Any]:
    """把嵌套参数摊平成 ``{点分路径: 叶子值}``。

    * dict → 递归下探（``box.center_x``）
    * list → 用下标路径（``size[0]``），长度变化因此体现为路径增删
    * 其余（标量 / None）→ 叶子

    空 dict / 空 list 会保留自身路径，否则「从无到空容器」这种变化会消失。
    """
    flat: dict[str, Any] = {}

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            if not node:
                flat[path or ""] = {}
                return
            for key in node:
                _walk(node[key], f"{path}.{key}" if path else str(key))
            return
        if isinstance(node, (list, tuple)):
            if not node:
                flat[path or ""] = []
                return
            for index, item in enumerate(node):
                _walk(item, f"{path}[{index}]")
            return
        flat[path or ""] = node

    _walk(value, prefix)
    return flat


def canonical_json(value: Any) -> str:
    """规范化 JSON：``sort_keys`` + 紧凑分隔符 + ``ensure_ascii=False``。

    键序不影响指纹，中文保持可读。
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def param_fingerprint(params: Any) -> str:
    """参数的 SHA256 指纹——「历史参数不可变」的可复核凭证。"""
    return hashlib.sha256(canonical_json(params if params is not None else {}).encode("utf-8")).hexdigest()


def _render_cell(value: Any, *, present: bool) -> str:
    """把叶子值渲染成单元格文本；``present=False`` 表示该任务没有这个字段。"""
    if not present:
        return "-"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) > MAX_VALUE_CHARS:
        return text[: MAX_VALUE_CHARS - 1] + _CELL_TRUNCATED_SUFFIX
    return text


def _sorted_paths(paths: Iterable[str]) -> list[str]:
    """叶子路径排序：按层级点分后仍保持稳定输出（便于前端列对齐与快照测试）。"""
    return sorted(paths)


def build_param_diff(
    tasks: Sequence[Task],
    params_by_task: Mapping[str, Any],
) -> dict[str, Any]:
    """构造参数差异矩阵。

    ``params_by_task`` 以 ``str(task.id)`` 为键；缺失的键按「无参数」处理，
    并在响应的 ``missingParams`` 里点名，不静默当成空对象。
    """
    columns = list(tasks)
    task_keys = [str(task.id) for task in columns]
    missing = [key for key in task_keys if key not in params_by_task]

    flat_by_task: dict[str, dict[str, Any]] = {}
    for key in task_keys:
        raw = params_by_task.get(key)
        flat_by_task[key] = flatten_params(raw if raw is not None else {})

    all_paths: set[str] = set()
    for key in task_keys:
        all_paths.update(flat_by_task[key].keys())
    ordered_paths = _sorted_paths(all_paths)

    rows: list[dict[str, Any]] = []
    changes: list[str] = []
    unchanged: list[str] = []

    for path in ordered_paths:
        values: dict[str, Any] = {}
        rendered: dict[str, str] = {}
        presence: dict[str, bool] = {}
        for key in task_keys:
            flat = flat_by_task[key]
            present = path in flat
            presence[key] = present
            values[key] = flat.get(path)
            rendered[key] = _render_cell(values[key], present=present)

        distinct = {canonical_json({"present": presence[key], "value": values[key]}) for key in task_keys}
        is_changed = len(distinct) > 1
        (changes if is_changed else unchanged).append(path)
        rows.append(
            {
                "path": path,
                "changed": is_changed,
                "values": rendered,
                "missing": [key for key in task_keys if not presence[key]],
            }
        )

    return {
        "taskIds": task_keys,
        "taskNames": {key: getattr(task, "name", None) for task, key in zip(columns, task_keys)},
        "columns": [
            {
                "taskId": key,
                "taskName": getattr(task, "name", None),
                "status": getattr(task, "status", None),
                "paramFingerprint": param_fingerprint(params_by_task.get(key)),
            }
            for task, key in zip(columns, task_keys)
        ],
        "rows": rows,
        "changes": changes,
        "unchanged": unchanged,
        "missingParams": missing,
        "identical": not changes,
        "summary": {
            "fieldCount": len(ordered_paths),
            "changedCount": len(changes),
            "unchangedCount": len(unchanged),
        },
        "diffVersion": "param-diff.v1",
    }


async def load_task_params(
    db: AsyncSession, *, task_ids: Sequence[str]
) -> dict[str, Any]:
    """批量取 ``TaskInput.params``，一次查询完成，避免 N+1。"""
    if not task_ids:
        return {}
    result = await db.execute(select(TaskInput).where(TaskInput.task_id.in_(list(task_ids))))
    return {str(row.task_id): row.params for row in result.scalars().all()}


async def load_tasks_by_ids(db: AsyncSession, *, task_ids: Sequence[str]) -> list[Task]:
    """按传入顺序返回任务；缺失的任务不出现在结果里（由调用方判定 404）。"""
    if not task_ids:
        return []
    result = await db.execute(select(Task).where(Task.id.in_(list(task_ids))))
    found = {str(task.id): task for task in result.scalars().all()}
    return [found[key] for key in task_ids if key in found]


__all__ = [
    "MAX_TASKS",
    "MAX_VALUE_CHARS",
    "MIN_TASKS",
    "build_param_diff",
    "canonical_json",
    "flatten_params",
    "load_task_params",
    "load_tasks_by_ids",
    "param_fingerprint",
]
