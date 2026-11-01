"""normalize tool package contract identifier to a single version

原来契约主标识带 `.v2` 后缀（`aidd.sciminer/tool-package.v2`），对外会让客户
看到一份"第二版"的迭代痕迹；交付线只有一个版本，主标识统一为
`aidd.sciminer/tool-package`，格式演进由独立的整数字段 `spec_version` 表达。

历史迁移保持原样（已合入的迁移不得修改），由本迁移统一改写已入库的
`tool_versions.config.tool_package_manifest`。

Revision ID: 20261030_02
Revises: 20261030_01
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20261030_02"
down_revision = "20261030_01"
branch_labels = None
depends_on = None

OLD_API_VERSION = "aidd.sciminer/tool-package.v2"
NEW_API_VERSION = "aidd.sciminer/tool-package"
TABLE = "tool_versions"


def _load(config: Any) -> dict[str, Any] | None:
    if isinstance(config, dict):
        return config
    if isinstance(config, str):
        try:
            parsed = json.loads(config)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _normalize(config: dict[str, Any]) -> dict[str, Any] | None:
    changed = False
    for holder in (config.get("tool_package_manifest"),
                   (config.get("tool_package") or {}).get("manifest")
                   if isinstance(config.get("tool_package"), dict) else None):
        if not isinstance(holder, dict):
            continue
        if holder.get("api_version") != OLD_API_VERSION:
            continue
        holder["api_version"] = NEW_API_VERSION
        holder.setdefault("spec_version", 1)
        changed = True
    return config if changed else None


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE not in sa.inspect(bind).get_table_names():
        return
    rows = bind.execute(sa.text(f"SELECT id, config FROM {TABLE}")).fetchall()
    for row_id, raw in rows:
        config = _load(raw)
        if config is None:
            continue
        normalized = _normalize(config)
        if normalized is None:
            continue
        bind.execute(
            sa.text(f"UPDATE {TABLE} SET config = :config WHERE id = :id"),
            {"config": json.dumps(normalized, ensure_ascii=False), "id": row_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    if TABLE not in sa.inspect(bind).get_table_names():
        return
    rows = bind.execute(sa.text(f"SELECT id, config FROM {TABLE}")).fetchall()
    for row_id, raw in rows:
        config = _load(raw)
        if config is None:
            continue
        changed = False
        for holder in (config.get("tool_package_manifest"),
                       (config.get("tool_package") or {}).get("manifest")
                       if isinstance(config.get("tool_package"), dict) else None):
            if not isinstance(holder, dict):
                continue
            if holder.get("api_version") != NEW_API_VERSION:
                continue
            holder["api_version"] = OLD_API_VERSION
            holder.pop("spec_version", None)
            changed = True
        if changed:
            bind.execute(
                sa.text(f"UPDATE {TABLE} SET config = :config WHERE id = :id"),
                {"config": json.dumps(config, ensure_ascii=False), "id": row_id},
            )
