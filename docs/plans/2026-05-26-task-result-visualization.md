# 任务结果可视化 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修通任务输出文件链路，并在任务详情页中为结构类与小分子类结果提供自动可视化预览。

**Architecture:** 后端先规范化 `TaskOutput.file_ids` 与任务详情接口响应，再由前端通过统一的结果可视化面板按文件类型识别并渲染支持格式。任务详情页保留现有原始输出、日志和下载区，Viewer 失败时回退到下载模式。

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3, Pinia, Ant Design Vue, Node `node:test`

---

### Task 1: 修复任务输出持久化链路

**Files:**
- Modify: `backend/app/worker/tasks.py`
- Test: `backend/tests/api/test_task_detail_visualization.py`

**Step 1: 写失败测试**

验证任务执行结果中若包含 `output_file_ids`，任务输出记录应写入 `TaskOutput.file_ids`，并能设置正确的 `output_type`。

**Step 2: 运行测试确认失败**

Run: `pytest backend/tests/api/test_task_detail_visualization.py -k output_persistence -v`

Expected: 失败，表现为 `file_ids` 未写入或 `output_type` 固定为 `json`

**Step 3: 写最小实现**

- 从 `executor.execute()` 返回值中提取 `result.result.output_file_ids`
- 写入 `TaskOutput.file_ids`
- 当存在可视化文件时，将 `output_type` 标记为 `visualization`

**Step 4: 重新运行测试确认通过**

Run: `pytest backend/tests/api/test_task_detail_visualization.py -k output_persistence -v`

Expected: PASS

### Task 2: 修复任务详情 API 的输入输出展开逻辑

**Files:**
- Modify: `backend/app/api/v1/tasks.py`
- Modify: `backend/app/schemas/tasks.py`
- Test: `backend/tests/api/test_task_detail_visualization.py`

**Step 1: 写失败测试**

验证任务详情接口：

- 不再把 `inputs` / `outputs` 当列表访问
- 能返回 `inputs.params`
- 能返回 `outputs.result`

**Step 2: 运行测试确认失败**

Run: `pytest backend/tests/api/test_task_detail_visualization.py -k task_detail_payload -v`

Expected: 失败，表现为访问关系字段方式错误或响应缺少预期结构

**Step 3: 写最小实现**

- 使用 `task.inputs.params`、`task.inputs.file_ids`
- 使用 `task.outputs.result`、`task.outputs.file_ids`、`task.outputs.output_type`
- 修正兼容字段生成逻辑

**Step 4: 重新运行测试确认通过**

Run: `pytest backend/tests/api/test_task_detail_visualization.py -k task_detail_payload -v`

Expected: PASS

### Task 3: 任务详情接口补齐文件元数据

**Files:**
- Modify: `backend/app/api/v1/tasks.py`
- Test: `backend/tests/api/test_task_detail_visualization.py`

**Step 1: 写失败测试**

验证任务详情接口可以返回：

- `input_files`
- `output_files`
- 每个文件包含 `id`、`filename`、`original_name`、`size`、`url`、`content_type`

**Step 2: 运行测试确认失败**

Run: `pytest backend/tests/api/test_task_detail_visualization.py -k file_metadata -v`

Expected: 失败，表现为缺少文件列表或字段不全

**Step 3: 写最小实现**

- 根据 `file_ids` 查询文件表
- 组装前端可消费的文件对象
- 为每个文件补 `/api/v1/files/{id}/download` URL

**Step 4: 重新运行测试确认通过**

Run: `pytest backend/tests/api/test_task_detail_visualization.py -k file_metadata -v`

Expected: PASS

### Task 4: 任务详情接口补齐工具版本可视化提示

**Files:**
- Modify: `backend/app/api/v1/tasks.py`
- Test: `backend/tests/api/test_task_detail_visualization.py`

**Step 1: 写失败测试**

验证任务详情响应可拿到工具当前版本配置中的最小必要信息，例如 `output_schema`。

**Step 2: 运行测试确认失败**

