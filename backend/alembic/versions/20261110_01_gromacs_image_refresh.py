"""gromacs / gmx_mmpbsa 镜像 1.0.1：自由能逐帧列与 MD 的 RMSF/Rg

Revision ID: 20261110_01
Revises: 20261106_02
Create Date: 2026-11-10

镜像内脚本改了两处（`docs/26` H-1 / H-3）：

* `mmpbsa_platform.py` 由「一行汇总」改为逐帧输出 7 列（`frame` / `delta_g_total` /
  `delta_g_vdw` / `delta_g_electrostatic` / `delta_g_polar_solvation` /
  `delta_g_nonpolar_solvation` / `delta_g_sasa`），与前端 `FreeEnergyRow`、mock 包
  契约逐字一致——此前前端按逐帧解析，镜像只给一行，页面恒「暂无可用的自由能数据」。
* `gromacs_platform.py` 补 `gmx gyrate`（Rg，逐帧进 `analysis.csv`）与
  `gmx rmsf -res`（逐残基 RMSF，单独 `rmsf.csv`）——此前 `rmsf_nm`/`rg_nm` 两列
  从来没被算过，MD 结果页两张图恒空。

`tool_versions.config` 里钉的是 `@sha256:` digest，所以镜像重建后必须改这一行，
否则线上跑的还是旧脚本。config 是 JSON，用「旧 digest → 新 digest」的字符串替换，
对 `image`、`tool_package_manifest.runtime.artifacts.{primary,fallback}` 与
`variants[].image` 同时生效，不需要逐个键走。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json

import sqlalchemy as sa
from alembic import op

revision = "20261110_01"
down_revision = "20261106_02"
branch_labels = None
depends_on = None

GRO_MAX_SLUG = "gromacs-md"
MMPBSA_SLUG = "gmx-mmpbsa"

# 旧 digest 是 20261031_16 里钉的那两个；新 digest 来自 2026-11-10 的重建。
NEW_DIGESTS: dict[str, tuple[str, str]] = {
    GRO_MAX_SLUG: (
        "sha256:28f64b63cd573e41684d794aa6f34c615f16e9b340303e9c04eac5e6391cab95",
        "sha256:cee36ec427a4665f2e9aecf0cd7cf96bc313968e0798fa1c0c9282aa28149855",
    ),
    MMPBSA_SLUG: (
        "sha256:d61753513a21ae4909f44611f3f7cc568b1db589f9d8238107928532919e94fb",
        "sha256:9122a4773ed3c2674ec1cc9a4e50ee71e4d76df3c4e1ef787ca0a500c38306ee",
    ),
}

NEW_VERSION = "1.0.1"
NEW_CHANGELOG = (
    "镜像 1.0.1：gmx_MMPBSA 改为逐帧输出 7 列自由能（与前端契约一致）；"
    "GROMACS 补 gmx gyrate（Rg）与 gmx rmsf -res（逐残基 RMSF）"
)


def _load_configs(bind) -> dict[str, tuple[str, str]]:
    rows = bind.execute(
        sa.text(
            "SELECT t.slug, v.id, v.config FROM tools t "
            "JOIN tool_versions v ON v.id = t.current_version_id "
            "WHERE t.slug IN (:a, :b)"
        ),
        {"a": GRO_MAX_SLUG, "b": MMPBSA_SLUG},
    ).all()
    return {str(row[0]): (str(row[1]), _as_json_text(row[2])) for row in rows}


def _as_json_text(value) -> str:
    """把列值归一成 JSON 文本。

    asyncpg 会把 json 列解成 dict，`str(dict)` 得到的是单引号 Python repr，
    再喂回 json 列会报 `invalid input syntax for type json`；SQLite 上本来就是文本。
    """
    if value is None:
        return "{}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _rewrite(bind, mapping: dict[str, tuple[str, str]], *, forward: bool) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # `tool_versions.config` 在 PG 上是 json 列：直接绑字符串会被 asyncpg 当成非法 JSON。
    # SQLite 没有 json 亲和性，CAST 反而会把文本转成数字，故按方言分叉。
    config_expr = (
        "CAST(:config AS json)" if bind.dialect.name == "postgresql" else ":config"
    )
    for slug, (version_id, config) in _load_configs(bind).items():
        old, new = mapping[slug]
        source, target = (old, new) if forward else (new, old)
        if source not in config:
            continue
        bind.execute(
            sa.text(
                f"UPDATE tool_versions SET config = {config_expr}, version = :version, "
                "changelog = :changelog, updated_at = :now WHERE id = :id"
            ),
            {
                "config": config.replace(source, target),
                "version": NEW_VERSION if forward else "1.0.0",
                "changelog": NEW_CHANGELOG if forward else "GROMACS 2024.1 真实模型包",
                "now": now,
                "id": version_id,
            },
        )


def _has_tables(bind) -> bool:
    """``tools`` / ``tool_versions`` 由基线 ``create_all`` 建出；``alembic_version``
    已经越过基线时它们可能并不存在（历史库从中间某个 revision 续跑的场景），
    这时本次改写无事可做，不能直接抛 ``no such table``。
    """
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions"}.issubset(names)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    _rewrite(bind, NEW_DIGESTS, forward=True)


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    _rewrite(bind, NEW_DIGESTS, forward=False)
