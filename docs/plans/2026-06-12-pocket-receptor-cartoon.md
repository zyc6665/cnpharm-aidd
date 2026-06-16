# Pocket Receptor Cartoon Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让任务详情页中的口袋受体输入按 cartoon 显示，同时不影响输出小分子的现有展示。

**Architecture:** 复用现有 `VisualizationSceneEntry.role` 语义，在 `MoleculeViewer.vue` 按 `receptor` 条目分支传入 Mol* 受体专用表示 preset。测试通过源码断言锁定该行为，避免回归。

**Tech Stack:** Vue 3, TypeScript, Mol*，Node 内置测试运行器

---

### Task 1: 锁定受体专用表示测试

**Files:**
- Modify: `frontend/test/task-result-visualization.test.ts`

**Step 1: Write the failing test**

新增断言，要求 `MoleculeViewer.vue` 中存在 `role === 'receptor'` 的专用处理以及 `polymer-cartoon` preset。

**Step 2: Run test to verify it fails**

Run: `npm test -- task-result-visualization.test.ts`

**Step 3: Write minimal implementation**

在 `frontend/src/components/tasks/MoleculeViewer.vue` 中为受体条目构建专用 Mol* 加载选项。

**Step 4: Run test to verify it passes**

Run: `npm test -- task-result-visualization.test.ts`

### Task 2: 实现受体 cartoon 表示

**Files:**
- Modify: `frontend/src/components/tasks/MoleculeViewer.vue`

**Step 1: Add receptor-only load options**

根据 `entry.role` 生成 Mol* 加载选项；受体使用 `representation: 'polymer-cartoon'`，其他条目维持默认。

**Step 2: Keep ligand output unchanged**

确认输出小分子依旧使用当前默认加载逻辑，不额外修改 ligand 表示。

**Step 3: Verify**

Run: `npm test -- task-result-visualization.test.ts`
