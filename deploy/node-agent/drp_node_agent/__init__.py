"""drp-node-agent —— 卡位执行与状态上报（离线内网，FastAPI :8780）。

契约来源：
- 平台侧客户端 `backend/app/gpu/node_agent.py`（POST /api/v1/jobs、cancel、status）
- 平台上报端点 `POST /api/v1/gpu/slots/report`（body SlotStateReport；header X-DRP-Agent-Token）
- 卡位声明 `slots.yaml`（docs/03 §4.4、docs/09 §5.6、docs/13 §4.4）
"""
__version__ = "1.0.0"
