#!/usr/bin/env python3
"""把 SciMiner 模型 bundle 转成标准 Docker 构建上下文。"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = REPOSITORY_ROOT / "deploy" / "kubernetes" / "model-image-template"


def _run_tar_extract(archive: Path, destination: Path) -> None:
    subprocess.run(
        ["tar", "--use-compress-program=unzstd", "-xf", str(archive), "-C", str(destination)],
        check=True,
    )


def _copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.is_symlink() or item.name == "legacy":
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _link_or_copy(source: Path, destination: Path) -> None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.unlink(missing_ok=True)
        destination.hardlink_to(source)
    except OSError:
        shutil.copy2(source, destination)


def _write_pocket2mol_dockerfile(output_dir: Path) -> None:
    (output_dir / "Dockerfile").write_text(
        """ARG BASE_IMAGE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

FROM ${BASE_IMAGE} AS bundle-extractor

WORKDIR /build

RUN apt-get update \\
    && apt-get install --no-install-recommends -y zstd \\
    && rm -rf /var/lib/apt/lists/*

COPY model/environment.tar.zst /build/environment.tar.zst
COPY model/legacy-source.tar.zst /build/legacy-source.tar.zst

RUN mkdir -p /build/env /build/legacy \\
    && tar --use-compress-program=unzstd -xf /build/environment.tar.zst -C /build/env \\
    && tar --use-compress-program=unzstd --strip-components=1 -xf /build/legacy-source.tar.zst -C /build/legacy

FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \\
    PYTHONDONTWRITEBYTECODE=1 \\
    MODEL_PACKAGE_ROOT=/opt/sciminer/model \\
    PLATFORM_ADAPTOR_ROOT=/opt/sciminer/platform_adaptor \\
    PATH=/home/zhuwy/.conda/envs/Pocket2Mol-h100/bin:${PATH} \\
    PLATFORM_PYTHON=/home/zhuwy/.conda/envs/Pocket2Mol-h100/bin/python \\
    POCKET2MOL_MODEL_ROOT=/opt/sciminer/model/legacy \\
    POCKET2MOL_PYTHON=/home/zhuwy/.conda/envs/Pocket2Mol-h100/bin/python \\
    POCKET2MOL_PLATFORM_PYTHON=/home/zhuwy/.conda/envs/Pocket2Mol-h100/bin/python \\
    POCKET2MOL_LEGACY_ENTRYPOINT=/opt/sciminer/model/legacy/platform_run.sh

WORKDIR /opt/sciminer

RUN apt-get update \\
    && apt-get install --no-install-recommends -y ca-certificates tini \\
    && rm -rf /var/lib/apt/lists/* \\
    && mkdir -p /home/zhuwy/.conda/envs /opt/sciminer/model/legacy

COPY --from=bundle-extractor /build/env/Pocket2Mol-h100/ /home/zhuwy/.conda/envs/Pocket2Mol-h100/
COPY --from=bundle-extractor /build/legacy/ /opt/sciminer/model/legacy/
COPY model/MODEL_PACKAGE.yaml /opt/sciminer/model/MODEL_PACKAGE.yaml
COPY model/README.md /opt/sciminer/model/README.md
COPY model/platform_run.sh /opt/sciminer/model/platform_run.sh
COPY model/src /opt/sciminer/model/src
COPY platform_adaptor /opt/sciminer/platform_adaptor

RUN /home/zhuwy/.conda/envs/Pocket2Mol-h100/bin/python -m pip install --no-cache-dir -r /opt/sciminer/platform_adaptor/requirements.txt \\
    && chmod +x /opt/sciminer/model/platform_run.sh /opt/sciminer/model/legacy/platform_run.sh /opt/sciminer/platform_adaptor/*.sh

ENTRYPOINT [\"/usr/bin/tini\", \"--\", \"/opt/sciminer/platform_adaptor/entrypoint.sh\"]
""",
        encoding="utf-8",
    )


def create_context(bundle_dir: Path, output_dir: Path) -> None:
    required = ("code.tar.zst", "env.tar.zst", "platform_overlay.tar.zst", "manifest.json")
    missing = [name for name in required if not (bundle_dir / name).is_file()]
    if missing:
        raise SystemExit(f"模型 bundle 缺少文件: {', '.join(missing)}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"输出目录非空，为避免覆盖已有内容而停止: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATE_ROOT / "README.md", output_dir / "README.template.md")
    shutil.copy2(TEMPLATE_ROOT / ".dockerignore", output_dir / ".dockerignore")
    with tempfile.TemporaryDirectory(prefix="sciminer-model-overlay-") as temporary:
        overlay_root = Path(temporary)
        _run_tar_extract(bundle_dir / "platform_overlay.tar.zst", overlay_root)
        package_root = next(overlay_root.glob("*/"))
        _copy_tree(package_root / "model", output_dir / "model")
        _copy_tree(package_root / "runner", output_dir / "platform_adaptor")
        for name in ("platform_run_v2.sh", "object_storage.py", "requirements.txt"):
            shutil.copy2(
                TEMPLATE_ROOT / "platform_adaptor" / name,
                output_dir / "platform_adaptor" / name,
            )
        _link_or_copy(bundle_dir / "code.tar.zst", output_dir / "model" / "legacy-source.tar.zst")
        _link_or_copy(bundle_dir / "env.tar.zst", output_dir / "model" / "environment.tar.zst")
        shutil.copy2(bundle_dir / "manifest.json", output_dir / "model" / "bundle-manifest.json")
        (output_dir / "README.md").write_text(
            (output_dir / "README.template.md").read_text(encoding="utf-8")
            + "\n\n本目录由 scripts/create_model_image_context.py 根据 Pocket2Mol bundle 生成。\n",
            encoding="utf-8",
        )
    (output_dir / "README.template.md").unlink()
    _write_pocket2mol_dockerfile(output_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    create_context(args.bundle_dir.resolve(), args.output_dir.resolve())
    print(f"已生成标准模型镜像构建上下文: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
