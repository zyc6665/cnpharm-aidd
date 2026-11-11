"""GROMACS / gmx_MMPBSA 镜像 digest 守护（`docs/26` H-1 / H-3）。

digest 同时出现在两个地方：迁移文件（`20261110_01`）与启动期种数据的 config 里。
只改一处会得到「迁移改了、启动又覆盖回去」或反之——而两种错都不会报错，
只会让线上继续跑旧脚本。这里把两处对齐关系钉成断言。
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
    module = _load_migration_module("20261110_01_gromacs_image_refresh.py")
    specs = _spec_by_slug()

    for slug, (_old, new_digest) in module.NEW_DIGESTS.items():
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
    module = _load_migration_module("20261110_01_gromacs_image_refresh.py")
    specs = _spec_by_slug()

    for slug in module.NEW_DIGESTS:
        spec = specs[slug]
        assert spec.version == module.NEW_VERSION
        assert spec.changelog == module.NEW_CHANGELOG


def test_gromacs_and_mmpbsa_point_at_different_images() -> None:
    specs = _spec_by_slug()
    gromacs = specs["gromacs-md"].config["image"]
    mmpbsa = specs["gmx-mmpbsa"].config["image"]

    assert "/aidd/compute-gromacs@" in gromacs
    assert "/aidd/compute-gmx-mmpbsa@" in mmpbsa
