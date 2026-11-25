"""Pocket2Mol 增量适配镜像 digest 与迁移对齐守护。"""

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
    spec = importlib.util.spec_from_file_location(f"_p2m_digest_{filename}", _VERSIONS_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seeded_config_pins_rebuilt_adaptor_digest() -> None:
    module = _load_migration_module("20261125_01_pocket2mol_adaptor_digest.py")
    specs = {spec.slug: spec for spec in build_platform_tool_specs()}

    spec = specs[module.SLUG]
    config = spec.config
    assert config["image"].endswith(f"@{module.NEW_DIGEST}")
    manifest = config["tool_package_manifest"]
    for slot in ("primary", "fallback"):
        entry = manifest["runtime"]["artifacts"][slot]
        assert entry["image_digest"] == module.NEW_DIGEST
        assert entry["image"].endswith(f"@{module.NEW_DIGEST}")
    for variant in manifest["variants"]:
        if variant.get("image"):
            assert variant["image"].endswith(f"@{module.NEW_DIGEST}")
    assert spec.changelog == module.NEW_CHANGELOG


def test_migration_upgrade_and_downgrade_round_trip(tmp_path) -> None:
    prev_mod = _load_migration_module("20261112_01_pocket2mol_batch_and_tool_timeouts.py")
    curr_mod = _load_migration_module("20261125_01_pocket2mol_adaptor_digest.py")

    db_path = tmp_path / "p2m_mig.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seeded_config = {
        "image": f"10.202.2.228:30500/aidd/compute-pocket2mol@{curr_mod.OLD_DIGEST}",
        "tool_package_manifest": {
            "runtime": {
                "artifacts": {
                    "primary": {
                        "image": f"10.202.2.228:30500/aidd/compute-pocket2mol@{curr_mod.OLD_DIGEST}",
                        "image_digest": curr_mod.OLD_DIGEST,
                    },
                    "fallback": {
                        "image": f"10.202.2.228:30500/aidd/compute-pocket2mol@{curr_mod.OLD_DIGEST}",
                        "image_digest": curr_mod.OLD_DIGEST,
                    },
                }
            },
            "variants": [
                {"name": "default", "image": f"10.202.2.228:30500/aidd/compute-pocket2mol@{curr_mod.OLD_DIGEST}"}
            ],
        },
    }

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE tools (id TEXT PRIMARY KEY, slug TEXT NOT NULL, current_version_id TEXT)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE tool_versions "
                "(id TEXT PRIMARY KEY, version TEXT, changelog TEXT, config TEXT, updated_at DATETIME)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO tools (id, slug, current_version_id) VALUES ('t1', :slug, 'v1')"
            ),
            {"slug": curr_mod.SLUG},
        )
        conn.execute(
            sa.text(
                "INSERT INTO tool_versions (id, version, changelog, config, updated_at) "
                "VALUES ('v1', :ver, :cl, :cfg, :now)"
            ),
            {
                "ver": prev_mod.NEW_VERSION,
                "cl": curr_mod.OLD_CHANGELOG,
                "cfg": json.dumps(seeded_config),
                "now": now,
            },
        )

        orig_op = curr_mod.op
        ctx = MigrationContext.configure(conn)
        curr_mod.op = Operations(ctx)
        try:
            curr_mod.upgrade()
            row_up = conn.execute(sa.text("SELECT config, changelog FROM tool_versions WHERE id='v1'")).one()
            assert curr_mod.NEW_DIGEST in row_up[0]
            assert curr_mod.OLD_DIGEST not in row_up[0]
            assert row_up[1] == curr_mod.NEW_CHANGELOG

            curr_mod.downgrade()
            row_down = conn.execute(sa.text("SELECT config, changelog FROM tool_versions WHERE id='v1'")).one()
            assert curr_mod.OLD_DIGEST in row_down[0]
            assert curr_mod.NEW_DIGEST not in row_down[0]
            assert row_down[1] == curr_mod.OLD_CHANGELOG
        finally:
            curr_mod.op = orig_op

    engine.dispose()
