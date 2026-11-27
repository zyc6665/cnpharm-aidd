"""Vina center coordinates & GROMACS water_model/nsteps schema migration tests."""

from __future__ import annotations

import copy
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
    spec = importlib.util.spec_from_file_location(f"_align_{filename}", _VERSIONS_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seeded_vina_and_gromacs_schemas_include_scientific_updates() -> None:
    specs = {spec.slug: spec for spec in build_platform_tool_specs()}

    vina_cfg = specs["autodock-vina-docking"].config
    for schema in (
        vina_cfg.get("parameters_schema"),
        (vina_cfg.get("tool_package_manifest") or {}).get("parameters_schema"),
    ):
        assert isinstance(schema, dict)
        props = schema["properties"]
        assert {"center_x", "center_y", "center_z"}.issubset(props.keys())
        assert props["center_x"]["type"] == "number"


def test_scientific_schema_alignment_migration_round_trip(tmp_path) -> None:
    vina_prev = _load_migration_module("20261106_01_vina_funnel_tool.py")
    curr_mod = _load_migration_module("20261127_02_tool_schema_scientific_alignment.py")

    db_path = tmp_path / "schema_align.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    vina_seed = {
        "parameters_schema": copy.deepcopy(vina_prev.NEW_SCHEMA),
        "tool_package_manifest": {"parameters_schema": copy.deepcopy(vina_prev.NEW_SCHEMA)},
    }

    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE tools (id TEXT PRIMARY KEY, slug TEXT NOT NULL, current_version_id TEXT)"))
        conn.execute(sa.text("CREATE TABLE tool_versions (id TEXT PRIMARY KEY, config TEXT, updated_at DATETIME)"))
        conn.execute(
            sa.text("INSERT INTO tools (id, slug, current_version_id) VALUES (:tid, :slug, :vid)"),
            {"tid": "t1", "slug": "autodock-vina-docking", "vid": "v1"},
        )
        conn.execute(
            sa.text("INSERT INTO tool_versions (id, config, updated_at) VALUES (:vid, :cfg, :now)"),
            {"vid": "v1", "cfg": json.dumps(vina_seed), "now": now},
        )

        orig_op = curr_mod.op
        curr_mod.op = Operations(MigrationContext.configure(conn))
        try:
            curr_mod.upgrade()
            v_up = json.loads(conn.execute(sa.text("SELECT config FROM tool_versions WHERE id='v1'")).scalar_one())
            assert "center_x" in v_up["parameters_schema"]["properties"]
            assert "center_x" in v_up["tool_package_manifest"]["parameters_schema"]["properties"]

            curr_mod.downgrade()
            v_down = json.loads(conn.execute(sa.text("SELECT config FROM tool_versions WHERE id='v1'")).scalar_one())
            assert "center_x" not in v_down["parameters_schema"]["properties"]
        finally:
            curr_mod.op = orig_op

    engine.dispose()
