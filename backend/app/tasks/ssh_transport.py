# backend/app/tasks/ssh_transport.py
"""基于 paramiko 的 SSH/SFTP 传输层。"""

from __future__ import annotations

from dataclasses import dataclass
import os
import posixpath
import stat
import time
from collections.abc import Callable, Iterable
from typing import Any, Dict, Optional

try:
    import paramiko  # type: ignore
except ImportError:  # pragma: no cover - 运行环境兜底
    class _MissingAutoAddPolicy:
        pass

    class _MissingRejectPolicy:
        pass

    class _MissingParamikoModule:
        SSHClient = None
        AutoAddPolicy = _MissingAutoAddPolicy
        RejectPolicy = _MissingRejectPolicy
        SSHException = RuntimeError
        AuthenticationException = RuntimeError

    paramiko = _MissingParamikoModule()  # type: ignore


@dataclass
class SSHCommandResult:
    """远端命令执行结果。"""

    exit_status: int
    stdout: str
    stderr: str


class ParamikoSSHTransport:
    """基于 paramiko 的远端传输与执行封装。"""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        auth_settings: Dict[str, Optional[str]],
        strict_host_key_checking: bool,
        timeout: int,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.auth_settings = auth_settings
        self.strict_host_key_checking = strict_host_key_checking
        self.timeout = timeout
        self.client = None
        self.sftp = None

    def connect(self) -> None:
        """建立 SSH 与 SFTP 连接。"""
        ssh_client_factory = getattr(paramiko, "SSHClient", None)
        if ssh_client_factory is None:
            raise RuntimeError("paramiko is not installed")

        self.client = ssh_client_factory()

        if self.strict_host_key_checking:
            known_hosts_path = self.auth_settings.get("known_hosts_path")
            if known_hosts_path:
                self.client.load_host_keys(known_hosts_path)
            else:
                self.client.load_system_host_keys()
            self.client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: Dict[str, Any] = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
            "timeout": self.timeout,
            "banner_timeout": self.timeout,
            "auth_timeout": self.timeout,
            "look_for_keys": False,
            "allow_agent": False,
        }

        auth_type = self.auth_settings.get("auth_type")
        if auth_type == "password":
            connect_kwargs["password"] = self.auth_settings.get("password")
        else:
            key_path = self.auth_settings.get("key_path")
            if not key_path:
                raise ValueError("Missing key_path for SSH key authentication")
            connect_kwargs["pkey"] = self._load_private_key(key_path)

        self.client.connect(**connect_kwargs)
        self.sftp = self.client.open_sftp()

    def _load_private_key(self, key_path: str):
        """显式加载私钥，避免 paramiko 对 key_filename 的自动探测误判。"""
        key_classes = [
            getattr(paramiko, "RSAKey", None),
            getattr(paramiko, "Ed25519Key", None),
            getattr(paramiko, "ECDSAKey", None),
            getattr(paramiko, "DSSKey", None),
        ]

        errors = []
        for key_class in key_classes:
            if key_class is None:
                continue
            try:
                return key_class.from_private_key_file(key_path)
            except Exception as exc:  # pragma: no cover - 依赖实际 key 类型
                errors.append(f"{key_class.__name__}: {exc}")

        error_message = "; ".join(errors) if errors else "no supported key loaders"
        raise ValueError(f"Failed to load SSH private key '{key_path}': {error_message}")

    def close(self) -> None:
        """关闭连接。"""
        close_error: Exception | None = None
        if self.sftp is not None:
            try:
                self.sftp.close()
            except Exception as exc:
                close_error = exc
            finally:
                self.sftp = None
        if self.client is not None:
            try:
                self.client.close()
            except Exception as exc:
                if close_error is None:
                    close_error = exc
            finally:
                self.client = None

        if close_error is not None:
            raise close_error

    def ensure_dir(self, remote_dir: str) -> None:
        """递归确保远端目录存在。"""
        sftp = self._require_sftp()
        normalized = remote_dir.rstrip("/")
        if not normalized:
            return

        pending_paths = []
        current = normalized
        while current and current not in {"/", "."}:
            pending_paths.append(current)
            current = posixpath.dirname(current)

        for path in reversed(pending_paths):
            try:
                sftp.stat(path)
            except IOError:
                sftp.mkdir(path)

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """上传单个文件。"""
        sftp = self._require_sftp()
        self.ensure_dir(posixpath.dirname(remote_path))
        sftp.put(local_path, remote_path)

    def path_exists(self, remote_path: str) -> bool:
        """检查远端路径是否存在。"""
        try:
            self._require_sftp().stat(remote_path)
        except IOError:
            return False
        return True

    def upload_tree(self, local_dir: str, remote_dir: str) -> None:
        """递归上传目录。"""
        self.ensure_dir(remote_dir)
        for entry_name in os.listdir(local_dir):
            local_path = os.path.join(local_dir, entry_name)
            remote_path = posixpath.join(remote_dir, entry_name)
            if os.path.isdir(local_path):
                self.upload_tree(local_path, remote_path)
            else:
                self.upload_file(local_path, remote_path)

    def download_tree(self, remote_dir: str, local_dir: str) -> None:
        """递归下载目录。"""
        sftp = self._require_sftp()
        os.makedirs(local_dir, exist_ok=True)

        for entry in sftp.listdir_attr(remote_dir):
            remote_path = posixpath.join(remote_dir, entry.filename)
            local_path = os.path.join(local_dir, entry.filename)
            if stat.S_ISDIR(entry.st_mode):
                self.download_tree(remote_path, local_path)
            else:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                sftp.get(remote_path, local_path)

    def run_command(
        self,
        command: str,
        timeout: Optional[int] = None,
        *,
        progress_callback: Callable[[str], None] | None = None,
        progress_log_paths: Iterable[str] | None = None,
        progress_poll_interval: float = 10.0,
    ) -> SSHCommandResult:
        """执行远端命令并返回结果。"""
        client = self._require_client()
        _, stdout, stderr = client.exec_command(command, timeout=timeout or self.timeout)
        channel = stdout.channel
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        log_offsets = {path: 0 for path in (progress_log_paths or [])}
        last_heartbeat = 0.0

        while not channel.exit_status_ready():
            if channel.recv_ready():
                stdout_chunks.append(channel.recv(65536))
            if channel.recv_stderr_ready():
                stderr_chunks.append(channel.recv_stderr(65536))

            if progress_callback:
                emitted_log = False
                for line in self._read_remote_progress_lines(log_offsets):
                    progress_callback(line)
                    emitted_log = True
                now = time.monotonic()
                heartbeat_interval = max(progress_poll_interval, 15.0)
                if not emitted_log and now - last_heartbeat >= heartbeat_interval:
                    progress_callback("远端任务仍在运行，等待模型输出...")
                    last_heartbeat = now

            time.sleep(max(progress_poll_interval, 0.1))

        if progress_callback:
            for line in self._read_remote_progress_lines(log_offsets):
                progress_callback(line)

        exit_status = stdout.channel.recv_exit_status()
        stdout_chunks.append(stdout.read())
        stderr_chunks.append(stderr.read())
        stdout_text = b"".join(stdout_chunks).decode("utf-8", errors="replace")
        stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace")
        return SSHCommandResult(
            exit_status=exit_status,
            stdout=stdout_text,
            stderr=stderr_text,
        )

    def _read_remote_progress_lines(self, log_offsets: dict[str, int]) -> list[str]:
        """读取远端日志新增行。缺失日志不视为错误。"""
        if not log_offsets:
            return []
        sftp = self._require_sftp()
        lines: list[str] = []
        for remote_path, offset in list(log_offsets.items()):
            try:
                size = int(sftp.stat(remote_path).st_size)
            except IOError:
                continue
            if size <= offset:
                continue
            try:
                with sftp.open(remote_path, "rb") as handle:
                    handle.seek(offset)
                    chunk = handle.read(size - offset)
                log_offsets[remote_path] = size
            except IOError:
                continue
            if isinstance(chunk, str):
                text = chunk
            else:
                text = bytes(chunk).decode("utf-8", errors="replace")
            for raw_line in text.replace("\r", "\n").splitlines():
                line = raw_line.strip()
                if line:
                    lines.append(line[:500])
        return lines

    def remove_tree(self, remote_dir: str) -> None:
        """递归删除远端目录。"""
        sftp = self._require_sftp()
        for entry in sftp.listdir_attr(remote_dir):
            remote_path = posixpath.join(remote_dir, entry.filename)
            if stat.S_ISDIR(entry.st_mode):
                self.remove_tree(remote_path)
            else:
                sftp.remove(remote_path)
        sftp.rmdir(remote_dir)

    def _require_client(self):
        if self.client is None:
            raise RuntimeError("SSH client is not connected")
        return self.client

    def _require_sftp(self):
        if self.sftp is None:
            raise RuntimeError("SFTP client is not connected")
        return self.sftp
