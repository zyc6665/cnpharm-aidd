# LangGraph Agent 与模型服务配置设计

## 目标

把当前 AIDD Agent 从轻量规则编排升级为 LangGraph 驱动的智能编排层，同时在管理员后台增加模型服务配置能力，让管理员可以维护 OpenAI-compatible 模型服务的 `base_url`、`api_key`、`model` 等参数。

升级后用户侧交互保持简单：

- 用户上传文件。
- 用户描述研究目标。
- Agent 自动判断输入语义、探索可用工具、规划步骤、提交任务，并根据结果继续执行或结束。

## 当前状态

当前工作台 Agent 已经具备基础编排能力：

- 前端入口在 `frontend/src/components/workflow/AiddAgentPanel.vue`。
- Agent API 在 `backend/app/api/v1/agents.py`。
- 编排服务在 `backend/app/agents/aidd/service.py`。
- 计划生成在 `backend/app/agents/aidd/planner.py`。
- 工具能力注册在 `backend/app/agents/aidd/capabilities.py`。
- 运行状态持久化在 `agent_runs` 和 `agent_run_steps`。

当前实现不是 LangGraph，而是：

```text
rule-based planner + capability registry + task orchestration state machine
```

这个实现适合验证平台链路，但不适合作为长期 Agent 架构，因为计划、观察、重规划仍然容易变成代码分支。

## 核心设计

推荐采用渐进式替换：

```text
LangGraph Agent Orchestrator
    -> platform tool capability registry
    -> existing Tool/Task/File execution system
    -> agent_runs / agent_run_steps visible state
```

LangGraph 只负责智能决策和状态流转，不直接执行模型工具。所有实际工具执行仍然通过现有 `Task` 系统完成。

这样可以避免重写已有工具执行器、文件系统、任务详情页和产物复用逻辑。

## LangGraph 图设计

第一版图节点：

```text
load_context
classify_input
discover_tools
plan_steps
validate_plan
execute_step
observe_result
replan_or_finish
```

节点职责：

- `load_context`：读取 Agent run、用户输入文件、模型服务配置、平台可用工具。
- `classify_input`：判断上传文件语义，例如 `protein_pdb`、`pocket_pdb`、`ligand_pdb`、`smiles_csv`。
- `discover_tools`：从能力注册表和数据库工具状态中找出当前可用工具。
- `plan_steps`：调用模型服务生成结构化计划。
- `validate_plan`：校验模型计划只能使用可用工具，并且每一步输入输出可以接上。
- `execute_step`：创建或继续平台任务。
- `observe_result`：读取已完成任务产物，抽取语义输出。
- `replan_or_finish`：决定继续执行、重新规划、等待任务、失败或成功结束。

图状态建议：

```python
class AIDDGraphState(TypedDict, total=False):
    run_id: str
    user_id: str
    message: str
    input_file_id: str
    semantic_inputs: dict[str, dict[str, str]]
    available_tools: list[dict[str, Any]]
    plan: dict[str, Any]
    current_step_key: str | None
    observations: list[dict[str, Any]]
    final_outputs: dict[str, Any]
    status: str
    error: str | None
```

`thread_id` 使用 `agent_run.id`。LangGraph checkpoint 保存内部推理状态；`agent_runs` 和 `agent_run_steps` 继续保存前端可见状态。

## 模型服务设计

第一版只支持 `OpenAI Compatible`，覆盖 OpenAI、DeepSeek、Qwen API、本地 vLLM、SGLang 等服务。

新增 `model_services` 表：

```text
id
name
provider_type
base_url
api_key_encrypted
model_name
is_default
is_enabled
timeout_seconds
max_tokens
temperature
last_test_status
last_test_message
last_tested_at
created_at
updated_at
```

安全要求：

- API Key 加密存储。
- 后端不向前端返回明文 key。
- 前端编辑时支持留空保留原 key。
- 删除、设默认、测试连接都必须要求管理员权限。
- 生产环境必须配置 `SETTINGS_ENCRYPTION_KEY`。
- 开发环境可以回退到 `JWT_SECRET_KEY` 派生密钥，但要在日志或健康检查里提示。

后端新增服务层：

```text
backend/app/models/system_settings.py
backend/app/services/model_services.py
backend/app/common/secret_crypto.py
```

API 设计：

```text
GET    /api/v1/system/model-services
POST   /api/v1/system/model-services
PUT    /api/v1/system/model-services/{id}
DELETE /api/v1/system/model-services/{id}
POST   /api/v1/system/model-services/{id}/test
POST   /api/v1/system/model-services/{id}/set-default
```

模型调用统一封装：

```text
backend/app/agents/aidd/llm_client.py
```

Agent 不直接读取数据库中的密钥，而是通过服务层获取已解密的默认模型客户端。

## 管理员前端设计

在 `/admin/system` 页面改为 tabs：

- 系统概览
- 模型服务
- 配置快照

模型服务 tab 使用表格 + 抽屉表单：

- 表格列：名称、Provider、模型、Base URL、默认、启用、最近测试、操作。
- 操作：编辑、设为默认、测试连接、禁用、删除。
- 表单字段：名称、Provider、Base URL、API Key、Model、Timeout、Max Tokens、Temperature、启用状态。
- API Key 显示为 masked 状态，编辑时空值表示保留原 key。

UI 不展示“LangGraph 内部节点”给普通用户。运行时间线仍用当前 Agent 运行步骤，但可以增加计划摘要、观察摘要和错误原因。

## 计划结构

模型服务返回的计划必须是结构化 JSON，不允许模型直接返回自由文本作为执行计划。

建议 schema：

```json
{
  "intent": "generate_molecules_from_protein",
  "steps": [
    {
      "step_key": "pocket_prediction",
      "capability": "pocket_prediction",
      "tool_slug": "lvpocket-pocket-prediction",
      "inputs": {
        "protein_pdb": "agent_input"
      },
      "params": {}
    }
  ],
  "finish_condition": "generated_ligand_ready"
}
```

后端必须执行：

- tool slug 必须存在且 published。
- capability 必须匹配注册表。
- semantic inputs 必须可解析。
- params 只能覆盖允许字段，不能注入路径或命令。

## 错误处理

关键失败场景：

- 没有默认模型服务：Agent run 进入 `failure`，提示管理员配置模型服务。
- 模型服务连接失败：记录模型服务测试状态，Agent run 失败。
- 模型输出无法解析：进入一次修复提示；仍失败则终止。
- 计划校验失败：要求模型重规划；达到次数上限后失败。
- 工具任务等待中：LangGraph 状态为 `waiting_task`，由 sync/poll 继续推进。
- 工具任务失败：记录 observation，让模型判断是否换工具或终止；第一版可以直接终止。

## 测试策略

后端：

- 模型服务 CRUD 与密钥脱敏测试。
- API Key 加密/解密测试。
- OpenAI-compatible 测试连接使用 mock transport。
- LangGraph 状态图单元测试，覆盖蛋白输入、口袋输入、无默认模型、无效计划。
- Agent API 集成测试，确保不需要前端传 `input_type`。

前端：

- 系统设置页存在模型服务 tab。
- 表单不会回显明文 API Key。
- 新建、编辑、测试连接、设默认按钮调用正确 API。
- Agent 面板仍只暴露上传文件和任务描述。

## 非目标

第一版不做：

- 多 Provider 原生适配器。
- 多用户模型服务配置。
- 前端图可视化编辑器。
- 复杂人类审批节点。
- 长期对话记忆。
- 工具能力后台编辑器。

这些可以在 LangGraph 基线稳定后继续演进。
