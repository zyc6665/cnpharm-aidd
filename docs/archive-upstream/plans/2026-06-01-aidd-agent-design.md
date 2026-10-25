# AIDD 可扩展智能体编排设计

## 目标

在现有 CPUModel/SciTool 平台上新增 AIDD 智能体能力，让用户可以通过自然语言和文件输入触发一条可靠的模型工具链。

第一版重点支持：

- 用户上传蛋白质结构后，智能体自动执行口袋探索。
- 口袋探索成功后，智能体自动把口袋产物交给分子生成工具。
- 用户上传口袋结构时，智能体跳过口袋探索，直接执行分子生成。

同时设计必须支持后续扩展：

- 分子对接
- 结合亲和力预测
- ADMET/性质预测
- 先导化合物优化
- 多分支和并行工具链

## 当前平台流程

当前平台已经具备可复用的工具运行基础，但产品形态是“工具工作台 + 单任务执行 + 手动产物复用”，不是自动工作流引擎。

### 现有工作台

`/workflow` 页面读取后端公开工作台分组，并以三栏布局展示：

- 左栏：工具分组
- 中栏：当前工具表单和运行按钮
- 右栏：当前用户历史产物

当前数据库中的工作台工具分组包括：

- 口袋探索：`lvpocket-pocket-prediction`
- 分子生成：`gcdm-pocket-generation`、`janus-qubo-ga-generation`
- 对接：`flowpepdock-docking`
- ADMET 性质预测：`molp-pc-property-prediction`
- 结合亲和力预测：`msign-affinity-prediction`

### 现有任务执行

用户在工具表单中上传文件或选择历史产物后，前端会构造普通任务请求：

- `params`
- `file_ids`
- `tool_id`
- 可选 `name`

后端 `POST /api/v1/tasks` 创建 `Task` 和 `TaskInput`，然后根据运行模式进入 direct runner 或 Celery。

执行器按工具版本配置中的 `type` 选择具体执行器：

- `remote_api`
- `docker_image`
- `python_script`
- `ssh_job`

执行完成后，平台把输出文件保存为 `File.source_type = tool_output`，并把文件 ID 写入 `TaskOutput.file_ids`。

### 现有产物复用

`GET /api/v1/files/artifacts` 返回当前用户自己的工具输出文件。前端的 `ArtifactFilePicker` 支持：

- 上传本地文件
- 从历史工具产物中选择文件

这套机制当前是手动复用，不负责自动判断上游输出该填入下游哪个字段。

## 核心设计决策

### 1. 智能体作为新增编排层

新增 AIDD Agent 编排层，不替代现有工具、任务、文件和执行器。

智能体只做：

- 理解用户目标
- 生成工具链计划
- 校验计划是否符合平台工具能力
- 创建普通平台任务
- 监听任务结果
- 提取语义产物并触发后续步骤

所有模型执行仍通过现有任务系统完成。

### 2. 不把 `/workflow` 改回强流程

现有 `/workflow` 已经定位为工具工作台，适合自由选择工具和手动复用产物。

智能体应作为新增入口接入，而不是把工作台重新改造成固定流程引擎。

推荐入口：

- 第一版可放在 `/workflow` 顶部作为“智能体运行入口”。
- 后续可独立成 `/agents/aidd` 页面。

### 3. 工具能力配置驱动，而不是写死工具链

不能只把 `lvpocket-pocket-prediction -> gcdm-pocket-generation` 写死在代码里。

应新增一层“工具能力注册表”，描述每个工具能消费什么语义输入、生成什么语义输出、字段如何映射。

这样后期新增对接、性质预测、亲和力预测时，只需要新增能力配置和少量提取规则，不需要重写智能体主流程。

### 4. LLM 只参与意图理解，不直接执行

第一版采用混合型智能体：

- LLM 或轻量意图解析器负责理解自然语言。
- 后端规则引擎负责选择允许的工具链。
- 工具字段、文件类型、依赖关系必须由后端配置校验。

LLM 不允许直接指定任意工具 ID、任意文件路径或绕过必需输入。

## 语义产物模型

新增统一的语义产物类型，用于跨工具连接。

首批建议：

- `protein_pdb`
- `pocket_pdb`
- `generated_ligand`
- `ligand_pdb`
- `smiles_csv`
- `docking_pose`
- `affinity_report`
- `property_report`
- `optimized_lead`

语义产物可以来源于：

- 用户上传文件
- 历史工具输出文件
- 某个 agent step 的任务输出文件
- 某个任务的结构化 `output_data`

