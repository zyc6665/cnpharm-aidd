#!/usr/bin/env python
"""用 compose 渲染出的环境变量真跑一次配置导入。

为什么需要这一步：``docker compose config`` 只校验 YAML 与必填变量，它不 import
应用，也就看不见「值合法但配置层解析不了」的故障。B-01 就是这么漏出去的——
``SSO_ALLOWED_UNIT_CODES: ${SSO_ALLOWED_UNIT_CODES:-}`` 渲染成空串，compose 校验
通过，后端一启动就 ``SettingsError`` 退出，三个服务全起不来。

本脚本把 ``docker compose config --format json`` 的输出读进来，取 ``backend`` 服务的
environment，原样注入子进程后执行 ``import app.config``：配置层任何字段解析失败都会
以非零码冒出来。

只用标准库 + 子进程，不需要装应用依赖之外的包。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

#: 只测配置层：``app.config`` 的导入面（dotenv / pydantic / pydantic-settings）就够，
#: 导入 ``app.main`` 会连带拉起数据库驱动等重依赖，CI 里没必要。
PROBE = "import app.config"


def _service_env(config: dict, service: str) -> dict[str, str]:
    services = config.get("services") or {}
    if service not in services:
        raise SystemExit(f"[compose-env] 服务 {service!r} 不存在，无法校验")
    raw = services[service].get("environment") or {}
    env: dict[str, str] = {}
    for key, value in raw.items():
        # compose 支持 ``- KEY``（只透传宿主值）与 ``KEY=`` 两种写法；后者渲染出来是空串，
        # 正是 B-01 的触发形态，必须原样保留而不是当成「没配置」跳过。
        if value is None:
            env[key] = ""
        elif isinstance(value, (int, float, bool)):
            env[key] = str(value)
        else:
            env[key] = str(value)
    return env


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法: check_compose_env.py <compose-config.json> [服务名]", file=sys.stderr)
        return 2
    config_path = Path(argv[1])
    service = argv[2] if len(argv) > 2 else "backend"
    if not config_path.is_file():
        print(f"[compose-env] 找不到 {config_path}", file=sys.stderr)
        return 2

    config = json.loads(config_path.read_text(encoding="utf-8"))
    service_env = _service_env(config, service)

    env = dict(os.environ)
    env.update(service_env)
    # 父进程可能是开发机（有 .env）也可能是 CI；把 dotenv 搜索路径钉死到不存在的
    # 位置，确保测的就是这份渲染结果，不掺本地文件。
    env["PYTHONPATH"] = str(BACKEND_DIR)
    env.pop("DOTENV_PATH", None)

    print(f"[compose-env] 校验 {service} 服务：{len(service_env)} 个环境变量")
    for key in sorted(service_env):
        if key.endswith(("SECRET", "PASSWORD", "TOKEN", "KEY")) and service_env[key]:
            print(f"  {key}=<set,len={len(service_env[key])}>")
        else:
            print(f"  {key}={service_env[key]!r}")

    completed = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        print("[compose-env] 配置导入失败：", file=sys.stderr)
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        return completed.returncode or 1

    print("[compose-env] PASSED：渲染出的环境可以被 app.config 解析")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
