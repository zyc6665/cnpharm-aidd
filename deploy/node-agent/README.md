# drp-node-agent

算力节点上的 Agent 服务（FastAPI，默认 `:8780`），负责：卡位状态机（FREE / RESERVED / BUSY / FAULT）、按指令在指定卡位 `docker run` 模型容器、超时/取消处理、把卡位状态上报平台。

> 契约依据：`docs/03 §4.4`、`docs/09 §4.5/§5.6`、`docs/13 §4.1~§4.4`；平台侧客户端 `backend/app/gpu/node_agent.py`；上报端点 `POST /api/v1/gpu/slots/report`（`SlotStateReport`）。

## 接口（平台主通道 A）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/jobs` | 提交卡位作业，body=`{taskId,slotId,image,env?,dockerArgs?,modelEntry?,maxMinutes?,heartbeatSeconds?}`，返回 `{jobId}` |
| POST | `/api/v1/jobs/{jobId}:cancel` | 取消作业，body 可带 `{reason}` |
| GET | `/api/v1/jobs/{jobId}` | 查状态，返回 `{jobId,state,slotId,progress,message,exitCode,deviceCount}` |
| GET | `/api/v1/slots` | 本机卡位与状态（观测用） |
| GET | `/healthz` | 健康检查（无需鉴权） |

鉴权：平台携带 `Authorization: Bearer <DRP_AGENT_API_TOKEN>`；`DRP_AGENT_API_TOKEN` 为空则不校验。

## 上报（辅通道 C）
后台每 `DRP_REPORT_INTERVAL_SECONDS` 秒把每个卡位 `{nodeId,slotId,state,message,deviceCount}` POST 到 `DRP_PLATFORM_BASE_URL/gpu/slots/report`，header `X-DRP-Agent-Token: <DRP_AGENT_REPORT_TOKEN>`。
平台侧必须配置 `DRP_NODE_AGENT_REPORT_TOKEN`，否则该端点返回 503（默认关闭）。

## 安装（在算力节点上）
```bash
sudo ./install-agent.sh /path/to/slots.yaml
# 编辑 /etc/drp/agent.env：DRP_PLATFORM_BASE_URL、DRP_AGENT_REPORT_TOKEN、DRP_AGENT_API_TOKEN
sudo systemctl restart drp-node-agent
curl -s http://127.0.0.1:8780/healthz
```
离线内网：请先把 `requirements.txt` 的 wheel 预下载到本机，用
`pip install --no-index --find-links=<wheelhouse> -r requirements.txt`。

## slots.yaml 要点（NVIDIA 4090）
- `deviceIds` 是宿主卡号，仅观测；
- `NVIDIA_VISIBLE_DEVICES`=宿主卡号，`CUDA_VISIBLE_DEVICES`="0"（容器内序号恒为 0）；
- `dockerArgs: ["--gpus","device=N","--ipc=host"]`；
- `models` 省略 = 允许任意模型；`memoryMb` 用于准入校验。

示例见 `slots.4090.example.yaml`（8 张 4090）。

## 目录
- `drp_node_agent/config.py` 配置与 slots 解析
- `drp_node_agent/core.py` 卡位状态机 + Docker 生命周期 + 作业监控
- `drp_node_agent/reporter.py` 状态上报
- `drp_node_agent/server.py` FastAPI 路由
- `systemd/drp-node-agent.service`、`install-agent.sh`

## 已知边界
- 当前平台的任务执行仍走 SSH 执行器（`app/tasks/executors/ssh_job.py`）；本 Agent 的 `/api/v1/jobs` 供后续 HTTP 执行通道使用，并可立刻用于**卡位状态上报**。
- `deviceCount` 目前按“容器已启动=1”上报；如需严格校验可在镜像内跑 `torch.cuda.device_count()` 后扩展。
