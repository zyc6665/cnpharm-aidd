# Result File Preview Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将任务输出中的文本、JSON、日志、表格和图片文件纳入统一结果列表，减少“未接入在线预览”提示对用户的阻断。

**Architecture:** 扩展结果项模型，为普通输出文件增加 `file` 类型和预览能力分类；使用独立通用文件预览组件按需读取受保护文件，文本/JSON 使用安全文本渲染，图片使用受控图片 URL，无法预览的文件显示元信息和下载按钮。结构文件、CSV、Typed Artifact 和当前 SDF 按需 Mol* 预览链路保持不变。

**Tech Stack:** Vue 3、TypeScript、Vitest、Ant Design Vue、现有受保护文件访问工具。

---

### Task 1: 扩展结果文件分类与结果项模型

**Files:**
- Modify: `frontend/src/domain/tasks/result-visualization.ts`
- Test: `frontend/test/task-result-visualization.test.ts`

**Step 1: Write the failing tests**

- 增加文本、JSON、日志、Markdown、图片和未知二进制输出文件。
- 断言它们进入统一结果项列表，分别标记为 `file`，并生成 `text`、`json`、`image` 或 `download` 预览分类。
- 断言结构文件、CSV 和 Artifact 不重复出现。

**Step 2: Run the focused test**

Run: `cd frontend && npx vitest run test/task-result-visualization.test.ts`

Expected: FAIL because普通输出文件当前不会生成结果项。

**Step 3: Implement the minimal model changes**

- 扩展 `VisualizationResultKind` 和结果项字段。
- 根据扩展名和 MIME 类型推导预览分类。
- 将尚未被结构、CSV 或 Artifact 占用的输出文件追加到统一结果项列表。

**Step 4: Run the focused test**

Run: `cd frontend && npx vitest run test/task-result-visualization.test.ts`

Expected: PASS。

### Task 2: 实现按需通用文件预览

**Files:**
- Create: `frontend/src/components/tasks/ResultFilePreview.vue`
- Modify: `frontend/src/components/tasks/ResultVisualizationPanel.vue`
- Test: `frontend/src/components/tasks/ResultFilePreview.spec.ts`
- Test: `frontend/src/components/tasks/ResultVisualizationPanel.spec.ts`

**Step 1: Write the failing tests**

- 文本文件按需调用 `fetchProtectedFileText` 并显示内容。
- JSON 文件自动格式化显示。
- 图片文件显示图片预览。
- 未知类型不读取内容，只显示文件名、类型、大小和下载按钮。
- 读取失败显示可理解的错误状态和下载入口。
- 结果面板选中 `file` 项时渲染通用预览组件。

**Step 2: Run the focused tests**

Run: `cd frontend && npx vitest run src/components/tasks/ResultFilePreview.spec.ts src/components/tasks/ResultVisualizationPanel.spec.ts`

Expected: FAIL because组件和 `file` 分支尚不存在。

**Step 3: Implement the minimal component**

- 复用 `fetchProtectedFileText` 和 `triggerProtectedFileDownload`。
- 文本预览限制最大读取大小，避免大日志阻塞页面。
- 使用 `<pre>` 渲染原始文本，不执行 HTML/脚本。
- 图片使用受保护 Blob URL，并在组件卸载时释放。
- 对二进制或超过限制的文件提供下载，不强行读取。

**Step 4: Integrate the panel**

- 在结果预览区增加 `file` 分支。
- 维持左右切换、统一结果列表和紧凑模式行为。
- 将原“部分结果文件未接入在线预览”提示改为轻量说明，仅在确实存在不可预览文件时展示。

**Step 5: Run the focused tests**

Run: `cd frontend && npx vitest run src/components/tasks/ResultFilePreview.spec.ts src/components/tasks/ResultVisualizationPanel.spec.ts`

Expected: PASS。

### Task 3: 更新文案、样式和回归验证

**Files:**
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Modify: `frontend/src/components/tasks/ResultVisualizationPanel.vue`
- Test: `frontend/test/task-result-visualization.test.ts`

**Step 1: Add localized labels**

- 增加文件类型、加载中、读取失败、仅下载、复制、下载和大小限制等文案。

**Step 2: Verify the complete visualization set**

Run: `cd frontend && npx vitest run test/sdf-result.test.ts test/task-result-visualization.test.ts src/components/tasks/ResultFilePreview.spec.ts src/components/tasks/ResultVisualizationPanel.spec.ts src/components/artifacts/ArtifactRenderer.spec.ts`

Expected: all focused visualization tests pass。

**Step 3: Verify type checking and build**

Run: `cd frontend && npx vue-tsc -b && npm run build`

Expected: type checking and build exit with code 0; only existing third-party `eval` and large chunk warnings may remain。

**Step 4: Verify formatting**

Run: `git diff --check`

Expected: no whitespace errors。