Run: `pytest backend/tests/api/test_task_detail_visualization.py -k tool_config -v`

Expected: 失败，表现为任务详情中无可视化相关配置

**Step 3: 写最小实现**

- 为任务详情查询增加 `tool.current_version`
- 返回 `tool.current_version.config` 中前端需要的最小字段

**Step 4: 重新运行测试确认通过**

Run: `pytest backend/tests/api/test_task_detail_visualization.py -k tool_config -v`

Expected: PASS

### Task 5: 新增前端结果可视化规则模块

**Files:**
- Create: `frontend/src/components/tasks/result-visualization.ts`
- Create: `frontend/test/task-result-visualization.test.ts`

**Step 1: 写失败测试**

覆盖以下规则：

- 识别 `pdb/cif/mmcif/pdbqt/sdf/mol2`
- 输入结构 + 输出小分子组合成统一场景
- 不支持格式时返回不可视化结果

**Step 2: 运行测试确认失败**

Run: `node --test frontend/test/task-result-visualization.test.ts`

Expected: FAIL，因规则模块尚不存在

**Step 3: 写最小实现**

- 实现文件扩展名识别
- 实现 viewer 场景选择逻辑
- 输出简洁的数据模型供组件消费

**Step 4: 重新运行测试确认通过**

Run: `node --test frontend/test/task-result-visualization.test.ts`

Expected: PASS

### Task 6: 新增统一结果可视化面板组件

**Files:**
- Create: `frontend/src/components/tasks/ResultVisualizationPanel.vue`
- Create: `frontend/src/components/tasks/MoleculeViewer.vue`
- Modify: `frontend/src/types/models.d.ts`
- Test: `frontend/test/task-result-visualization.test.ts`

**Step 1: 写失败测试**

至少增加源码级断言，确认任务详情页已接入可视化面板并依赖规则模块。

**Step 2: 运行测试确认失败**

Run: `node --test frontend/test/task-result-visualization.test.ts`

Expected: FAIL

**Step 3: 写最小实现**

- 封装结果可视化面板
- 封装 Viewer 生命周期
- 支持空态、错误态、回退文案

**Step 4: 重新运行测试确认通过**

Run: `node --test frontend/test/task-result-visualization.test.ts`

Expected: PASS

### Task 7: 接入任务详情页

**Files:**
- Modify: `frontend/src/views/tasks/Detail.vue`
- Modify: `frontend/src/types/models.d.ts`
- Test: `frontend/test/task-result-visualization.test.ts`

**Step 1: 写失败测试**

验证任务详情页源码中已接入：

- `ResultVisualizationPanel`
- 新的任务结果字段消费
- 回退展示仍保留

**Step 2: 运行测试确认失败**

Run: `node --test frontend/test/task-result-visualization.test.ts`

Expected: FAIL

**Step 3: 写最小实现**

- 在输出结果区域顶部插入可视化面板
- 兼容 `output_data` / `output_files` / `tool.current_version.config`
- 保留原 JSON 和下载区作为降级路径

**Step 4: 重新运行测试确认通过**

Run: `node --test frontend/test/task-result-visualization.test.ts`

Expected: PASS

### Task 8: 端到端验证

**Files:**
- Modify: `frontend/package.json`（如需补测试脚本）
- Verify: `backend/tests/api/test_task_detail_visualization.py`
- Verify: `frontend/test/task-result-visualization.test.ts`

**Step 1: 运行后端测试**

Run: `pytest backend/tests/api/test_task_detail_visualization.py -v`

Expected: 全部通过

**Step 2: 运行前端测试**

Run: `node --test frontend/test/task-result-visualization.test.ts`

Expected: 全部通过

**Step 3: 运行前端构建**

Run: `npm run build`

Workdir: `frontend`

Expected: 构建成功

**Step 4: 记录遗留问题**

- 历史任务若没有 `file_ids` 仅展示原始结果
- 不支持格式保持下载模式

**Step 5: 不提交 git**

本轮按主人要求直接实现，不自动执行 `git commit`
