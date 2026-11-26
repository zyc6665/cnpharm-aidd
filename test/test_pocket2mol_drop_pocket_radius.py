"""Pocket2Mol 契约移除 pocket_radius 与迁移往返守护（#172）。"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.services.platform_tool_seeding import build_platform_tool_specs

_VERSIONS_DIR = Path(__file__).resolve().parents[1] / "backend" / "alembic" / "versions"


def _load_migration_module(filename: str):
    spec = importlib.util.spec_from_file_location(f"_p2m_drop_{filename}", _VERSIONS_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seeded_pocket2mol_schema_omits_pocket_radius() -> None:
    module = _load_migration_module("20261125_02_pocket2mol_drop_pocket_radius.py")
    specs = {spec.slug: spec for spec in build_platform_tool_specs()}

    config = specs[module.SLUG].config
    for schema in (
        config.get("parameters_schema"),
        (config.get("tool_package_manifest") or {}).get("parameters_schema"),
    ):
        assert isinstance(schema, dict)
        props = schema["properties"]
        assert "pocket_radius" not in props
        assert set(props.keys()) == {
            "device",
            "num_samples",
            "batch_size",
            "center_x",
            "center_y",
            "center_z",
        }
        assert schema == module.NEW_SCHEMA


def test_drop_pocket_radius_migration_round_trip(tmp_path) -> None:
    prev_mod = _load_migration_module("20261112_01_pocket2mol_batch_and_tool_timeouts.py")
    curr_mod = _load_migration_module("20261125_02_pocket2mol_drop_pocket_radius.py")

    db_path = tmp_path / "p2m_drop_radius.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seeded_config = {
        "parameters_schema": json.loads(json.dumps(prev_mod.NEW_SCHEMA)),
        "tool_package_manifest": {
            "parameters_schema": json.loads(json.dumps(prev_mod.NEW_SCHEMA)),
        },
    }

    with engine.begin() as conn:
        conn.execute(
            sa.text("CREATE TABLE tools (id TEXT PRIMARY KEY, slug TEXT NOT NULL, current_version_id TEXT)")
        )
        conn.execute(
            sa.text(
                "CREATE TABLE tool_versions (id TEXT PRIMARY KEY, config TEXT, updated_at DATETIME)"
            )
        )
        conn.execute(
            sa.text("INSERT INTO tools (id, slug, current_version_id) VALUES ('t1', :slug, 'v1')"),
            {"slug": curr_mod.SLUG},
        )
        conn.execute(
            sa.text("INSERT INTO tool_versions (id, config, updated_at) VALUES ('v1', :cfg, :now)"),
            {"cfg": json.dumps(seeded_config), "now": now},
        )

        orig_op = curr_mod.op
        ctx = MigrationContext.configure(conn)
        curr_mod.op = Operations(ctx)
        try:
            curr_mod.upgrade()
            up_cfg = json.loads(
                conn.execute(sa.text("SELECT config FROM tool_versions WHERE id='v1'")).scalar_one()
            )
            assert "pocket_radius" not in up_cfg["parameters_schema"]["properties"]
            assert "pocket_radius" not in up_cfg["tool_package_manifest"]["parameters_schema"]["properties"]

            curr_mod.downgrade()
            down_cfg = json.loads(
                conn.execute(sa.text("SELECT config FROM tool_versions WHERE id='v1'")).scalar_one()
            )
            assert "pocket_radius" in down_cfg["parameters_schema"]["properties"]
            assert "pocket_radius" in down_cfg["tool_package_manifest"]["parameters_schema"]["properties"]
        finally:
            curr_mod.op = orig_op

    engine.dispose()
