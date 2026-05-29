# CSV 结果可视化 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为任务详情页新增通用 CSV 结果预览能力，在表格中按行展示结果，并在可识别 SMILES 的情况下追加 2D 分子结构列。

**Architecture:** 保留现有 3D 结构结果可视化规则不动，在 `ResultVisualizationPanel` 上增加 CSV 分支。CSV 分支通过受保护文件下载拉取文本、前端解析为表格数据，并通过启发式规则识别 SMILES 列，再用浏览器端 2D 分子渲染组件嵌入到表格单元格中。表格区域使用固定高度和内部滚动，避免页面无限拉长。

**Tech Stack:** Vue 3, Ant Design Vue, Papa Parse, Smiles Drawer, Node `node:test`

---

### Task 1: 新增 CSV 结果规则与测试

**Files:**
- Create: `frontend/src/components/tasks/csv-result.ts`
- Create: `frontend/test/task-csv-visualization.test.ts`

**Step 1: 写失败测试**

覆盖：

- 识别 `text/csv` 或 `.csv` 输出文件
- 识别表头命中 `smiles/canonical_smiles/...`
- 识别空表头但内容看起来像 SMILES 的列

**Step 2: 运行测试确认失败**

Run: `node --test test/task-csv-visualization.test.ts`

Expected: FAIL，规则模块不存在

**Step 3: 写最小实现**

- 实现 CSV 文件识别
- 实现 CSV 行列归一化
- 实现 SMILES 列启发式识别

**Step 4: 重新运行测试确认通过**

Run: `node --test test/task-csv-visualization.test.ts`

Expected: PASS

### Task 2: 新增 2D 分子图单元格组件

**Files:**
- Create: `frontend/src/components/tasks/Smiles2DCell.vue`
- Test: `frontend/test/task-csv-visualization.test.ts`

**Step 1: 写失败测试**

至少用源码级断言确认组件存在并使用 `smiles-drawer`。

**Step 2: 运行测试确认失败**

Run: `node --test test/task-csv-visualization.test.ts`

Expected: FAIL

**Step 3: 写最小实现**

- 用 `SmilesDrawer.SvgDrawer` 渲染单个 SMILES
- 提供错误态和空值态
- 将结构图尺寸限制在表格单元格内

**Step 4: 重新运行测试确认通过**

Run: `node --test test/task-csv-visualization.test.ts`

Expected: PASS

### Task 3: 新增 CSV 结果表格面板

**Files:**
- Create: `frontend/src/components/tasks/CsvResultViewer.vue`
- Modify: `frontend/src/utils/protected-file-access.ts`
- Test: `frontend/test/protected-file-access.test.ts`
- Test: `frontend/test/task-csv-visualization.test.ts`

**Step 1: 写失败测试**

验证：

- 能以鉴权方式拉取 CSV 文本
- 结果表格有固定高度并支持内部滚动
- 有 SMILES 列时追加结构图列

**Step 2: 运行测试确认失败**

Run: `node --test test/protected-file-access.test.ts test/task-csv-visualization.test.ts`

Expected: FAIL

**Step 3: 写最小实现**

- 扩展受保护文件访问工具，支持拉取文本
- 使用 `Papa.parse` 解析 CSV
- 使用 Ant Design Vue 表格显示数据并配置 `scroll.y`

**Step 4: 重新运行测试确认通过**

Run: `node --test test/protected-file-access.test.ts test/task-csv-visualization.test.ts`

Expected: PASS

### Task 4: 接入任务详情结果面板

**Files:**
- Modify: `frontend/src/components/tasks/ResultVisualizationPanel.vue`
- Modify: `frontend/src/components/tasks/result-visualization.ts`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Test: `frontend/test/task-result-visualization.test.ts`

**Step 1: 写失败测试**

验证任务详情结果面板源码中已优先接入 CSV viewer，并保留原有 3D 可视化分支。

**Step 2: 运行测试确认失败**

Run: `node --test test/task-result-visualization.test.ts test/task-csv-visualization.test.ts`

Expected: FAIL

**Step 3: 写最小实现**

- 在结果面板优先检查 CSV 输出文件
- 有 CSV 时展示 CSV 表格 viewer
- 没有 CSV 时继续走现有结构文件 viewer

**Step 4: 重新运行测试确认通过**

Run: `node --test test/task-result-visualization.test.ts test/task-csv-visualization.test.ts`

Expected: PASS

### Task 5: 运行构建与真实任务验证

**Files:**
- Verify: `frontend/src/components/tasks/CsvResultViewer.vue`
- Verify: `frontend/src/components/tasks/ResultVisualizationPanel.vue`

**Step 1: 运行前端测试**

Run: `node --test test/protected-file-access.test.ts test/task-result-visualization.test.ts test/task-csv-visualization.test.ts`

Expected: PASS

**Step 2: 运行构建**

Run: `npm run build`

Expected: PASS

**Step 3: 用真实任务校验**

检查 `MolP-PC Property Prediction` 的 CSV 输出是否能在任务详情页显示为带结构列的滚动表格。