第一版优先处理文件型产物。结构化结果只保存元信息，暂不参与自动下游绑定，除非工具能力显式声明可消费。

## 工具能力注册表

建议先用代码配置文件落地，后续再演进为数据库表和管理后台。

建议位置：

- `backend/app/agents/aidd/capabilities.py`

能力配置示例：

```python
{
    "tool_slug": "lvpocket-pocket-prediction",
    "capability": "pocket_prediction",
    "stage": "pocket_exploration",
    "inputs": [
        {
            "semantic_type": "protein_pdb",
            "field": "protein_pdb",
            "required": True,
            "accepted_extensions": [".pdb"],
        }
    ],
    "outputs": [
        {
            "semantic_type": "pocket_pdb",
            "source": "output_files",
            "match": {
                "filename_contains_any": ["pocket", "Pocket"],
                "extension": ".pdb",
            },
        }
    ],
    "defaults": {
        "model_choice": "auto",
        "device": "auto",
    },
}
```

分子生成工具：

```python
{
    "tool_slug": "gcdm-pocket-generation",
    "capability": "molecule_generation",
    "stage": "molecule_generation",
    "inputs": [
        {
            "semantic_type": "pocket_pdb",
            "field": "input_files.pocket_pdb",
            "required": True,
            "accepted_extensions": [".pdb"],
        }
    ],
    "outputs": [
        {
            "semantic_type": "generated_ligand",
            "source": "output_files",
            "match": {
                "extension": ".sdf",
            },
        }
    ],
    "defaults": {
        "params.n_samples": 8,
        "params.device": "cuda:0",
    },
}
```

后续工具示例：

```python
{
    "tool_slug": "msign-affinity-prediction",
    "capability": "affinity_prediction",
    "stage": "affinity_prediction",
    "inputs": [
        {"semantic_type": "protein_pdb", "field": "protein_pdb", "required": True},
        {"semantic_type": "ligand_pdb", "field": "ligand_pdb", "required": True},
    ],
    "outputs": [
        {
            "semantic_type": "affinity_report",
            "source": "output_data",
            "path": "result.outputs.prediction",
        }
    ],
}
```

## 智能体计划模型

智能体生成的不是立即执行代码，而是一个可校验计划。

计划结构：

```json
{
  "intent": "generate_molecules_from_protein",
  "requested_outputs": ["pocket_pdb", "generated_ligand"],
  "steps": [
    {
      "step_key": "pocket_prediction",
      "tool_slug": "lvpocket-pocket-prediction",
      "depends_on": [],
      "inputs": {
        "protein_pdb": "agent_input:protein"
      },
      "params": {
        "model_choice": "auto",
        "device": "auto"
      }
    },
    {
      "step_key": "molecule_generation",
      "tool_slug": "gcdm-pocket-generation",
      "depends_on": ["pocket_prediction"],
      "inputs": {
        "pocket_pdb": "step:pocket_prediction:pocket_pdb"
      },
      "params": {
        "params.n_samples": 8
      }
    }
  ]
}
```

第一版只执行线性计划，但计划结构保留 `depends_on`，用于后续支持 DAG。

后期可支持：

```text
protein_pdb
  -> pocket_prediction
  -> molecule_generation
      -> property_prediction
      -> docking
      -> affinity_prediction
```

其中 `property_prediction`、`docking`、`affinity_prediction` 可以在依赖满足后并行或半并行执行。

## 数据模型

### agent_runs

记录一次智能体运行。

字段建议：

- `id`
- `user_id`
- `message`
- `intent`
- `status`
- `input_type`
- `input_file_id`
- `requested_outputs`
- `plan`
- `summary`
- `error_message`
- `created_at`
- `updated_at`
- `finished_at`

状态：

- `pending`
- `planning`
- `running`
- `waiting_task`
- `success`
- `failure`
- `canceled`

### agent_run_steps

记录一次智能体运行中的单个工具步骤。

字段建议：

- `id`
- `agent_run_id`
- `step_key`
- `tool_slug`
- `tool_id`
- `task_id`
- `status`
- `sort_order`
- `depends_on_step_ids`
- `semantic_inputs`
- `semantic_outputs`
- `params`
- `input_file_ids`
- `output_file_ids`
- `error_message`
- `created_at`
- `updated_at`
- `started_at`
- `finished_at`

状态：

- `pending`
- `ready`
- `running`
- `waiting_task`
- `success`
- `failure`
- `skipped`
- `canceled`

### agent_artifacts

第一版可以不单独建表，把语义产物存进 `agent_run_steps.semantic_outputs`。

