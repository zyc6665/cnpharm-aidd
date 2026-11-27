"""GROMACS / gmx_MMPBSA 镜像 digest 与契约守护（`docs/26` H-1/H-3 及 1.1.0 复合物 MD 扩展）。

digest 与输入/参数契约同时出现在迁移文件（`20261110_01` / `20261127_01`）与启动期
种数据中，这里把两处对齐关系钉成断言。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.services.platform_tool_seeding import build_platform_tool_specs

_VERSIONS_DIR = Path(__file__).resolve().parents[1] / "backend" / "alembic" / "versions"


def _load_migration_module(filename: str):
    spec = importlib.util.spec_from_file_location(f"_digest_guard_{filename}", _VERSIONS_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _spec_by_slug() -> dict:
    return {spec.slug: spec for spec in build_platform_tool_specs()}


def test_seeded_configs_pin_the_rebuilt_digests() -> None:
    mmpbsa_mod = _load_migration_module("20261110_01_gromacs_image_refresh.py")
    gromacs_mod = _load_migration_module("20261127_01_gromacs_complex_interactions.py")
    specs = _spec_by_slug()

    expected = {
        "gmx-mmpbsa": mmpbsa_mod.NEW_DIGESTS["gmx-mmpbsa"][1],
        "gromacs-md": gromacs_mod.NEW_DIGEST,
    }
    for slug, new_digest in expected.items():
        config = specs[slug].config
        assert config["image"].endswith(f"@{new_digest}"), f"{slug} 的 image 未指向新 digest"
        manifest = config["tool_package_manifest"]
        for slot in ("primary", "fallback"):
            entry = manifest["runtime"]["artifacts"][slot]
            assert entry["image_digest"] == new_digest, f"{slug}.{slot} 仍钉旧 digest"
            assert entry["image"].endswith(f"@{new_digest}")
        for variant in manifest["variants"]:
            if variant.get("image"):
                assert variant["image"].endswith(f"@{new_digest}"), f"{slug} variant 仍钉旧 digest"


def test_seeded_versions_match_the_migration_changelog() -> None:
    mmpbsa_mod = _load_migration_module("20261110_01_gromacs_image_refresh.py")
    gromacs_mod = _load_migration_module("20261127_01_gromacs_complex_interactions.py")
    specs = _spec_by_slug()

    assert specs["gmx-mmpbsa"].version == mmpbsa_mod.NEW_VERSION
    assert specs["gmx-mmpbsa"].changelog == mmpbsa_mod.NEW_CHANGELOG
    assert specs["gromacs-md"].version == gromacs_mod.NEW_VERSION
    assert specs["gromacs-md"].changelog == gromacs_mod.NEW_CHANGELOG
    manifest = specs["gromacs-md"].config["tool_package_manifest"]
    assert manifest["artifacts"]["inputs"] == gromacs_mod.NEW_INPUTS
    assert manifest["parameters_schema"] == gromacs_mod.NEW_SCHEMA
    assert specs["gromacs-md"].config["parameters_schema"] == gromacs_mod.NEW_SCHEMA


def test_gromacs_and_mmpbsa_point_at_different_images() -> None:
    specs = _spec_by_slug()
    gromacs = specs["gromacs-md"].config["image"]
    mmpbsa = specs["gmx-mmpbsa"].config["image"]

    assert "/aidd/compute-gromacs@" in gromacs
    assert "/aidd/compute-gmx-mmpbsa@" in mmpbsa
