"""守护「模型镜像构建与权重外置」这套约定（docs/19）。

这些断言看起来琐碎，但每一条都对应一个真实踩过的坑：

- `--model-root` 探测：模板无条件传该参数时，遗留模型的入口脚本会以
  `Unknown argument: --model-root`、退出码 2 失败。这条容易被「改回原样」而不自知。
- 权重不进镜像：一旦有人把 `new_best/` 拷进构建上下文，镜像从 6 GB 变 25 GB，
  而 build 仍然"成功"，只有推送时才被发现。
- `mountPath` 与 Dockerfile 里的空目录必须一致：不一致的话挂载点不存在，
  k8s 会把这个 hostPath 挂到一个自动创建的目录上，模型读到空目录后失败在很后面。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ADAPTOR = ROOT / "deploy" / "kubernetes" / "model-image-template" / "platform_adaptor"
MODEL_IMAGES = ROOT / "deploy" / "model-images"
LVPOCKET = MODEL_IMAGES / "lvpocket"


def test_platform_run_v2_probes_model_root_support() -> None:
    """模板必须探测模型入口是否支持 --model-root，而不是无条件传。"""
    source = (TEMPLATE_ADAPTOR / "platform_run_v2.sh").read_text(encoding="utf-8")

    assert "MODEL_ROOT_ARGS=()" in source
    assert "grep -q -- '--model-root)' /opt/sciminer/model/platform_run.sh" in source
    assert '${MODEL_ROOT_ARGS[@]+"${MODEL_ROOT_ARGS[@]}"}' in source
    # 无条件传的写法必须已经不存在（否则探测就是摆设）
    assert '\n  --model-root "${MODEL_PACKAGE_ROOT:-/opt/sciminer/model}" \\\n' not in source


def test_model_images_readme_documents_weight_externalisation() -> None:
    readme = (MODEL_IMAGES / "README.md").read_text(encoding="utf-8")

    assert "权重不进镜像" in readme
    assert "digest" in readme
    assert "runtime.weights" in readme


def test_lvpocket_weights_manifest_matches_dockerfile_mountpoint() -> None:
    spec = json.loads((LVPOCKET / "weights.json").read_text(encoding="utf-8"))
    dockerfile = (LVPOCKET / "Dockerfile").read_text(encoding="utf-8")

    mount_points = [item["mountPath"] for item in spec["weights"]]
    assert mount_points == ["/opt/sciminer/model/new_best"]
    for mount_point in mount_points:
        assert f"mkdir -p {mount_point}" in dockerfile, (
            f"Dockerfile 必须为 {mount_point} 建好空目录作为挂载点"
        )
    for item in spec["weights"]:
        assert item["readOnly"] is True, "权重必须只读挂载，模型不应有机会改权重"
        assert item["source"]["kind"] in {"host-path", "object-store"}
        assert item["cache"]["kind"] == "host-path"


def test_lvpocket_weights_manifest_pins_image_by_digest() -> None:
    """镜像必须用 @sha256: 不可变引用（docs/07 §3.6，manifest 生成器会强校验）。"""
    spec = json.loads((LVPOCKET / "weights.json").read_text(encoding="utf-8"))
    image = spec["image"]

    assert image.split("/")[-1].count("@sha256:") == 1, image
    digest = image.split("@sha256:", 1)[1]
    assert len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest), digest


def test_lvpocket_dockerfile_keeps_weights_out_and_pythonpath_set() -> None:
    dockerfile = (LVPOCKET / "Dockerfile").read_text(encoding="utf-8")

    assert "ENTRYPOINT [" in dockerfile
    # 权重不能出现在 COPY 里
    for line in dockerfile.splitlines():
        stripped = line.strip()
        if stripped.startswith("COPY ") and "new_best" in stripped:
            raise AssertionError(f"权重不应进入镜像：{stripped}")
    # 模型根必须在 PYTHONPATH 里（scripts/ 子目录的脚本要能 import 根目录的 pybel.py）
    assert "PYTHONPATH=/opt/sciminer/model" in dockerfile
    # openbabel 的库修补必须在构建期执行
    assert "patch_openbabel.py" in dockerfile
    # env/bin/python 软链（模型入口硬编码了这个路径）
    assert "ln -sfn /usr/local/bin/python /opt/sciminer/model/env/bin/python" in dockerfile


def test_shared_openbabel_patch_is_idempotent(tmp_path: Path) -> None:
    """patch 脚本必须可重复执行，而且 pattern 不匹配时要报错而不是静默跳过。"""
    import re

    source = (MODEL_IMAGES / "shared" / "patch_openbabel.py").read_text(encoding="utf-8")
    pattern = re.compile(r"broken = \[\(x, y\.strip\(\)\) for x, y in broken\]")
    replacement = "broken = [(v[0], v[1].strip()) for v in broken if len(v) > 1]"
    assert replacement in source
    assert pattern.search(source) is not None

    # 模拟一段含 bug 的 pybel.py，验证替换后语法完好且再次替换为空操作
    broken = "def f(formats):\n    broken = formats.split('\\n')\n    broken = [(x, y.strip()) for x, y in broken]\n"
    once, count = pattern.subn(replacement, broken)
    assert count == 1
    assert replacement in once
    twice, count_again = pattern.subn(replacement, once)
    assert count_again == 0, "替换后不应再匹配，否则 patch 不幂等"
    compile(once, "<patched>", "exec")


def test_docs19_is_indexed() -> None:
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "19-模型镜像构建与权重外置流程.md" in index