如果后期需要跨 run 检索和比较，再新增独立表：

- `id`
- `agent_run_id`
- `step_id`
- `semantic_type`
- `file_id`
- `task_id`
- `tool_slug`
- `metadata`
- `created_at`

## API 设计

### 创建智能体运行

```text
POST /api/v1/agents/aidd/runs
```

请求：

```json
{
  "message": "上传蛋白后进行口袋探索并生成分子",
  "input_file_id": "file-id",
  "input_type": "protein_pdb",
  "params": {
    "generation_count": 8,
    "device": "auto"
  },
  "requested_outputs": ["pocket_pdb", "generated_ligand"]
}
```

返回：

```json
{
  "id": "agent-run-id",
  "status": "running",
  "intent": "generate_molecules_from_protein",
  "steps": [
    {
      "id": "step-id",
      "step_key": "pocket_prediction",
      "tool_slug": "lvpocket-pocket-prediction",
      "status": "waiting_task",
      "task_id": "task-id"
    }
  ]
}
```

### 查询智能体运行

```text
GET /api/v1/agents/aidd/runs/{run_id}
```

返回：

- run 基本信息
- steps
- 每步关联 task 摘要
- 语义输入和输出
- 输出文件下载信息
- 错误信息

### 列表

```text
GET /api/v1/agents/aidd/runs
```

只返回当前用户自己的智能体运行。

### 取消

```text
POST /api/v1/agents/aidd/runs/{run_id}/cancel
```

取消当前等待或运行中的步骤，并调用已有任务取消能力。

### 重试步骤

后续建议增加：

```text
POST /api/v1/agents/aidd/runs/{run_id}/steps/{step_id}/retry
```

第一版可以先不做，保留接口设计。

## 编排执行流程

### 创建 run

1. 校验用户登录状态。
2. 校验输入文件归属当前用户。
3. 解析 `input_type`。
4. 解析用户 message 得到 intent 和 requested outputs。
5. 根据工具能力注册表生成计划。
6. 校验计划中的工具均存在、已发布、公开、具有当前版本。
7. 创建 `agent_runs` 和 `agent_run_steps`。
8. 调度第一个 ready step。

### 执行 step

1. 根据 step 的语义输入找到文件 ID。
2. 根据工具能力配置把语义输入映射成工具字段。
3. 生成 `params` 和 `file_ids`。
4. 调用内部任务创建服务创建普通任务。
5. 保存 `task_id` 到 `agent_run_steps`。
6. step 进入 `waiting_task`。

### 任务完成回收

第一版可以用轮询型后台调度器：

1. 定期扫描 `waiting_task` 的 agent step。
2. 查询对应 task 状态。
3. 如果 task 成功，按工具能力配置提取语义输出。
4. 保存 `semantic_outputs` 和 `output_file_ids`。
5. 判断哪些下游 step 依赖已满足。
6. 调度下游 step。
7. 如果所有 step 成功，run 标记为 `success`。

后续可以把 task 成功事件接入 worker 完成回调，减少轮询。

## 参数映射规则

智能体必须复用当前前端任务提交协议的语义，但实现位置在后端。

对于 `ssh_job` 工具：

- 文件输入在 `file_ids` 中传入。
- 参数中对应字段应填 `input/<filename>`。
- 嵌套字段如 `input_files.pocket_pdb` 应写入嵌套对象。

示例：

```json
{
  "params": {
    "params": {
      "n_samples": 8,
      "device": "cuda:0"
    },
    "input_files": {
      "pocket_pdb": "input/pocket_001.pdb"
    }
  },
  "file_ids": ["pocket-file-id"]
}
```

对于非 `ssh_job` 工具：

- 文件字段可填下载 URL。
- 同时保留 `file_ids` 便于执行器下载或审计。

## 输出提取规则

输出提取必须显式配置，不做宽泛猜测。

文件输出匹配维度：

- 文件扩展名
- 文件名包含关键词
- content type
- 来源 task/tool

结构化输出匹配维度：

- JSON path
- 数据类型
- 是否允许作为下游输入

如果一个步骤找不到必需语义输出：

- step 标记为 `failure`
- run 标记为 `failure`
- 保留原始 task 结果和日志入口

## 可扩展工具链示例

### 1. 蛋白到分子生成

```text
protein_pdb
  -> lvpocket-pocket-prediction
  -> pocket_pdb
  -> gcdm-pocket-generation
  -> generated_ligand
```

### 2. 口袋到分子生成

```text
pocket_pdb
  -> gcdm-pocket-generation
  -> generated_ligand
```

### 3. 蛋白到分子生成再性质预测

