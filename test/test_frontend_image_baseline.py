"""Frontend nginx image security baseline tests."""

import re
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"

_NGINX_RUNTIME_RE = re.compile(
    r"^FROM\s+nginx:(?P<version>\d+\.\d+\.\d+)-alpine"
    r"(?:@sha256:[0-9a-f]{64})?\s+AS\s+runtime\s*$",
    re.MULTILINE,
)


def _version_tuple(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch


def test_frontend_runtime_nginx_meets_security_baseline() -> None:
    """前端运行时 nginx 必须满足集团 2026-11-19 预警的修复基线。"""
    dockerfile = (FRONTEND_DIR / "Dockerfile").read_text(encoding="utf-8")
    match = _NGINX_RUNTIME_RE.search(dockerfile)
    assert match, "frontend/Dockerfile 必须定义带版本号的 nginx alpine 运行阶段"

    version = _version_tuple(match.group("version"))
    assert version >= (1, 30, 7), (
        f"nginx {match.group('version')} 低于 1.30.7 修复基线"
    )
    if version[:2] == (1, 31):
        assert version >= (1, 31, 9), "nginx 1.31.x 必须 >= 1.31.9"


def test_frontend_nginx_disables_http2() -> None:
    """HTTP/2 必须在 nginx 配置中显式关闭（漏洞升级前的临时缓解）。"""
    config = (FRONTEND_DIR / "nginx.conf").read_text(encoding="utf-8")

    assert re.search(r"^\s*http2\s+off\s*;\s*$", config, re.MULTILINE)
