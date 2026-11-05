# 在 4090 节点部署 drp-node-agent（8 卡）

> 本包已通过本地冒烟测试：`python tests/smoke_local.py`（提交→SUCCEEDED→卡位回 FREE、上报平台 mock 成功）。下面是真机部署步骤。

## 0. 前置
- 节点：10.202.2.228（hostname `4090`），Ubuntu 20.04，8×RTX 4090，Docker + nvidia runtime 已就绪。
- 需要 **root**（装 systemd、写 `/etc/drp`）。若只用普通用户验证，可先 `python -m drp_node_agent` 前台跑（见 §4）。
- 内网离线安装需提前准备 pip wheel；有外网则直接 pip。

## 1. 拷贝并安装 Agent
```bash
# 在节点上
tar -xzf drp-node-agent.tgz
cd node-agent
sudo ./install-agent.sh /path/to/slots.4090.yaml   # 或使用自带的 slots.4090.example.yaml
```
安装脚本会：建 `/opt/drp/node-agent` + venv、装依赖、写 `/etc/drp/slots.yaml`（若不存在）、写 `/etc/drp/agent.env`（若不存在）、装并启动 `drp-node-agent.service`。

## 2. 配置 /etc/drp/agent.env（关键）
```ini
DRP_PLATFORM_BASE_URL=http://<平台后端地址>:8000/api/v1
DRP_AGENT_REPORT_TOKEN=<与平台 DRP_NODE_AGENT_REPORT_TOKEN 一致>
DRP_AGENT_API_TOKEN=<与平台 DRP_NODE_AGENT_TOKEN 一致；可留空>
DRP_SLOTS_FILE=/etc/drp/slots.yaml
DRP_WORK_ROOT=/var/drp/work
DRP_REPORT_INTERVAL_SECONDS=15
```
改完：`sudo systemctl restart drp-node-agent`

## 3. 平台侧（让算力队列显示 8×4090）
1. `slots.yaml` 用本包的 `slots.4090.yaml`（8 卡，`nodeId=dev4090-01`，`agentEndpoint=http://10.202.2.228:8780`）。
2. 后端 `.env`：
   ```ini
   DRP_NODE_SLOTS_FILE=/绝对路径/slots.4090.yaml
   DRP_NODE_AGENT_REPORT_TOKEN=<与 agent.env 一致>
   DRP_NODE_AGENT_BASE_URL=http://10.202.2.228:8780
   DRP_NODE_AGENT_TOKEN=<与 DRP_AGENT_API_TOKEN 一致>
   ```
3. 重启后端 → `GET /api/v1/gpu/slots` 应 `configured:true`、`slotCount:8`、节点 4090；后台「算力队列」显示 8 个卡位，Agent 上报后状态变 FREE/BUSY。

## 4. 快速验证
```bash
# 节点本机
curl -s http://127.0.0.1:8780/healthz
curl -s -H "Authorization: Bearer <DRP_AGENT_API_TOKEN>" http://127.0.0.1:8780/api/v1/slots
# 平台
curl -s -H "Cookie: ..." http://<平台>/api/v1/gpu/slots | jq '.data.configured,.data.slotCount'
```

## 5. 重要提醒
- **当前平台任务执行仍走 SSH 执行器**（`app/tasks/executors/ssh_job.py`）；本 Agent 的 `/api/v1/jobs` 已按 `NodeAgentClient` 契约实现，供后续 HTTP 执行通道使用，当前主要作用是**卡位状态上报**（不接上报则页面卡位状态不会更新）。
- 4090 机器当前 GPU2~7 被其他任务占用（利用率 56~100%、显存 20~23G）。全部 8 卡声明会出现“页面可调度但实际被占”的风险；建议先用 GPU0/1，或等空闲后再全量。
- 严格 `deviceCount` 校验（容器内 `torch.cuda.device_count()==1`）待镜像侧支持后可增强。
