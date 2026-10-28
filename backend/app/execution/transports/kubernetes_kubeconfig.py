"""Resolve Kubernetes credentials from an operator-provided kubeconfig.

集群内运行时凭证来自 Pod 的 ServiceAccount；但开发与交付验证阶段平台进程跑在集群之外
（Windows 工作站 + 远程 k3s），此时唯一可用的凭证就是运维给的 kubeconfig。本模块把它
解析成与 ``InClusterSecretProvider`` 完全相同的 ``KubernetesCredentials``，因此适配器、
HTTP 传输层与业务代码都不需要知道凭证来自哪里。

刻意不调用 ``kubectl``：平台进程可能不在装有 kubectl 的机器上；而且把凭证交给外部进程
会同时暴露在子进程环境与命令行里（``ps`` 可见）。

只支持 kubeconfig 里的静态凭证（token 或 client-certificate/client-key 或
certificate-authority）。``exec`` 类插件一律拒绝——它会执行任意命令，离线交付环境里
既不可控也无法审计。
"""

from __future__ import annotations

import base64
import binascii
import ssl
import tempfile
from pathlib import Path
from typing import Any

import yaml

from app.execution.adapters.kubernetes import KubernetesCredentials, KubernetesSecretProvider


class KubeconfigError(RuntimeError):
    """Raised when a kubeconfig cannot be turned into usable credentials."""


def _decode(value: str, *, what: str) -> str:
    try:
        return base64.b64decode(value, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise KubeconfigError(f"kubeconfig {what} 不是有效的 base64 文本") from exc


def _inline_or_file(
    entry: dict[str, Any],
    *,
    data_key: str,
    path_key: str,
    base_dir: Path,
    what: str,
) -> str | None:
    """读取 ``*-data``（base64 内联）或 ``*``（文件路径）两种写法。

    kubeconfig 规范允许两种，k3s 生成的用内联，手写的常用路径。生产环境两者都会出现，
    只认一种就会在某台机器上莫名失败。
    """
    inline = entry.get(data_key)
    if isinstance(inline, str) and inline.strip():
        return _decode(inline, what=what)
    relative = entry.get(path_key)
    if isinstance(relative, str) and relative.strip():
        candidate = Path(relative)
        if not candidate.is_absolute():
            candidate = base_dir / candidate
        try:
            return candidate.read_text(encoding="utf-8")
        except OSError as exc:
            raise KubeconfigError(f"kubeconfig 指向的 {what} 文件不可读: {candidate}") from exc
    return None


def _pick(entries: list[dict[str, Any]], name: str, *, kind: str) -> dict[str, Any]:
    for entry in entries:
        if entry.get("name") == name:
            return entry
    raise KubeconfigError(f"kubeconfig 中不存在 {kind}: {name}")


def load_kubeconfig_credentials(
    kubeconfig_path: str | Path,
    *,
    context: str | None = None,
) -> KubernetesCredentials:
    """把一个 kubeconfig 文件解析成可直接投喂传输层的凭证。"""
    path = Path(kubeconfig_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise KubeconfigError(f"kubeconfig 不可读: {path}") from exc
    document = yaml.safe_load(raw) or {}
    if not isinstance(document, dict):
        raise KubeconfigError("kubeconfig 顶层不是映射结构")

    contexts = document.get("contexts") or []
    clusters = document.get("clusters") or []
    users = document.get("users") or []
    context_name = context or document.get("current-context")
    if not context_name:
        raise KubeconfigError("kubeconfig 没有 current-context，且未显式指定 context")

    context_entry = _pick(contexts, context_name, kind="context").get("context") or {}
    cluster_name = context_entry.get("cluster")
    user_name = context_entry.get("user")
    if not cluster_name:
        raise KubeconfigError(f"context {context_name} 未绑定 cluster")

    cluster = _pick(clusters, cluster_name, kind="cluster").get("cluster") or {}
    api_server = cluster.get("server")
    if not isinstance(api_server, str) or not api_server.strip():
        raise KubeconfigError(f"cluster {cluster_name} 缺少 server")

    base_dir = path.parent
    certificate_authority = _inline_or_file(
        cluster,
        data_key="certificate-authority-data",
        path_key="certificate-authority",
        base_dir=base_dir,
        what="certificate-authority",
    )

    token: str | None = None
    client_certificate: str | None = None
    client_key: str | None = None
    if user_name:
        user = _pick(users, user_name, kind="user").get("user") or {}
        if user.get("exec") or user.get("auth-provider"):
            raise KubeconfigError(
                "kubeconfig 使用了 exec/auth-provider 插件，离线交付环境不支持；"
                "请提供静态 token 或 client-certificate"
            )
        raw_token = user.get("token")
        if isinstance(raw_token, str) and raw_token.strip():
            token = raw_token.strip()
        elif isinstance(user.get("tokenFile"), str):
            token_file = Path(user["tokenFile"])
            if not token_file.is_absolute():
                token_file = base_dir / token_file
            try:
                token = token_file.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise KubeconfigError(f"kubeconfig 指向的 tokenFile 不可读: {token_file}") from exc
        client_certificate = _inline_or_file(
            user,
            data_key="client-certificate-data",
            path_key="client-certificate",
            base_dir=base_dir,
            what="client-certificate",
        )
        client_key = _inline_or_file(
            user,
            data_key="client-key-data",
            path_key="client-key",
            base_dir=base_dir,
            what="client-key",
        )

    if not token and not (client_certificate and client_key):
        raise KubeconfigError(
            f"context {context_name} 的 user 既没有 token 也没有完整的 client-certificate/client-key"
        )

    return KubernetesCredentials(
        api_server=api_server.strip(),
        token=token,
        certificate_authority=certificate_authority,
        client_certificate=client_certificate,
        client_key=client_key,
    )


def build_ssl_context(credentials: KubernetesCredentials) -> ssl.SSLContext | bool:
    """按凭证构建 httpx 的 ``verify`` 参数。

    客户端证书**必须**走 ``SSLContext.load_cert_chain``：httpx 0.28.x 的
    ``cert=(crt, key)`` 不会把证书真正发出去，服务端只会看到 ``system:anonymous``，
    错误表现为 403 而不是 TLS 握手失败——非常容易误判成 RBAC 问题。
    """
    context = ssl.create_default_context()
    if credentials.certificate_authority:
        context.load_verify_locations(cadata=credentials.certificate_authority)
    if credentials.client_certificate and credentials.client_key:
        cert_file = _write_temp(credentials.client_certificate, suffix=".crt")
        key_file = _write_temp(credentials.client_key, suffix=".key")
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        _TEMP_FILES.extend([cert_file, key_file])
    return context


_TEMP_FILES: list[str] = []


def _write_temp(content: str, *, suffix: str) -> str:
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    )
    with handle:
        handle.write(content)
    return handle.name


def release_temp_files() -> None:
    """删除 ``build_ssl_context`` 写出的临时证书文件。"""
    while _TEMP_FILES:
        target = _TEMP_FILES.pop()
        try:
            Path(target).unlink(missing_ok=True)
        except OSError:  # pragma: no cover - 清理失败不应影响停机流程
            pass


class KubeconfigSecretProvider(KubernetesSecretProvider):
    """把一个已解析的 kubeconfig 凭证当作唯一合法引用暴露给适配器。"""

    def __init__(self, *, credential_ref: str, credentials: KubernetesCredentials):
        self._credential_ref = credential_ref
        self._credentials = credentials

    async def resolve(self, reference: str) -> KubernetesCredentials:
        if reference != self._credential_ref:
            raise KubeconfigError(f"unexpected Kubernetes credential reference: {reference}")
        return self._credentials
