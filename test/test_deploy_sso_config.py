"""G-03：部署清单必须列全 SSO 配置。

只做静态断言——CI 里没有 docker/kubectl，任何「起一个容器看看」的写法都跑不了。
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = PROJECT_ROOT / "deploy" / "compose" / "docker-compose.prod.yml"
COMPOSE_README = PROJECT_ROOT / "deploy" / "compose" / "README.md"
K8S_README = PROJECT_ROOT / "deploy" / "kubernetes" / "README.md"

SSO_KEYS = (
    "SSO_ENABLED",
    "SSO_AUTO_PROVISION",
    "SSO_ALLOWED_UNIT_CODES",
    "SSO_BASE_URL",
    "SSO_APP_ID",
    "SSO_CLIENT_SECRET",
    "SSO_REDIRECT_URI",
    "SSO_SUCCESS_PATH",
    "SSO_DEFAULT_ROLE",
    "SSO_USERNAME_CLAIM",
    "SSO_VALIDATE_ON_REFRESH",
    "SSO_TIMEOUT_SECONDS",
    "SSO_TLS_VALIDATE",
    "SSO_STATE_TTL_SECONDS",
    "SSO_OFFLINE_GRACE_SECONDS",
    "SSO_LOGOUT_REDIRECT_URI",
)


def test_prod_compose_lists_all_sso_keys():
    text = COMPOSE.read_text(encoding="utf-8")
    missing = [key for key in SSO_KEYS if f"      {key}:" not in text]
    assert missing == []
    # 部署层默认值必须是 false：漏配时越权开户的代价远大于登不进去。
    line = next(
        row for row in text.splitlines() if row.strip().startswith("SSO_AUTO_PROVISION:")
    )
    assert "${SSO_AUTO_PROVISION:-false}" in line


def test_prod_compose_keeps_single_key_required():
    """单键仍是必填（`:?`）：轮换列表是「多一个选择」，不是取消原约束。"""
    text = COMPOSE.read_text(encoding="utf-8")
    assert "SETTINGS_ENCRYPTION_KEY: ${SETTINGS_ENCRYPTION_KEY:?" in text
    assert "SETTINGS_ENCRYPTION_KEYS: ${SETTINGS_ENCRYPTION_KEYS:-}" in text


def test_sso_block_stays_offline():
    """只看新增的 SSO 行：整个文件本就有 healthcheck 的 localhost，不能整文件断言。"""
    text = COMPOSE.read_text(encoding="utf-8")
    rows = [
        row
        for row in text.splitlines()
        if re.match(r"^\s+(SSO_[A-Z_]+|SETTINGS_ENCRYPTION_KEYS):", row)
    ]
    assert len(rows) == len(SSO_KEYS) + 1
    for row in rows:
        for forbidden in ("http://", "https://", ".com", ".cn"):
            assert forbidden not in row, row


def test_readmes_document_injection_list():
    compose_doc = COMPOSE_README.read_text(encoding="utf-8")
    assert "对所有 SSO 登录生效" in compose_doc
    # 逐项核对，而不是抽查两三个键：漏一个键的文档等于让运维上线时缺配置。
    assert [key for key in SSO_KEYS if key not in compose_doc] == []

    k8s_doc = K8S_README.read_text(encoding="utf-8")
    assert [key for key in SSO_KEYS if key not in k8s_doc] == []
    assert "SETTINGS_ENCRYPTION_KEYS" in k8s_doc
