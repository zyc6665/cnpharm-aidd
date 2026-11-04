"""配置与 slots.yaml 解析（兼容单节点 / 多节点两种文档形态）。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml


@dataclass(frozen=True)
class SlotConfig:
    node_id: str
    slot_id: str
    device_ids: Tuple[str, ...] = ()
    env: Dict[str, str] = field(default_factory=dict)
    docker_args: Tuple[str, ...] = ()
    models: Tuple[str, ...] = ()
    image: Optional[str] = None
    memory_mb: int = 0


@dataclass(frozen=True)
class NodeConfig:
    node_id: str
    hostname: str
    agent_endpoint: Optional[str]
    accelerator_model: Optional[str]
    accelerator_count: int
    slots: Tuple[SlotConfig, ...]


@dataclass(frozen=True)
class AgentSettings:
    slots_file: str
    platform_base_url: Optional[str]
    report_token: Optional[str]
    api_token: Optional[str]
    host: str
    port: int
    work_root: str
    log_root: str
    docker_bin: str
    report_interval_seconds: int
    node_id_override: Optional[str]
    max_concurrent_jobs: int


def _str(value) -> str:
    return "" if value is None else str(value).strip()


def _tuple_str(value) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return (str(value),)


def load_settings() -> AgentSettings:
    return AgentSettings(
        slots_file=os.environ.get("DRP_SLOTS_FILE", "/etc/drp/slots.yaml"),
        platform_base_url=(os.environ.get("DRP_PLATFORM_BASE_URL") or "").rstrip("/") or None,
        report_token=(os.environ.get("DRP_AGENT_REPORT_TOKEN") or "").strip() or None,
        api_token=(os.environ.get("DRP_AGENT_API_TOKEN") or "").strip() or None,
        host=os.environ.get("DRP_AGENT_HOST", "0.0.0.0"),
        port=int(os.environ.get("DRP_AGENT_PORT", "8780")),
        work_root=os.environ.get("DRP_WORK_ROOT", "/var/drp/work"),
        log_root=os.environ.get("DRP_LOG_ROOT", "/var/drp/logs"),
        docker_bin=os.environ.get("DRP_DOCKER_BIN", "docker"),
        report_interval_seconds=int(os.environ.get("DRP_REPORT_INTERVAL_SECONDS", "15")),
        node_id_override=(os.environ.get("DRP_NODE_ID") or "").strip() or None,
        max_concurrent_jobs=int(os.environ.get("DRP_MAX_CONCURRENT_JOBS", "32")),
    )


def load_nodes(settings: AgentSettings) -> List[NodeConfig]:
    path = Path(os.path.expandvars(settings.slots_file))
    if not path.exists():
        raise FileNotFoundError("slots 文件不存在: %s" % path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("slots 声明必须是对象")
    raw_nodes = payload.get("nodes")
    if raw_nodes is None:
        raw_nodes = [payload]
    nodes: List[NodeConfig] = []
    for raw in raw_nodes:
        node_id = _str(settings.node_id_override or raw.get("nodeId"))
        if not node_id:
            raise ValueError("节点缺少 nodeId")
        accelerator = raw.get("accelerator") or {}
        default_memory = int(accelerator.get("memoryMb") or 0)
        slots: List[SlotConfig] = []
        for item in raw.get("slots") or []:
            slot_id = _str(item.get("id") or item.get("slotId"))
            if not slot_id:
                raise ValueError("卡位缺少 id（node=%s）" % node_id)
            env = {str(k): str(v) for k, v in (item.get("env") or {}).items()}
            slots.append(
                SlotConfig(
                    node_id=node_id,
                    slot_id=slot_id,
                    device_ids=_tuple_str(item.get("deviceIds")),
                    env=env,
                    docker_args=_tuple_str(item.get("dockerArgs")),
                    models=_tuple_str(item.get("models")),
                    image=(_str(item.get("image")) or None),
                    memory_mb=int(item.get("memoryMb") or default_memory or 0),
                )
            )
        if not slots:
            raise ValueError("节点 %s 没有声明卡位" % node_id)
        nodes.append(
            NodeConfig(
                node_id=node_id,
                hostname=_str(raw.get("hostname") or node_id),
                agent_endpoint=(_str(raw.get("agentEndpoint")) or None),
                accelerator_model=(_str(accelerator.get("model")) or None),
                accelerator_count=int(accelerator.get("count") or len(slots)),
                slots=tuple(slots),
            )
        )
    if not nodes:
        raise ValueError("slots 声明为空")
    return nodes
