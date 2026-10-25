# 任务结果可视化设计

## 背景

当前工具详情页已经支持基于 `input_schema` 的动态输入表单，但任务详情页仍停留在通用结果展示层，只能显示原始 JSON、日志和下载按钮，尚未真正实现结构类/小分子类结果的前端可视化。

从现有实现看，结果链路还存在两个断点：

1. 执行器能够产出 `output_file_ids`，但 worker 持久化任务输出时只写入 `result`，没有规范写入 `TaskOutput.file_ids`。
2. 任务详情 API 与前端消费字段不一致，页面期待 `output_files` / `input_files` / `output_data`，但接口主体仍以 `inputs` / `outputs` 为核心。

本设计目标是先补齐链路，再在任务详情页落地统一的结果可视化面板。

## 目标

- 支持在任务详情页直接可视化结构类结果：`PDB`、`mmCIF`、`PDBQT`
- 支持在任务详情页直接可视化小分子结果：`SDF`、`MOL2`
- 支持“输入口袋/受体 + 输出配体”同场景展示
- 不支持的格式自动回退到原始输出与下载列表
- 不破坏现有任务创建、日志刷新、文件下载能力

## 非目标

- 不在本轮引入复杂的多标签分析工作台
- 不实现结果编辑、标注、导出图片等增强功能
- 不在本轮支持所有科学格式，只覆盖首批明确需要的格式

## 方案选择

### 采用方案

采用单一 Viewer 方案：在前端引入一个统一的分子结构查看器，负责承接结构类与小分子类文件。

选择理由：

- 前端只维护一套加载、错误处理、空态和样式逻辑
- 任务详情页只需要一套“文件识别 -> 预览模型 -> Viewer 渲染”的流程
- 后续若扩展更多结构文件格式，改动范围更小

### 放弃方案

- 双 Viewer 方案：能力可分治，但会提高前端依赖、状态与渲染路径复杂度
- 仅修链路不做可视化：无法满足任务详情页直接查看结果的目标

## 架构设计

### 后端

后端新增一个“规范化任务结果”职责，确保任务详情接口返回稳定、可视化友好的结构。

#### 1. 任务输出持久化

`backend/app/worker/tasks.py`

- 从执行器返回值中提取规范结果对象
- 把输出文件 ID 正式写入 `TaskOutput.file_ids`
- 根据结果内容设置 `output_type`
  - 默认 `json`
  - 存在可预览文件时可标记为 `visualization`

#### 2. 任务详情接口规范化

`backend/app/api/v1/tasks.py`

- 修复当前把 `uselist=False` 关系当列表使用的问题
- 统一从 `TaskInput.file_ids` / `TaskOutput.file_ids` 读取文件 ID
- 查询文件元数据，返回前端真正可用的：
  - `id`
  - `filename`
  - `original_name`
  - `size`
  - `url`
  - `content_type`
- 同时补齐兼容字段：
  - `input_files`
  - `output_files`
  - `output_data`
- 返回 `tool.current_version.config` 的最小必要信息，至少让前端拿到 `output_schema`

### 前端

前端在任务详情页引入一个独立的可视化面板组件，不影响现有状态卡、时间线、日志和下载区。

#### 1. 新增结果可视化面板

建议文件：

- `frontend/src/components/tasks/ResultVisualizationPanel.vue`
- `frontend/src/components/tasks/MoleculeViewer.vue`
- `frontend/src/components/tasks/result-visualization.ts`

职责划分：

- `ResultVisualizationPanel`
  - 识别任务输入/输出文件中哪些可预览
  - 组织 viewer 所需的数据模型
  - 处理空态、错误态、降级提示
- `MoleculeViewer`
  - 封装统一 Viewer 的初始化、销毁、加载文件逻辑
- `result-visualization.ts`
  - 负责文件类型识别、展示优先级和组合规则

#### 2. 文件识别规则

首批支持：

- 结构类：`.pdb`、`.cif`、`.mmcif`、`.pdbqt`
- 小分子类：`.sdf`、`.mol2`

优先判断依据：

1. 文件扩展名
2. `content_type`
3. 必要时回退到文件名模式

#### 3. 场景组织规则

- 若输出文件中存在结构/小分子可视化文件，优先使用输出文件作为主结果
- 若输入中存在口袋/受体结构文件，且输出中存在配体/生成分子文件，则进行叠加展示
- 若只有单个结构或单个配体文件，则单独展示
- 若存在多个候选输出文件，优先：
  1. 结构主文件
  2. 小分子结果文件
  3. 其他支持预览的附属文件

## 数据流

1. 用户在工具详情页提交任务
2. 执行器返回 `result` 与 `output_file_ids`
3. worker 将 `result`、`file_ids`、`output_type` 写入 `task_outputs`
4. 任务详情接口查询任务、输入输出、关联文件元数据并返回规范响应
5. 前端任务详情页读取任务详情
6. `ResultVisualizationPanel` 根据输入/输出文件生成 viewer 模型
7. 若命中支持格式，展示可视化；否则回退到下载与 JSON 展示

## 错误处理与降级

### 后端

- 若文件 ID 不存在，接口跳过该文件并记录警告，不让整个任务详情失败
- 若输出结果中没有文件，仅返回 `output_data`

### 前端

- Viewer 初始化失败时展示错误提示，不阻塞整页
- 文件格式不支持时展示“暂不支持预览，可下载查看”
- 文件下载 URL 缺失时只展示文件名与元数据

## 测试策略

### 后端

- 新增任务详情 API 测试
  - 正常返回 `input_files` / `output_files` / `output_data`
  - 能从 `TaskOutput.file_ids` 正确展开文件元数据
  - 输入输出关系为单对象时不再按列表访问

### 前端

- 新增纯逻辑测试
  - 文件扩展名识别
  - 输入输出组合成 viewer 场景的规则
  - 不支持格式时的回退判断

### 验证

- 前端 `node --test`
- 前端 `npm run build`
- 若仓库已有后端测试入口，则运行对应 `pytest`

## 风险

- 现有任务详情字段兼容层较乱，修复时需要避免影响旧页面调用
- 若统一 Viewer 对个别格式支持不稳定，需要保留格式级降级能力
- 部分历史任务可能只有 `result`，没有 `file_ids`，需要兼容展示

## 验收标准

- 任务详情页中，`PDB/mmCIF/PDBQT` 可直接预览
- 任务详情页中，`SDF/MOL2` 可直接预览
- 输入结构 + 输出配体的任务能在一个可视化面板中显示
- 不支持格式时，页面仍可正常查看日志、原始输出和下载文件
