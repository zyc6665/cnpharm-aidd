#!/usr/bin/env bash
# 安装 drp-node-agent 到本机（systemd 常驻，:8780）。
# 用法：sudo ./install-agent.sh [slots.yaml]
#   slots.yaml 可选，缺省用本目录下 slots.4090.example.yaml（仅当 /etc/drp/slots.yaml 不存在时复制）。
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "请用 root 运行（sudo ./install-agent.sh）" >&2
  exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/drp/node-agent"
VENV_DIR="/opt/drp/venv"
SLOTS_SRC="${1:-$SRC_DIR/slots.4090.example.yaml}"

echo "[1/7] 创建目录"
mkdir -p "$INSTALL_DIR" /etc/drp /var/drp/work /var/drp/logs /var/drp/model-cache

echo "[2/7] 复制 Agent 代码"
rm -rf "$INSTALL_DIR/drp_node_agent"
cp -r "$SRC_DIR/drp_node_agent" "$INSTALL_DIR/"
cp "$SRC_DIR/requirements.txt" "$INSTALL_DIR/"

echo "[3/7] 创建 Python 虚拟环境并安装依赖"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
if ! "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt"; then
  echo "依赖安装失败：内网离线环境请预先准备 wheel 并使用 pip install --no-index --find-links=<wheelhouse>" >&2
  exit 1
fi

echo "[4/7] 安装卡位声明与 Agent 配置"
if [[ ! -f /etc/drp/slots.yaml ]]; then
  cp "$SLOTS_SRC" /etc/drp/slots.yaml
  echo "已写入 /etc/drp/slots.yaml（来源 $SLOTS_SRC）"
else
  echo "/etc/drp/slots.yaml 已存在，跳过"
fi
if [[ ! -f /etc/drp/agent.env ]]; then
  cp "$SRC_DIR/agent.env.example" /etc/drp/agent.env
  chmod 600 /etc/drp/agent.env
  echo "已写入 /etc/drp/agent.env（请按需修改平台地址与 token 后重启服务）"
fi

echo "[5/7] 安装 systemd 单元"
cp "$SRC_DIR/systemd/drp-node-agent.service" /etc/systemd/system/drp-node-agent.service
systemctl daemon-reload

echo "[6/7] 启动服务"
systemctl enable drp-node-agent >/dev/null
systemctl restart drp-node-agent

echo "[7/7] 健康检查"
sleep 2
systemctl --no-pager --full status drp-node-agent | head -15 || true
echo "--- /healthz ---"
curl -s "http://127.0.0.1:${DRP_AGENT_PORT:-8780}/healthz" || true
echo
echo "安装完成。请确认 /etc/drp/agent.env 的平台地址与 token 与平台一致后：systemctl restart drp-node-agent"
