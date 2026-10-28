"""修补 openbabel-wheel 3.1.1.23 的 pybel 模块级格式解析缺陷。

## 症状

`import pybel`（或 `from openbabel import pybel`）直接崩溃：

```
Traceback (most recent call last):
  File "<...>/openbabel/pybel.py", line 69, in <module>
    broken = [(x, y.strip()) for x, y in broken]
ValueError: not enough values to unpack (expected 2, got 1)
```

注意崩在**模块级**（import 阶段），所以任何 import pybel 的代码都跑不起来，
错误信息也完全不提 openbabel 版本——很容易误判成自己代码的问题。

## 原因

`pybel.py` 模块加载时会执行

```python
def _formatstodict(formats):
    broken = formats.split("\n")
    broken = [(x, y.strip()) for x, y in broken]
```

而 `openbabel-wheel 3.1.1.23` 内置的 libopenbabel 返回的格式表中，
部分行不含制表符，`split()` 后只有 1 个字段，二元解包失败。

## 改法

改为索引取值，并跳过字段不足的行——这些行本身没有可用的「格式名 → 描述」映射，
丢弃不影响任何格式的可用性。

## 为什么改库文件而不是改模型代码

模型侧（`/opt/sciminer/model/pybel.py`）只是 `from openbabel import pybel` 的
薄封装，问题在第三方包里。在镜像构建期修库文件，模型代码保持原样（可追溯、
与原环境行为一致），代价是换 openbabel-wheel 版本时这段 patch 要在 CI 里被验证。
"""

from __future__ import annotations

import pathlib
import re
import sys

TARGET = pathlib.Path("/usr/local/lib/python3.11/site-packages/openbabel/pybel.py")
PATTERN = re.compile(r"broken = \[\(x, y\.strip\(\)\) for x, y in broken\]")
REPLACEMENT = "broken = [(v[0], v[1].strip()) for v in broken if len(v) > 1]"


def main() -> int:
    if not TARGET.exists():
        print(f"openbabel pybel not found at {TARGET}（该模型不依赖 openbabel，跳过）")
        return 0

    text = TARGET.read_text(encoding="utf-8")
    if REPLACEMENT in text:
        print(f"openbabel pybel already patched: {TARGET}")
        return 0

    patched, count = PATTERN.subn(REPLACEMENT, text)
    if count != 1:
        # 不静默通过：pattern 不匹配意味着 openbabel 内部实现变了，
        # 这时应当失败并让人工确认，而不是留下一个「构建成功但运行必崩」的镜像。
        print(
            f"openbabel patch pattern matched {count} times in {TARGET}；"
            "openbabel 版本可能已变更，请人工确认 pybel._formatstodict 的实现后更新本脚本",
            file=sys.stderr,
        )
        return 1

    TARGET.write_text(patched, encoding="utf-8")
    print(f"patched openbabel pybel._formatstodict: {TARGET}")
    return 0


raise SystemExit(main())
