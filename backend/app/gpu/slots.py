"""卡位（slot）注册表：把 ``slots.yaml`` 的静态声明变成平台侧可调度的卡位视图。

依据 `docs/09` §5.5~§5.6 与 `docs/13` §4.1~§4.5：

* **卡位是调度的最小单位**，一个卡位独占一张（或一组）加速卡；平台不做显存共享。
* **卡位互斥不靠一张 slot 表**（`docs/04` 数据模型明确 38 张表里没有 slot 表）：
  互斥由 ``slots.yaml`` 静态声明 + Agent 单队列 + ``gpu_allocations`` 活动租约唯一索引三层共同保证。
  本模块只负责「读声明、记状态、给出可调度视图」，不承担互斥判定。
* ``accelerator.model`` **只做观测展示，不得参与调度判定**（`docs/09` §5.6 迁移纪律 ①）。
* 容器内可见设备序号恒为 0（``DRP_DEVICE=cuda:0``）。``NVIDIA_VISIBLE_DEVICES`` 用宿主卡号、
  ``CUDA_VISIBLE_DEVICES`` 用容器内序号——两者都填宿主卡号会导致 ``torch.cuda.device_count()==0``
  并静默回退 CPU（`docs/09` §5.6 v1.4 实测陷阱）。本模块在加载期就把这种配置拒掉。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from app.common.time import utcnow
from app.config import settings

logger = logging.getLogger(__name__)

SLOT_SCHEMA_VERSION = 2

SLOT_STATE_FREE = "FREE"
SLOT_STATE_RESERVED = "RESERVED"
SLOT_STATE_BUSY = "BUSY"
SLOT_STATE_FAULT = "FAULT"
SLOT_STATE_BORROWED = "BORROWED"

SLOT_STATES: tuple[str, ...] = (
    SLOT_STATE_FREE,
    SLOT_STATE_RESERVED,
    SLOT_STATE_BUSY,
    SLOT_STATE_FAULT,
    SLOT_STATE_BORROWED,
)

# 只有 FREE 能接新任务；BORROWED 在冷却期内不外借（`docs/09` §5.5 状态机）。
SCHEDULABLE_SLOT_STATES: tuple[str, ...] = (SLOT_STATE_FREE,)

# 卡位状态的缓存键前缀：状态权威在 Agent，平台只做缓存与消费。
SLOT_STATE_CACHE_PREFIX = "gpu:slot:state:"

_DCU_DOCKER_ARGS = ("--device=/dev/kfd", "--device=/dev/dri")


class SlotConfigError(ValueError):
    """``slots.yaml`` 声明不合法。"""


@dataclass(frozen=True)
class NodeSlot:
    """一个卡位的静态声明。"""

    node_id: str
    slot_id: str
    ordinal: int
    device_ids: tuple[int, ...]
    env: Mapping[str, str] = field(default_factory=dict)
    docker_args: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    image: str | None = None
    accelerator_model: str | None = None
    accelerator_count: int = 1
    memory_mb: int = 0

    @property
    def identifier(self) -> str:
        """全局唯一的卡位标识，形如 ``node-a/A3``。"""
        return f"{self.node_id}/{self.slot_id}"

    @property
    def vendor(self) -> str:
        """从环境变量推断加速卡厂商（只用于展示与自检，不参与调度判定）。"""
        if "ROCR_VISIBLE_DEVICES" in self.env or "HIP_VISIBLE_DEVICES" in self.env:
            return "haiguang-dcu"
        if "CUDA_VISIBLE_DEVICES" in self.env or "NVIDIA_VISIBLE_DEVICES" in self.env:
            return "nvidia-cuda"
        return "unknown"

    @property
    def gpu_index(self) -> int:
        """平台内部把卡位当成一个「设备」占位。

        优先用宿主卡号（与既有 ``gpu_allocations.gpu_index`` 语义一致），
        未声明设备号时退化为卡位序号，保证 ``(gpu_node_id, gpu_index)`` 仍然唯一。
        """
        if self.device_ids:
            return self.device_ids[0]
        return self.ordinal

    @property
    def visible_device(self) -> str | None:
        """容器内看到的设备序号（必须是 ``0``）。"""
        return self.env.get("CUDA_VISIBLE_DEVICES") or self.env.get("ROCR_VISIBLE_DEVICES")

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodeId": self.node_id,
            "slotId": self.slot_id,
            "identifier": self.identifier,
            "ordinal": self.ordinal,
            "deviceIds": list(self.device_ids),
            "env": dict(self.env),
            "dockerArgs": list(self.docker_args),
            "models": list(self.models),
            "image": self.image,
            "acceleratorModel": self.accelerator_model,
            "acceleratorCount": self.accelerator_count,
            "memoryMb": self.memory_mb,
            "vendor": self.vendor,
            "gpuIndex": self.gpu_index,
            "visibleDevice": self.visible_device,
        }


@dataclass(frozen=True)
class RegisteredNode:
    """一台声明了卡位的计算节点。"""

    node_id: str
    hostname: str
    accelerator_model: str | None
    accelerator_count: int
    slots: tuple[NodeSlot, ...]
    agent_endpoint: str | None = None

    def slot(self, slot_id: str) -> NodeSlot | None:
        for slot in self.slots:
            if slot.slot_id == slot_id:
                return slot
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodeId": self.node_id,
            "hostname": self.hostname,
            "acceleratorModel": self.accelerator_model,
            "acceleratorCount": self.accelerator_count,
            "agentEndpoint": self.agent_endpoint,
            "slotCount": len(self.slots),
        }


@dataclass(frozen=True)
class SlotRegistry:
    """一份完整的卡位声明（可能包含多台节点）。"""

    nodes: tuple[RegisteredNode, ...] = ()
    schema_version: int = SLOT_SCHEMA_VERSION
    source: str = "empty"

    def node(self, node_id: str) -> RegisteredNode | None:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    @property
    def slots(self) -> tuple[NodeSlot, ...]:
        return tuple(slot for node in self.nodes for slot in node.slots)

    def find(self, node_id: str, slot_id: str) -> NodeSlot | None:
        node = self.node(node_id)
        return node.slot(slot_id) if node else None

    def find_by_identifier(self, identifier: str) -> NodeSlot | None:
        node_id, _, slot_id = identifier.partition("/")
        if not slot_id:
            return None
        return self.find(node_id, slot_id)

    def slots_for_model(self, model_slug: str) -> tuple[NodeSlot, ...]:
        """声明里显式点名了该模型的卡位。

        卡位不点名模型时视为通用卡位（``models`` 为空），一并返回——这是
        「静态声明 + 镜像即契约」的默认口径，避免每接一个模型就要改一次 slots.yaml。
        """
        slug = (model_slug or "").strip()
        return tuple(
            slot
            for slot in self.slots
            if not slot.models or (slug and slug in slot.models)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "source": self.source,
            "nodes": [node.to_dict() for node in self.nodes],
            "slots": [slot.to_dict() for slot in self.slots],
        }


def _normalize_device_ids(raw: Any) -> tuple[int, ...]:
    if raw is None:
        return ()
    if isinstance(raw, bool):
        raise SlotConfigError("deviceIds 不能是布尔值")
    if isinstance(raw, int):
        return (int(raw),)
    if isinstance(raw, str):
        parts = [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]
        return tuple(int(item) for item in parts)
    if isinstance(raw, Iterable):
        return tuple(int(item) for item in raw)
    raise SlotConfigError(f"deviceIds 不支持的类型: {type(raw).__name__}")


def _string_mapping(raw: Any) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _string_tuple(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, Iterable):
        return tuple(str(item) for item in raw)
    return ()


def _uses_gpu_flag(docker_args: tuple[str, ...]) -> bool:
    for index, item in enumerate(docker_args):
        if item == "--gpus":
            return True
        if item.startswith("--gpus="):
            return True
        if item.startswith("--runtime") and index + 1 < len(docker_args):
            return docker_args[index + 1].strip() == "nvidia"
    return False


def _validate_visible_device_contract(
    *,
    identifier: str,
    env: Mapping[str, str],
    docker_args: tuple[str, ...],
) -> None:
    """拦住会让容器看不到卡的配置组合（`docs/09` §5.6 v1.4 实测陷阱）。

    实测矩阵：``--gpus device=3`` + ``CUDA_VISIBLE_DEVICES=3`` → ``device_count()==0``（静默回退 CPU）；
    ``--gpus device=3`` + ``CUDA_VISIBLE_DEVICES=0`` → 1；``--gpus device=3``（不设 CVD）→ 1。
    因此只要用了 ``--gpus``，容器内序号就必须是 0 或干脆不设。
    """
    if not _uses_gpu_flag(docker_args):
        return
    visible = env.get("CUDA_VISIBLE_DEVICES")
    if visible is None:
        return
    normalized = visible.strip()
    if normalized in {"", "0", "all"}:
        return
    raise SlotConfigError(
        f"卡位 {identifier} 的 CUDA_VISIBLE_DEVICES={visible!r} 与 --gpus 同时使用会退回 CPU；"
        "容器内序号必须是 0 或不设置（docs/09 §5.6 v1.4 实测陷阱）"
    )


def _validate_dcu_mounts(*, identifier: str, env: Mapping[str, str], docker_args: tuple[str, ...]) -> None:
    """DCU 卡位必须挂驱动设备节点，否则容器内看不到加速卡。"""
    if "ROCR_VISIBLE_DEVICES" not in env:
        return
    missing = [item for item in _DCU_DOCKER_ARGS if item not in docker_args]
    if missing:
        raise SlotConfigError(
            f"卡位 {identifier} 声明了 ROCR_VISIBLE_DEVICES，但 dockerArgs 缺少 {missing}"
        )


def _parse_slot(node_id: str, ordinal: int, raw: Mapping[str, Any], *, defaults: Mapping[str, Any]) -> NodeSlot:
    slot_id = str(raw.get("id") or "").strip()
    if not slot_id:
        raise SlotConfigError(f"节点 {node_id} 的第 {ordinal + 1} 个卡位缺少 id")

    merged_env = {**_string_mapping(defaults.get("env")), **_string_mapping(raw.get("env"))}
    docker_args = _string_tuple(defaults.get("dockerArgs")) + _string_tuple(raw.get("dockerArgs"))
    identifier = f"{node_id}/{slot_id}"

    _validate_visible_device_contract(identifier=identifier, env=merged_env, docker_args=docker_args)
    _validate_dcu_mounts(identifier=identifier, env=merged_env, docker_args=docker_args)

    memory_mb = raw.get("memoryMb") or defaults.get("memoryMb") or 0
    return NodeSlot(
        node_id=node_id,
        slot_id=slot_id,
        ordinal=ordinal,
        device_ids=_normalize_device_ids(raw.get("deviceIds")),
        env=merged_env,
        docker_args=docker_args,
        models=_string_tuple(raw.get("models")),
        image=(str(raw.get("image")).strip() or None) if raw.get("image") else None,
        accelerator_model=str(raw.get("acceleratorModel") or defaults.get("acceleratorModel") or "").strip() or None,
        accelerator_count=int(raw.get("acceleratorCount") or defaults.get("acceleratorCount") or 1),
        memory_mb=max(int(memory_mb or 0), 0),
    )


def parse_slot_document(payload: Any, *, source: str = "inline") -> SlotRegistry:
    """把 ``slots.yaml`` 解析后的结构转成 :class:`SlotRegistry`。

    支持两种文档形态：

    * 单节点：``{schemaVersion, nodeId, accelerator, slots: [...]}``
    * 多节点：``{schemaVersion, nodes: [{nodeId, ...}]}``
    """
    if not isinstance(payload, Mapping):
        raise SlotConfigError("slots 声明必须是对象")

    schema_version = int(payload.get("schemaVersion") or SLOT_SCHEMA_VERSION)
    if schema_version != SLOT_SCHEMA_VERSION:
        raise SlotConfigError(f"不支持的 slots schemaVersion: {schema_version}")

    if "nodes" in payload:
        node_payloads = payload.get("nodes") or []
        if not isinstance(node_payloads, Iterable) or isinstance(node_payloads, (str, bytes)):
            raise SlotConfigError("nodes 必须是数组")
    else:
        node_payloads = [payload]

    nodes: list[RegisteredNode] = []
    for node_raw in node_payloads:
        if not isinstance(node_raw, Mapping):
            raise SlotConfigError("节点声明必须是对象")
        node_id = str(node_raw.get("nodeId") or "").strip()
        if not node_id:
            raise SlotConfigError("节点缺少 nodeId")

        accelerator = node_raw.get("accelerator") or {}
        if not isinstance(accelerator, Mapping):
            raise SlotConfigError(f"节点 {node_id} 的 accelerator 必须是对象")

        defaults = {
            "acceleratorModel": accelerator.get("model"),
            "acceleratorCount": accelerator.get("count"),
            "memoryMb": accelerator.get("memoryMb"),
        }
        slots_raw = node_raw.get("slots") or []
        if not isinstance(slots_raw, Iterable) or isinstance(slots_raw, (str, bytes)):
            raise SlotConfigError(f"节点 {node_id} 的 slots 必须是数组")

        slots = tuple(
            _parse_slot(node_id, ordinal, raw, defaults=defaults)
            for ordinal, raw in enumerate(slots_raw)
            if isinstance(raw, Mapping)
        )
        if not slots:
            raise SlotConfigError(f"节点 {node_id} 没有声明任何卡位")

        seen: set[str] = set()
        for slot in slots:
            if slot.slot_id in seen:
                raise SlotConfigError(f"节点 {node_id} 的卡位 id 重复: {slot.slot_id}")
            seen.add(slot.slot_id)

        nodes.append(
            RegisteredNode(
                node_id=node_id,
                hostname=str(node_raw.get("hostname") or node_id),
                accelerator_model=(
                    str(accelerator.get("model")).strip() or None if accelerator.get("model") else None
                ),
                accelerator_count=int(accelerator.get("count") or len(slots)),
                slots=slots,
                agent_endpoint=(
                    str(node_raw.get("agentEndpoint")).strip() or None
                    if node_raw.get("agentEndpoint")
                    else None
                ),
            )
        )

    return SlotRegistry(nodes=tuple(nodes), schema_version=schema_version, source=source)


def _read_raw_configuration() -> tuple[str | None, str]:
    """按「内联字符串 > 文件路径」的优先级读取声明。"""
    inline = getattr(settings, "DRP_NODE_SLOTS_YAML", None)
    if inline and str(inline).strip():
        return str(inline), "settings:DRP_NODE_SLOTS_YAML"

    file_setting = getattr(settings, "DRP_NODE_SLOTS_FILE", None)
    if file_setting and str(file_setting).strip():
        path = Path(os.path.expandvars(str(file_setting)))
        if not path.exists():
            raise SlotConfigError(f"DRP_NODE_SLOTS_FILE 指向的文件不存在: {path}")
        return path.read_text(encoding="utf-8"), f"file:{path}"

    return None, "empty"


def load_slot_registry(raw: str | None = None) -> SlotRegistry:
    """加载卡位声明；未配置时返回空注册表（不抛错，保证无卡位节点也能启动）。"""
    source = "argument"
    if raw is None:
        raw, source = _read_raw_configuration()
    if raw is None or not str(raw).strip():
        return SlotRegistry()
    payload = yaml.safe_load(str(raw))
    return parse_slot_document(payload, source=source)


def _state_cache_key(node_id: str, slot_id: str) -> str:
    return f"{SLOT_STATE_CACHE_PREFIX}{node_id}:{slot_id}"


async def record_slot_state(
    *,
    node_id: str,
    slot_id: str,
    state: str,
    message: str | None = None,
    device_count: int | None = None,
    cache_client: Any = None,
) -> dict[str, Any]:
    """登记 Agent 上报的卡位状态（缓存，TTL 由 ``DRP_SLOT_STATE_TTL_SECONDS`` 控制）。

    状态权威在 Agent；平台这一层只是「消费并展示 + 参与调度决策」。
    ``device_count`` 来自 Agent 就绪自检 ``torch.cuda.device_count()``，不等于 1 时置 FAULT。
    """
    normalized = str(state or "").strip().upper()
    if normalized not in SLOT_STATES:
        raise SlotConfigError(f"不支持的卡位状态: {state}")

    if device_count is not None and device_count != 1:
        # 卡位验收铁律：容器内必须恰好看到 1 张卡（docs/09 §5.6 迁移纪律 ⑤）。
        normalized = SLOT_STATE_FAULT
        message = message or f"容器内 device_count()={device_count}，卡位验收失败"

    record = {
        "nodeId": node_id,
        "slotId": slot_id,
        "state": normalized,
        "message": message,
        "deviceCount": device_count,
        "updatedAt": utcnow().isoformat(),
    }

    cache = cache_client
    if cache is None:
        from app.cache import get_cache

        cache = get_cache()
    ttl = int(getattr(settings, "DRP_SLOT_STATE_TTL_SECONDS", 120) or 120)
    await cache.set(_state_cache_key(node_id, slot_id), record, expire=ttl)
    return record


async def load_slot_states(
    registry: SlotRegistry,
    *,
    cache_client: Any = None,
) -> dict[str, dict[str, Any]]:
    """读取所有已声明卡位的当前状态，未上报过的按 FREE 处理。"""
    if not registry.slots:
        return {}

    cache = cache_client
    if cache is None:
        from app.cache import get_cache

        cache = get_cache()

    states: dict[str, dict[str, Any]] = {}
    for slot in registry.slots:
        record = await cache.get(_state_cache_key(slot.node_id, slot.slot_id))
        if isinstance(record, Mapping) and record.get("state") in SLOT_STATES:
            states[slot.identifier] = dict(record)
        else:
            states[slot.identifier] = {
                "nodeId": slot.node_id,
                "slotId": slot.slot_id,
                "state": SLOT_STATE_FREE,
                "message": None,
                "deviceCount": None,
                "updatedAt": None,
            }
    return states


def slot_view(
    registry: SlotRegistry,
    states: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """节点 + 卡位 + 状态的可展示视图（`docs/06` P-36 算力与队列页的数据源）。"""
    view: list[dict[str, Any]] = []
    for node in registry.nodes:
        slots: list[dict[str, Any]] = []
        for slot in node.slots:
            record = states.get(slot.identifier) or {}
            state = str(record.get("state") or SLOT_STATE_FREE)
            slots.append(
                {
                    **slot.to_dict(),
                    "state": state,
                    "schedulable": state in SCHEDULABLE_SLOT_STATES,
                    "stateMessage": record.get("message"),
                    "deviceCount": record.get("deviceCount"),
                    "stateUpdatedAt": record.get("updatedAt"),
                }
            )
        view.append(
            {
                **node.to_dict(),
                "slots": slots,
                "schedulableSlotCount": sum(1 for slot in slots if slot["schedulable"]),
            }
        )
    return view


async def schedulable_node_view(
    registry: SlotRegistry,
    *,
    cache_client: Any = None,
) -> list[dict[str, Any]]:
    """给分配器用的节点视图，形状与既有 ``_get_available_nodes`` 保持一致。

    只返回 FREE 卡位；``gpus[i]["index"]`` 是宿主卡号，``gpus[i]["slotId"]`` 是卡位号。
    """
    states = await load_slot_states(registry, cache_client=cache_client)
    nodes: list[dict[str, Any]] = []
    for node in registry.nodes:
        gpus: list[dict[str, Any]] = []
        for slot in node.slots:
            record = states.get(slot.identifier) or {}
            if str(record.get("state") or SLOT_STATE_FREE) not in SCHEDULABLE_SLOT_STATES:
                continue
            gpus.append(
                {
                    "index": slot.gpu_index,
                    "name": slot.accelerator_model or node.accelerator_model or "",
                    "total_memory_mb": slot.memory_mb,
                    "free_memory_mb": slot.memory_mb,
                    "slot_id": slot.slot_id,
                    "slot_identifier": slot.identifier,
                    "device_ids": list(slot.device_ids),
                    "accelerator_model": slot.accelerator_model or node.accelerator_model,
                    "agent_endpoint": node.agent_endpoint,
                    "image": slot.image,
                    "models": list(slot.models),
                }
            )
        if not gpus:
            continue
        nodes.append(
            {
                "id": node.node_id,
                "hostname": node.hostname,
                "gpu_count": len(gpus),
                "source": "slots",
                "agent_endpoint": node.agent_endpoint,
                "gpus": gpus,
            }
        )
    return nodes


def describe_registry(registry: SlotRegistry) -> str:
    """一行摘要，方便启动日志与排障。"""
    if not registry.nodes:
        return "卡位声明为空（未配置 DRP_NODE_SLOTS_YAML / DRP_NODE_SLOTS_FILE）"
    return json.dumps(
        {
            "source": registry.source,
            "schemaVersion": registry.schema_version,
            "nodes": [node.to_dict() for node in registry.nodes],
            "slotCount": len(registry.slots),
        },
        ensure_ascii=False,
    )


__all__ = [
    "NodeSlot",
    "RegisteredNode",
    "SCHEDULABLE_SLOT_STATES",
    "SLOT_SCHEMA_VERSION",
    "SLOT_STATES",
    "SLOT_STATE_BORROWED",
    "SLOT_STATE_BUSY",
    "SLOT_STATE_FAULT",
    "SLOT_STATE_FREE",
    "SLOT_STATE_RESERVED",
    "SlotConfigError",
    "SlotRegistry",
    "describe_registry",
    "load_slot_registry",
    "load_slot_states",
    "parse_slot_document",
    "record_slot_state",
    "schedulable_node_view",
    "slot_view",
]
