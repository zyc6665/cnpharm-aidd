#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

browser="${PLAYWRIGHT_BROWSER:-chromium}"
mode="${1:---install}"

run_as_root() {
  if [[ "$(id -u)" == "0" ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "缺少 Playwright 系统依赖，但当前用户没有 root/sudo 权限。"
    echo "请使用 root 或具备 sudo 权限的用户执行：cd frontend && npm run test:e2e:deps"
    return 1
  fi
}

install_nspr_nss_fallback() {
  if command -v apt-get >/dev/null 2>&1; then
    run_as_root env DEBIAN_FRONTEND=noninteractive apt-get update
    run_as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      libnspr4 \
      libnss3
    return
  fi

  if command -v dnf >/dev/null 2>&1; then
    run_as_root dnf install -y nspr nss
    return
  fi

  if command -v yum >/dev/null 2>&1; then
    run_as_root yum install -y nspr nss
    return
  fi

  echo "未识别的系统包管理器，无法自动安装 libnspr4/libnss3。"
  echo "请手动安装 nspr/nss 后重试：cd frontend && npm run test:e2e"
  return 1
}

ensure_system_deps() {
  local dry_run_output

  if dry_run_output="$(npx playwright install-deps "${browser}" --dry-run 2>&1)"; then
    echo "Playwright system dependencies are installed."
    return
  fi

  echo "${dry_run_output}"
  echo "检测到 Playwright 系统依赖缺失，开始安装 ${browser} 运行时依赖。"

  if ! npx playwright install-deps "${browser}"; then
    echo "Playwright 自动依赖安装失败，尝试补齐 Chromium 必需的 nspr/nss。"
    install_nspr_nss_fallback
    npx playwright install-deps "${browser}" --dry-run
  fi
}

case "${mode}" in
  --check)
    npx playwright install-deps "${browser}" --dry-run
    ;;
  --ensure-runtime)
    ensure_system_deps
    npx playwright install "${browser}"
    ;;
  --install)
    ensure_system_deps
    npx playwright install "${browser}"
    ;;
  *)
    echo "用法：$0 [--install|--ensure-runtime|--check]"
    exit 2
    ;;
esac
