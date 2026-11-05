"""卡位状态机、Docker 生命周期与作业管理。"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import AgentSettings, NodeConfig, SlotConfig

logger = logging.getLogger(__name__)

SLOT_FREE = "FREE"
SLOT_RESERVED = "RESERVED"
SLOT_BUSY = "BUSY"
SLOT_FAULT = "FAULT"

JOB_PENDING = "PENDING"
JOB_RUNNING = "RUNNING"
JOB_SUCCEEDED = "SUCCEEDED"
JOB_FAILED = "FAILED"
JOB_CANCELED = "CANCELED"
JOB_TIMEOUT = "TIMEOUT"
JOB_FAULT = "FAULT"

TERMINAL_JOB_STATES = frozenset(
    {JOB_SUCCEEDED, JOB_FAILED, JOB_CANCELED, JOB_TIMEOUT, JOB_FAULT}
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    job_id: str
    task_id: str
    node_id: str
    slot_id: str
    image: str
    state: str = JOB_PENDING
    container_id: Optional[str] = None
    exit_code: Optional[int] = None
    message: Optional[str] = None
    progress: Optional[float] = None
    created_at: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    max_minutes: Optional[int] = None

    def to_status(self) -> Dict[str, Any]:
        return {
            "jobId": self.job_id,
            "taskId": self.task_id,
            "slotId": self.slot_id,
            "state": self.state,
            "progress": self.progress,
            "message": self.message,
            "exitCode": self.exit_code,
            "deviceCount": 1 if self.container_id else None,
        }


class AgentCore:
    """单进程内维护卡位与作业；Docker 独占由卡位状态串行化保证。"""

    def __init__(self, settings: AgentSettings, nodes: List[NodeConfig]) -> None:
        self.settings = settings
        self.nodes = {node.node_id: node for node in nodes}
        self.node_id = nodes[0].node_id if len(nodes) == 1 else (settings.node_id_override or nodes[0].node_id)
        self._slots: Dict[Tuple[str, str], SlotConfig] = {}
        for node in nodes:
            for slot in node.slots:
                self._slots[(node.node_id, slot.slot_id)] = slot
        self._slot_states: Dict[Tuple[str, str], str] = {key: SLOT_FREE for key in self._slots}
        self._slot_messages: Dict[Tuple[str, str], Optional[str]] = {key: None for key in self._slots}
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.RLock()

    # ── slots ──────────────────────────────────────────────
    def slot_snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            result = []
            for (node_id, slot_id), slot in self._slots.items():
                result.append(
                    {
                        "nodeId": node_id,
                        "slotId": slot_id,
                        "state": self._slot_states[(node_id, slot_id)],
                        "message": self._slot_messages[(node_id, slot_id)],
                        "deviceCount": 1 if self._slot_states[(node_id, slot_id)] == SLOT_BUSY else None,
                    }
                )
            return result

    def _set_slot(self, key: Tuple[str, str], state: str, message: Optional[str] = None) -> None:
        self._slot_states[key] = state
        self._slot_messages[key] = message
        logger.info("slot %s/%s -> %s (%s)", key[0], key[1], state, message or "")

    # ── jobs ───────────────────────────────────────────────
    def submit(self, payload: Dict[str, Any]) -> Job:
        task_id = str(payload.get("taskId") or "").strip()
        slot_id = str(payload.get("slotId") or "").strip()
        image = str(payload.get("image") or "").strip()
        if not task_id or not slot_id or not image:
            raise ValueError("taskId / slotId / image 必填")
        node_id = str(payload.get("nodeId") or self.node_id)
        key = (node_id, slot_id)
        if key not in self._slots:
            raise ValueError("卡位未声明: %s/%s" % (node_id, slot_id))
        with self._lock:
            if self._slot_states[key] != SLOT_FREE:
                raise ValueError("卡位忙: %s/%s (%s)" % (node_id, slot_id, self._slot_states[key]))
            self._set_slot(key, SLOT_RESERVED)
            job = Job(
                job_id=task_id,
                task_id=task_id,
                node_id=node_id,
                slot_id=slot_id,
                image=image,
                created_at=_utcnow(),
                max_minutes=(int(payload["maxMinutes"]) if payload.get("maxMinutes") else None),
            )
            self._jobs[job.job_id] = job
            try:
                work_dir = self._prepare_workdir(job)
                command = self._build_docker_command(job, self._slots[key], payload, work_dir)
                logger.info("docker run: %s", " ".join(command))
                container_id = self._docker(command, capture=True).strip()
                job.container_id = container_id
                job.state = JOB_RUNNING
                job.started_at = _utcnow()
                self._set_slot(key, SLOT_BUSY)
            except Exception as exc:  # noqa: BLE001
                job.state = JOB_FAULT
                job.message = str(exc)
                job.finished_at = _utcnow()
                self._set_slot(key, SLOT_FAULT, str(exc))
                raise
        threading.Thread(target=self._monitor, args=(job,), daemon=True).start()
        return job

    def cancel(self, job_id: str, reason: Optional[str] = None) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError("job 不存在: %s" % job_id)
            if job.state in TERMINAL_JOB_STATES:
                return job
            if job.container_id:
                try:
                    self._docker([self.settings.docker_bin, "stop", job.container_id], capture=True, timeout=60)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("docker stop 失败: %s", exc)
            job.state = JOB_CANCELED
            job.message = reason or "canceled"
            job.finished_at = _utcnow()
            self._set_slot((job.node_id, job.slot_id), SLOT_FREE)
            self._remove_container(job)
            return job

    def status(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError("job 不存在: %s" % job_id)
            return job

    def _monitor(self, job: Job) -> None:
        started = time.time()
        while True:
            time.sleep(2)
            with self._lock:
                if job.state in TERMINAL_JOB_STATES:
                    return
                if job.max_minutes and (time.time() - started) > job.max_minutes * 60:
                    self._terminate(job, JOB_TIMEOUT, "超时 %s 分钟" % job.max_minutes)
                    return
                if not job.container_id:
                    continue
                try:
                    status, exit_code = self._inspect(job.container_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("inspect 失败: %s", exc)
                    continue
                progress = self._read_progress(job)
                if progress is not None:
                    job.progress = progress
                if status in ("exited", "dead"):
                    if exit_code == 0:
                        job.state = JOB_SUCCEEDED
                        job.message = "completed"
                    else:
                        job.state = JOB_FAILED
                        job.message = "exit code %s" % exit_code
                    job.exit_code = exit_code
                    job.finished_at = _utcnow()
                    self._set_slot((job.node_id, job.slot_id), SLOT_FREE)
                    self._remove_container(job)
                    return

    def _terminate(self, job: Job, state: str, message: str) -> None:
        if job.container_id:
            try:
                self._docker([self.settings.docker_bin, "stop", job.container_id], capture=True, timeout=90)
            except Exception as exc:  # noqa: BLE001
                logger.warning("stop 失败: %s", exc)
        job.state = state
        job.message = message
        job.finished_at = _utcnow()
        self._set_slot((job.node_id, job.slot_id), SLOT_FREE)
        self._remove_container(job)

    def _remove_container(self, job: Job) -> None:
        if not job.container_id:
            return
        try:
            self._docker([self.settings.docker_bin, "rm", "-f", job.container_id], capture=True, timeout=30)
        except Exception as exc:  # noqa: BLE001
            logger.debug("rm 失败: %s", exc)

    # ── helpers ────────────────────────────────────────────
    def _prepare_workdir(self, job: Job) -> Path:
        path = Path(self.settings.work_root) / job.node_id / job.slot_id / job.job_id
        (path / "in").mkdir(parents=True, exist_ok=True)
        (path / "out").mkdir(parents=True, exist_ok=True)
        return path

    def _build_docker_command(
        self, job: Job, slot: SlotConfig, payload: Dict[str, Any], work_dir: Path
    ) -> List[str]:
        name = "drp-job-%s" % job.job_id[:32]
        command: List[str] = [self.settings.docker_bin, "run", "-d", "--name", name]
        command.extend(slot.docker_args)
        command.extend(str(arg) for arg in payload.get("dockerArgs") or [])
        env = dict(slot.env)
        env.update({str(k): str(v) for k, v in (payload.get("env") or {}).items()})
        env.setdefault("DRP_SLOT_ID", job.slot_id)
        for key, value in env.items():
            command.extend(["-e", "%s=%s" % (key, value)])
        command.extend(["-v", "%s:/work" % work_dir])
        cache = Path("/var/drp/model-cache")
        if cache.exists():
            command.extend(["-v", "%s:/var/drp/model-cache:ro" % cache])
        command.append(job.image)
        command.extend(str(arg) for arg in payload.get("modelEntry") or [])
        return command

    def _docker(self, args: List[str], capture: bool = False, timeout: int = 60) -> str:
        completed = subprocess.run(
            args,
            check=False,
            timeout=timeout,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.returncode != 0:
            message = (completed.stderr or "").strip() or "docker 退出码 %s" % completed.returncode
            raise RuntimeError("命令失败: %s: %s" % (" ".join(args[:3]), message[:500]))
        return completed.stdout or ""

    def _inspect(self, container_id: str) -> Tuple[str, int]:
        out = self._docker(
            [self.settings.docker_bin, "inspect", "-f", "{{.State.Status}}|{{.State.ExitCode}}", container_id],
            capture=True,
            timeout=20,
        ).strip()
        status, _, code = out.partition("|")
        try:
            exit_code = int(code)
        except ValueError:
            exit_code = -1
        return status, exit_code

    def _read_progress(self, job: Job) -> Optional[float]:
        path = Path(self.settings.work_root) / job.node_id / job.slot_id / job.job_id / "out" / "progress.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pct = data.get("pct")
            return float(pct) if pct is not None else None
        except Exception:  # noqa: BLE001
            return None