```text
protein_pdb
  -> lvpocket-pocket-prediction
  -> gcdm-pocket-generation
  -> generated_ligand
  -> molp-pc-property-prediction
  -> property_report
```

### 4. 蛋白到候选分子再亲和力预测

```text
protein_pdb + ligand_pdb
  -> msign-affinity-prediction
  -> affinity_report
```

如果上游生成的是 `.sdf`，而亲和力工具需要 `ligand_pdb`，必须先接入一个显式转换工具。第一版不做隐式格式转换。

### 5. 后续 DAG

```text
protein_pdb
  -> pocket_prediction
  -> molecule_generation
      -> property_prediction
      -> docking
      -> affinity_prediction
```

各下游步骤只在依赖语义产物满足后执行。

## 前端设计

第一版建议在 `/workflow` 顶部新增智能体入口，不破坏现有工具工作台。

界面包括：

- 目标输入框
- 输入类型选择：蛋白质 PDB / 口袋 PDB
- 文件上传或选择历史产物
- 可选参数：生成数量、设备、是否继续做性质预测等
- 运行按钮
- 智能体步骤时间线
- 每一步任务入口和输出文件入口

步骤时间线展示：

- step 名称
- 工具名称
- 状态
- 关联 task id
- 进度
- 输出产物
- 错误信息

第一版不做复杂多轮聊天，也不做用户编辑 DAG。用户可以通过普通工作台继续手动使用任意产物。

## 错误处理

### 输入错误

- 缺少输入文件：返回明确错误。
- 输入文件不属于当前用户：拒绝访问。
- 输入类型与文件扩展名不匹配：拒绝创建 run。

### 工具不可用

- 工具不存在：计划失败。
- 工具未发布或不公开：计划失败。
- 工具没有当前版本：计划失败。
- 工具 schema 与能力配置不匹配：计划失败，并提示管理员修复配置。

### 执行失败

- 任一步 task 失败：对应 step 失败，run 失败。
- 已成功的上游产物保留。
- 用户可进入 task 详情查看日志。

### 输出缺失

- task 成功但没有匹配到必需语义输出：step 失败。
- 错误信息必须包含工具 slug、task id、缺失的 semantic type。

## 安全与权限

- 所有 run 只属于当前用户。
- agent 只能使用当前用户上传文件或当前用户自己的工具输出文件。
- agent 不接受客户端直接传入任意文件路径。
- agent 不允许客户端直接指定未注册能力的工具链。
- 工具参数必须经过 schema 和能力配置双重校验。

## 测试策略

### 后端单元测试

- protein 输入生成两步计划。
- pocket 输入生成一步计划。
- 请求性质预测时追加性质预测步骤。
- 工具缺失时计划失败。
- 工具未发布时计划失败。
- 字段映射能正确生成 `params` 和 `file_ids`。
- `ssh_job` 文件字段能正确映射为 `input/<filename>`。
- task 成功后能提取语义输出。
- task 失败后 step 和 run 状态正确。

### 后端 API 测试

- 创建 agent run。
- 查询 run 详情。
- 非本人 run 不可访问。
- 取消 run 会取消等待或运行中的任务。

### 前端测试

- `/workflow` 显示智能体入口。
- 上传文件后可以创建 agent run。
- run 时间线能显示每步状态。
- 成功 step 能显示 task 和输出文件入口。
- 失败 step 能显示错误信息。

## 实施顺序

1. 后端能力配置和语义类型定义。
2. 后端 plan builder。
3. `agent_runs`、`agent_run_steps` 模型与迁移脚本。
4. 后端 agent API。
5. 后端 step 调度器和 task 状态回收。
6. 首批工具能力配置：LVPocket、GCDM。
7. `/workflow` 顶部智能体入口。
8. agent run 时间线组件。
9. 扩展性质预测和亲和力预测能力配置。

## 非目标

第一版不做：

- 用户可视化拖拽 DAG。
- 复杂多轮聊天记忆。
- 隐式文件格式转换。
- 跨用户产物共享。
- 让 LLM 直接执行工具。
- 改造现有任务执行器。
- 替换现有工具工作台。

## 验收标准

- 用户上传蛋白质 PDB 后，可以一键触发口袋探索和分子生成。
- 用户上传口袋 PDB 后，可以跳过口袋探索直接生成分子。
- 每一步都能看到关联任务、状态和输出产物。
- 任一步失败后，错误可追踪到具体工具和任务。
- 新增对接或性质预测工具时，可以通过能力配置接入智能体计划，不需要重写核心编排逻辑。
