"""patch_cpu_ckpt_load.py — 把 checkpoint 先读到 CPU 再搬到设备。

背景：`sample_for_pdb.py:115` 用的是 `torch.load(path, map_location=args.device)`，
unpickle 过程中每个 storage 都直接在 GPU 上分配。在共享 24GB 卡上（其他租户已占
15~22GB）这一步会抛 `RuntimeError: CUDA error: out of memory`，而且是在
`_cuda_deserialize` 里，看起来像「模型太大」，实际上是「加载方式把峰值放大了」。

改法：`map_location='cpu'` 反序列化（CPU 内存 1~2GB，代价可忽略），
再由下一行的 `.to(args.device)` 一次性搬到 GPU。

幂等：已经改过就只打印跳过。
"""

from __future__ import annotations

import pathlib
import sys

OLD = "ckpt = torch.load(config.model.checkpoint, map_location=args.device)"
NEW = (
    "# 先反序列化到 CPU 再搬到设备：直接在 GPU 上 unpickle 会把每个 storage\n"
    "    # 都当成一次 GPU 分配，在共享卡上极易 OOM（见 platform patch 说明）。\n"
    "    ckpt = torch.load(config.model.checkpoint, map_location='cpu')"
)
MARKER = "map_location='cpu'"


def patch_text(py_text: str) -> tuple[str, bool]:
    if MARKER in py_text:
        return py_text, False
    if OLD not in py_text:
        raise SystemExit(f"未找到待替换的加载语句：{OLD}")
    return py_text.replace(OLD, NEW, 1), True


def main() -> int:
    target = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "sample_for_pdb.py")
    text = target.read_text(encoding="utf-8")
    patched, changed = patch_text(text)
    if not changed:
        print(f"[skip] {target} 已经打过补丁")
        return 0
    target.write_text(patched, encoding="utf-8")
    print(f"[ok] {target} 已改为 CPU 反序列化")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
