"""paramiko SSH transport 测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class _FakeStream:
    def __init__(self, content: str = "", exit_status: int = 0) -> None:
        self._content = content
        self.channel = self
        self._exit_status = exit_status

    def read(self) -> bytes:
        return self._content.encode("utf-8")

    def recv_exit_status(self) -> int:
        return self._exit_status


class _FakeSSHClient:
    def __init__(self) -> None:
        self.loaded_host_keys: list[str] = []
        self.policy = None
        self.connect_kwargs = None

    def load_host_keys(self, path: str) -> None:
        self.loaded_host_keys.append(path)

    def set_missing_host_key_policy(self, policy) -> None:
        self.policy = policy

    def connect(self, **kwargs) -> None:
        self.connect_kwargs = kwargs

    def open_sftp(self):
        return object()

    def close(self) -> None:
        return None

    def exec_command(self, command: str, timeout: int | None = None):
        return (None, _FakeStream("ok", 0), _FakeStream("", 0))


def test_paramiko_transport_connects_with_password_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """密码认证模式应通过 paramiko 建立 SSH 连接。"""
    from app.tasks import ssh_transport

    fake_client = _FakeSSHClient()

    class FakeAutoAddPolicy:
        pass

    monkeypatch.setattr(ssh_transport.paramiko, "SSHClient", lambda: fake_client)
    monkeypatch.setattr(ssh_transport.paramiko, "AutoAddPolicy", FakeAutoAddPolicy)

    transport = ssh_transport.ParamikoSSHTransport(
        host="10.202.2.228",
        port=22,
        username="zhouyc",
        auth_settings={
            "auth_type": "password",
            "password": "super-secret",
            "known_hosts_path": None,
            "key_path": None,
        },
        strict_host_key_checking=False,
        timeout=30,
    )

    transport.connect()

    assert isinstance(fake_client.policy, FakeAutoAddPolicy)
    assert fake_client.connect_kwargs is not None
    assert fake_client.connect_kwargs["hostname"] == "10.202.2.228"
    assert fake_client.connect_kwargs["port"] == 22
    assert fake_client.connect_kwargs["username"] == "zhouyc"
    assert fake_client.connect_kwargs["password"] == "super-secret"
    assert fake_client.connect_kwargs["look_for_keys"] is False
    assert fake_client.connect_kwargs["allow_agent"] is False


def test_paramiko_transport_connects_with_key_auth_and_known_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """私钥认证模式应加载 known_hosts 并传入已解析的 pkey。"""
    from app.tasks import ssh_transport

    fake_client = _FakeSSHClient()
    fake_key = object()

    class FakeRejectPolicy:
        pass

    class FakeRSAKey:
        @staticmethod
        def from_private_key_file(path: str):
            assert path == "/tmp/id_ed25519"
            return fake_key

    monkeypatch.setattr(ssh_transport.paramiko, "SSHClient", lambda: fake_client)
    monkeypatch.setattr(ssh_transport.paramiko, "RejectPolicy", FakeRejectPolicy)
    monkeypatch.setattr(ssh_transport.paramiko, "RSAKey", FakeRSAKey)

    transport = ssh_transport.ParamikoSSHTransport(
        host="gpu-node-01.internal",
        port=2222,
        username="runner",
        auth_settings={
            "auth_type": "key",
            "key_path": "/tmp/id_ed25519",
            "known_hosts_path": "/tmp/known_hosts",
            "password": None,
        },
        strict_host_key_checking=True,
        timeout=45,
    )

    transport.connect()

    assert fake_client.loaded_host_keys == ["/tmp/known_hosts"]
    assert isinstance(fake_client.policy, FakeRejectPolicy)
    assert fake_client.connect_kwargs is not None
    assert fake_client.connect_kwargs["pkey"] is fake_key
    assert fake_client.connect_kwargs["port"] == 2222
