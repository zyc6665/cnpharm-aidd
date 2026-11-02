"""SSH 作业凭据解析。"""

import os
import re
from typing import Any

from app.tasks.executors.errors import TaskExecutionError


def _secret_file_path(prefix: str, directory_env: str, ref_name: str) -> str | None:
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", ref_name).upper()
    candidate = os.environ.get(f"{prefix}{suffix}") if prefix else None
    if candidate and os.path.exists(candidate):
        return candidate
    base_dir = os.environ.get(directory_env)
    candidate = os.path.join(base_dir, ref_name) if base_dir else None
    return candidate if candidate and os.path.exists(candidate) else None


def resolve_auth_settings(config: dict[str, Any]) -> dict[str, str | None]:
    auth_type = str(config.get("auth_type", "key")).lower()
    if auth_type not in {"key", "password"}:
        raise TaskExecutionError(f"不支持的 ssh_job auth_type：{auth_type}")
    ref_name = config.get("auth_ref" if auth_type == "key" else "password_ref")
    if not isinstance(ref_name, str) or not ref_name.strip():
        raise TaskExecutionError(f"ssh_job 配置缺少 {'auth_ref' if auth_type == 'key' else 'password_ref'}")
    key_path = password = None
    if auth_type == "key":
        key_path = _secret_file_path("SSH_AUTH_REF_", "SSH_AUTH_REF_DIR", ref_name)
        if not key_path:
            raise TaskExecutionError(f"SSH auth_ref '{ref_name}' 未在 Worker 节点配置", details={"auth_ref": ref_name})
    else:
        suffix = re.sub(r"[^A-Za-z0-9]+", "_", ref_name).upper()
        password = os.environ.get(f"SSH_PASSWORD_REF_{suffix}")
        if not password:
            file_path = _secret_file_path("", "SSH_PASSWORD_REF_DIR", ref_name)
            password = open(file_path, encoding="utf-8").read().strip() if file_path else None
        if not password:
            raise TaskExecutionError(f"SSH password_ref '{ref_name}' 未在 Worker 节点配置", details={"password_ref": ref_name})
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", ref_name).upper()
    known_hosts_path = os.environ.get(f"SSH_KNOWN_HOSTS_{suffix}") or os.environ.get("SSH_KNOWN_HOSTS")
    if known_hosts_path and not os.path.exists(known_hosts_path):
        raise TaskExecutionError(f"SSH known_hosts 文件不存在：{known_hosts_path}")
    return {"auth_type": auth_type, "key_path": key_path, "password": password, "known_hosts_path": known_hosts_path}
