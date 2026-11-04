# 设计流程 UX（结构预测 / 口袋预测纳入设计主链路）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把结构预测、口袋预测纳入「设计」主链路，让用户在一个连续的地方完成「结构 → 口袋 → 分子设计 → 评估」，并消除「选不到口袋」的死路。

**Architecture:** 复用后端 `GET /projects/{id}/stage`（`ProjectStage` 的 counters/gaps）做就绪判定；复用并改造既有 `GuidedWorkflow`，把其结构/口袋两步从「跳外链」改为就地预测/选定；把结构/口袋预测逻辑抽成共享 composable + 组件，供既有 `Predict/Pockets` 与新的「上游接力条」同源使用；侧栏按阶段分组、新增 `/design` 流程总览页、`设计任务` 增加结构/口袋两类。

**Tech Stack:** Vue 3 + TypeScript + Ant Design Vue 4 + vue-router + vue-i18n + vitest(jsdom)

**Spec:** `docs/superpowers/specs/2026-11-04-design-pipeline-ux-design.md`

## Global Constraints

- 不新增后端端点；仅复用 `api/targets.ts`（`predictStructure/predictPockets/selectPocket/listStructures/listPockets`）、`api/decisions.ts`（`getProjectStage`）、`api/design.ts`、`api/tasks.ts`。
- 不新建并行阶段模型：就绪判定唯一真相是后端 `compute_project_stage`；前端 `pipeline.ts` 只做展示映射。
- 不写第二套预测逻辑：`Predict.vue` / `Pockets.vue` 与新组件共用同一 composable（`useStructurePrediction` / `usePocketPrediction` / `useStructurePockets`）。
- 所有新增 UI 文案必须同时补 `locales/zh-CN/index.ts` 与 `locales/en-US/index.ts`，组件内不硬编码中文。
- 样式用现有语义 token / LESS 变量（`@accent-color`、`@text-secondary` 等），不写裸十六进制色值；暗色为默认。
- 任务 slug 常量集中放 `types/design.ts`：`STRUCTURE_PREDICT_TOOL_SLUG='boltz2-structure-prediction'`、`POCKET_PREDICT_TOOL_SLUG='lvpocket-pocket-prediction'`。
- 阶段命名唯一来源：`domain/design/pipeline.ts` 的 `DESIGN_STAGES`（总览 / 引导 / 设计任务共用）。

## Review Focus

- **空数据项目（0 靶点 / 0 结构）**：`/design` 总览与接力条必须给可操作引导，不白屏、不抛错。
- **有结构但 0 个已选口袋**（gap `NO_POCKET_SELECTED`）：接力条给「预测口袋 / 选定」入口，而不是旧的「请先在结构详情中标记口袋」死提示。
- **结构/口袋预测失败或超时**：就地显示错误并可重试，界面不能卡在 loading。
- **并发 / 多次预测**：完成后「取新增的一条」而不是盲取 `items[0]`，避免误选旧结构/口袋。
- **无项目权限或项目列表为空**：`/design` 给出「选择/新建项目」引导而非报错。
- **i18n 回退**：英文环境下不出现中文键值；新增 key 两语言齐全。

---

### Task 1: 任务 slug 常量 + 设计任务新增「结构预测 / 口袋预测」两类

**Files:**
- Modify: `frontend/src/types/design.ts`
- Modify: `frontend/src/domain/design/runs.ts`
- Modify: `frontend/src/locales/zh-CN/index.ts` (`design.runs.category.structure/pocket`)
- Modify: `frontend/src/locales/en-US/index.ts` (同 key)
- Test: `frontend/src/domain/design/runs.spec.ts` (新建)

**Interfaces:**
- Produces: `types/design.ts` 追加
  ```ts
  export const STRUCTURE_PREDICT_TOOL_SLUG = 'boltz2-structure-prediction'
  export const POCKET_PREDICT_TOOL_SLUG = 'lvpocket-pocket-prediction'
  ```
- Produces: `DESIGN_RUN_CATEGORIES` 顺序变为 `structure, pocket, molecule, peptide, predict, screening, md, freeEnergy`；`key:'structure'|'pocket'` 的 `resultPath` 返回 `/tasks/${taskId}`（结构/口袋任务无专属结果页，落通用任务详情）。
- Consumes: 既有 `DesignRunCategory`、`findDesignRunCategory`、`resolveDesignRunPath` 保持不变。

- [ ] **Step 1: 写失败测试**

```ts
// frontend/src/domain/design/runs.spec.ts
import { describe, it, expect } from 'vitest'
import {
  DESIGN_RUN_CATEGORIES, ALL_DESIGN_TOOL_SLUGS, findDesignRunCategory, resolveDesignRunPath
} from './runs'
import { STRUCTURE_PREDICT_TOOL_SLUG, POCKET_PREDICT_TOOL_SLUG } from '@/types/design'

describe('design runs categories', () => {
  it('contains structure and pocket as first two categories', () => {
    expect(DESIGN_RUN_CATEGORIES.slice(0, 2).map(c => c.key)).toEqual(['structure', 'pocket'])
    expect(DESIGN_RUN_CATEGORIES[0]!.slugs).toEqual([STRUCTURE_PREDICT_TOOL_SLUG])
    expect(DESIGN_RUN_CATEGORIES[1]!.slugs).toEqual([POCKET_PREDICT_TOOL_SLUG])
  })
  it('ALL_DESIGN_TOOL_SLUGS includes both and has no duplicates', () => {
    expect(ALL_DESIGN_TOOL_SLUGS).toContain(STRUCTURE_PREDICT_TOOL_SLUG)
    expect(ALL_DESIGN_TOOL_SLUGS).toContain(POCKET_PREDICT_TOOL_SLUG)
    expect(new Set(ALL_DESIGN_TOOL_SLUGS).size).toBe(ALL_DESIGN_TOOL_SLUGS.length)
  })
  it('maps a structure task to its category and task-detail path', () => {
    expect(findDesignRunCategory(STRUCTURE_PREDICT_TOOL_SLUG)?.key).toBe('structure')
    expect(resolveDesignRunPath(STRUCTURE_PREDICT_TOOL_SLUG, 't1')).toBe('/tasks/t1')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm run test -- src/domain/design/runs.spec.ts`
Expected: FAIL（`STRUCTURE_PREDICT_TOOL_SLUG` 未导出 / 类别数不符）

- [ ] **Step 3: 实现**

在 `types/design.ts` 追加两个 slug 常量（放 `MOLECULE_GENERATION_TOOL_SLUG` 附近）。
在 `runs.ts` 顶部 `import { ..., STRUCTURE_PREDICT_TOOL_SLUG, POCKET_PREDICT_TOOL_SLUG } from '@/types/design'`，在 `DESIGN_RUN_CATEGORIES` 数组最前插入：
```ts
{ key: 'structure', slugs: [STRUCTURE_PREDICT_TOOL_SLUG], resultPath: t => `/tasks/${t}` },
{ key: 'pocket', slugs: [POCKET_PREDICT_TOOL_SLUG], resultPath: t => `/tasks/${t}` },
```
两个 locale 的 `design.runs.category` 下加 `structure: '结构预测' / 'Structure Prediction'`、`pocket: '口袋预测' / 'Pocket Prediction'`。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npm run test -- src/domain/design/runs.spec.ts`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/types/design.ts frontend/src/domain/design/runs.ts frontend/src/domain/design/runs.spec.ts frontend/src/locales
git commit -m "feat(design): add structure/pocket task categories to design runs"
```

---

### Task 2: `pipeline.ts` —— 从 `ProjectStage` 映射设计视角 5 段

**Files:**
- Create: `frontend/src/domain/design/pipeline.ts`
- Test: `frontend/src/domain/design/pipeline.spec.ts`

**Interfaces:**
- Consumes: `ProjectStage`, `StageGap`, `StageCounters` from `@/types/decisions`。
- Produces:
  ```ts
  export type DesignStageKey = 'structure' | 'pocket' | 'molecule' | 'evaluation' | 'validation'
  export type StageReadiness = 'ready' | 'missing' | 'empty'
  export interface DesignStageDef {
    key: DesignStageKey; order: number; labelKey: string;
    counterKey: keyof StageCounters; gapCode: string; defaultPath: (projectId: string) => string
  }
  export const DESIGN_STAGES: readonly DesignStageDef[]
  export interface DesignStageState {
    key: DesignStageKey; order: number; labelKey: string;
    readiness: StageReadiness; count: number;
    gap: StageGap | null; primaryPath: string
  }
  export function buildDesignStages(stage: ProjectStage | null, projectId: string): DesignStageState[]
  export function firstMissingStage(states: readonly DesignStageState[]): DesignStageState | null
  ```
- 映射：structure←`counters.structures`/`NO_STRUCTURE`；pocket←`selected_pockets`/`NO_POCKET_SELECTED`；molecule←`candidates`/`NO_CANDIDATE`；evaluation←`submitted_tasks`/`NO_TASK`；validation←`finished_tasks`/`NO_TASK`。
- `readiness`：`stage===null` → `'empty'`；`count>0` → `'ready'`；否则 `'missing'`。
- `primaryPath`：`gap.link ?? def.defaultPath(projectId)`；`defaultPath`：molecule→`/design/molecules?project_id=${id}`、evaluation→`/predict?project_id=${id}`、validation→`/md?project_id=${id}`、structure/pocket→`/projects/${id}/targets`。

- [ ] **Step 1: 写失败测试**

```ts
// frontend/src/domain/design/pipeline.spec.ts
import { describe, it, expect } from 'vitest'
import { buildDesignStages, firstMissingStage, DESIGN_STAGES } from './pipeline'
import type { ProjectStage } from '@/types/decisions'

const stage: ProjectStage = {
  currentStage: 'S2', stageName: '结构与口袋就绪',
  reachedStages: ['S0', 'S1', 'S2'], nextStage: 'S3',
  counters: { targets: 1, structures: 2, selected_pockets: 0, candidates: 0, submitted_tasks: 0, finished_tasks: 0, decisions: 0 },
  gaps: [{ code: 'NO_POCKET_SELECTED', message: '未选定口袋', action: '选定口袋', link: '/projects/p1/targets' }],
}

describe('buildDesignStages', () => {
  it('exposes five ordered stages', () => {
    expect(DESIGN_STAGES.map(s => s.key)).toEqual(['structure', 'pocket', 'molecule', 'evaluation', 'validation'])
  })
  it('marks readiness from counters and picks gap link as primaryPath', () => {
    const states = buildDesignStages(stage, 'p1')
    expect(states[0]).toMatchObject({ key: 'structure', readiness: 'ready', count: 2 })
    expect(states[1]).toMatchObject({ key: 'pocket', readiness: 'missing', count: 0, primaryPath: '/projects/p1/targets' })
    expect(states[2]!.primaryPath).toBe('/design/molecules?project_id=p1')
  })
  it('returns all empty when stage is null', () => {
    expect(buildDesignStages(null, 'p1').every(s => s.readiness === 'empty')).toBe(true)
  })
  it('firstMissingStage returns the first non-ready stage', () => {
    expect(firstMissingStage(buildDesignStages(stage, 'p1'))?.key).toBe('pocket')
  })
})
```

- [ ] **Step 2: 运行确认失败** — `cd frontend && npm run test -- src/domain/design/pipeline.spec.ts` → FAIL（模块不存在）
- [ ] **Step 3: 实现 `pipeline.ts`**（按上面 Interfaces；`buildDesignStages` 遍历 `DESIGN_STAGES`，按 `counterKey` 取 `counters`，在 `stage.gaps` 中按 `gapCode` 找 gap）
- [ ] **Step 4: 运行确认通过** — 同上命令 → PASS
- [ ] **Step 5: 提交**

```bash
git add frontend/src/domain/design/pipeline.ts frontend/src/domain/design/pipeline.spec.ts
git commit -m "feat(design): add ProjectStage -> design pipeline stage adapter"
```

---

### Task 3: 共享预测逻辑（composables + 组件）

**Files:**
- Create: `frontend/src/composables/useTaskCompletion.ts`
- Create: `frontend/src/composables/useStructurePrediction.ts`
- Create: `frontend/src/composables/usePocketPrediction.ts`
- Create: `frontend/src/composables/useStructurePockets.ts`
- Create: `frontend/src/components/design/StructurePredictForm.vue`
- Create: `frontend/src/components/design/PocketPredictPanel.vue`
- Test: `frontend/src/composables/useStructurePrediction.spec.ts`, `useStructurePockets.spec.ts`, `useTaskCompletion.spec.ts`

**Interfaces:**
- Produces `waitForTaskCompletion(taskId: string, opts?: { pollMs?: number; timeoutMs?: number }): Promise<{ status: TaskStatus; ok: boolean }>` — 用 `openTaskEventStream`（`onDone`/`onStatus` 终态）resolve；`available===false` 或 error 时回退 `getTaskDetail` 轮询（默认 `pollMs=3000`、`timeoutMs=600000`）。
- Produces `useStructurePrediction()`：`{ form: {modelName:string;numRecycles:number;seed:number;useMsa:boolean}, submitting: Ref<boolean>, error: Ref<string>, submit(proteinId:string): Promise<string|null> }`；`submit` 校验 `numRecycles>=1 && seed>=0`，否则置 `error` 返回 null；调用 `predictStructure(proteinId, { model_ref:{name}, params:{useMsa,numRecycles,seed} })` 返回 `task_id`。
- Produces `usePocketPrediction()`：`{ predicting: Ref<boolean>, error: Ref<string>, predict(structureId:string): Promise<string|null> }`；调用 `predictPockets(structureId, {})` 返回 `task_id`。
- Produces `useStructurePockets(structureId: Ref<string>)`：`{ pockets: Ref<PocketSummary[]>, loading, error, selectingId, load():Promise<void>, select(pocketId:string):Promise<void>, selected: ComputedRef<PocketSummary|null>, sorted: ComputedRef<PocketSummary[]> }`；`select` 调 `selectPocket(id,true)` 后 `load()`。
- Produces `StructurePredictForm.vue`：props `{ proteinId: string }`；emits `submitted(taskId:string)`、`completed(taskId:string)`、`error(msg:string)`；内部用 `useStructurePrediction` + `waitForTaskCompletion`（提交后 `submitted`，终态 `completed`）。
- Produces `PocketPredictPanel.vue`：props `{ structureId: string }`；emits `selected(pocket: PocketSummary)`、`predicted(taskId:string)`；内部用 `usePocketPrediction` + `useStructurePockets` + `waitForTaskCompletion`。

- [ ] **Step 1: 写失败测试（三个 composable 各一个最小用例）**

```ts
// useStructurePrediction.spec.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
vi.mock('@/api/targets', () => ({ predictStructure: vi.fn() }))
import { predictStructure } from '@/api/targets'
import { useStructurePrediction } from './useStructurePrediction'
describe('useStructurePrediction', () => {
  beforeEach(() => vi.mocked(predictStructure).mockReset())
  it('rejects invalid numbers', async () => {
    const p = useStructurePrediction()
    p.form.numRecycles = 0
    expect(await p.submit('protein-1')).toBeNull()
    expect(predictStructure).not.toHaveBeenCalled()
  })
  it('submits payload and returns task id', async () => {
    vi.mocked(predictStructure).mockResolvedValue({ data: { task_id: 'task-1' } } as never)
    const p = useStructurePrediction()
    expect(await p.submit('protein-1')).toBe('task-1')
    expect(predictStructure).toHaveBeenCalledWith('protein-1', {
      model_ref: { name: 'boltz-2' }, params: { useMsa: false, numRecycles: 3, seed: 42 },
    })
  })
})
```

```ts
// useStructurePockets.spec.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
vi.mock('@/api/targets', () => ({ listPockets: vi.fn(), selectPocket: vi.fn() }))
import { ref } from 'vue'
import { listPockets, selectPocket } from '@/api/targets'
import { useStructurePockets } from './useStructurePockets'
describe('useStructurePockets', () => {
  beforeEach(() => { vi.mocked(listPockets).mockReset(); vi.mocked(selectPocket).mockReset() })
  it('loads, sorts and exposes selected pocket', async () => {
    vi.mocked(listPockets).mockResolvedValue({ data: { items: [
      { id: 'b', rank: 2, score: 0.5, selected: false }, { id: 'a', rank: 1, score: 0.9, selected: true },
    ] } } as never)
    const c = useStructurePockets(ref('s1'))
    await c.load()
    expect(c.sorted.value.map(p => p.id)).toEqual(['a', 'b'])
    expect(c.selected.value?.id).toBe('a')
  })
})
```

```ts
// useTaskCompletion.spec.ts（jsdom 无 EventSource → 走轮询兜底）
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
vi.mock('@/api/tasks', () => ({ getTaskDetail: vi.fn() }))
import { getTaskDetail } from '@/api/tasks'
import { waitForTaskCompletion } from './useTaskCompletion'
describe('waitForTaskCompletion', () => {
  beforeEach(() => { vi.useFakeTimers(); vi.mocked(getTaskDetail).mockReset() })
  afterEach(() => vi.useRealTimers())
  it('resolves when polled status becomes success', async () => {
    vi.mocked(getTaskDetail)
      .mockResolvedValueOnce({ data: { status: 'running' } } as never)
      .mockResolvedValueOnce({ data: { status: 'success' } } as never)
    const promise = waitForTaskCompletion('t1', { pollMs: 10 })
    await vi.advanceTimersByTimeAsync(30)
    expect((await promise).ok).toBe(true)
  })
})
```

- [ ] **Step 2: 运行确认失败** — `cd frontend && npm run test -- src/composables/useStructurePrediction.spec.ts src/composables/useStructurePockets.spec.ts src/composables/useTaskCompletion.spec.ts` → FAIL（模块不存在）
- [ ] **Step 3: 实现三个 composable + 两个组件**

实现要点：`useTaskCompletion` 先 `openTaskEventStream`（`handlers.onDone` 或 `onStatus` 且 `payload.terminal` 时 resolve），若 `!handle.available` 或 `onError` 则 `startPolling()`（`setTimeout` 递归 `getTaskDetail`，`isTerminalTask` 为真时按 `status==='success'` resolve）。组件模板用 `a-form`/`a-table`，沿用 `targets.predict` / `targets.pockets` 文案键与 `data-testid`（`structure-predict-form`、`pocket-predict-panel`、`pocket-predict-button`、`pocket-select-button`）。

- [ ] **Step 4: 运行确认通过** — 同上命令 → PASS
- [ ] **Step 5: 提交**

```bash
git add frontend/src/composables/use*.ts frontend/src/components/design frontend/src/composables/*.spec.ts
git commit -m "feat(design): add shared structure/pocket prediction composables and components"
```

---

### Task 4: 侧栏按阶段分组（设计流程）

**Files:**
- Create: `frontend/src/domain/design/navigation.ts`
- Modify: `frontend/src/components/layout/AppShell.vue`（`designNav` → 分组渲染）
- Modify: `frontend/src/locales/zh-CN/index.ts`、`en-US/index.ts`（nav 分组与新增项）
- Test: `frontend/src/domain/design/navigation.spec.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface DesignNavItem { key: string; to: string; labelKey: string; isNew?: boolean }
  export interface DesignNavGroup { groupKey: string; labelKey: string; items: DesignNavItem[] }
  export function buildDesignNavGroups(): DesignNavGroup[]
  ```
- 顺序：组 `prepare`(structurePredict `/design/structure`, pocketPredict `/design/pocket`, 均 `isNew`) → `design`(molecules `/design/molecules`, peptides `/design/peptides`, screen `/screen`) → `evaluate`(predict `/predict`, md `/md`) → `record`(designRuns `/design/runs`)。
- Consumes（AppShell）：按 `item.key` 映射图标（`DeploymentUnitOutlined`/`ClusterOutlined`/`LineChartOutlined`/`FilterOutlined`/`ThunderboltOutlined`/`HistoryOutlined` + 新增 `NodeIndexOutlined`(结构)/`AimOutlined`(口袋)）。

- [ ] **Step 1: 写失败测试**

```ts
// navigation.spec.ts
import { describe, it, expect } from 'vitest'
import { buildDesignNavGroups } from './navigation'
describe('buildDesignNavGroups', () => {
  it('groups stages in pipeline order and ends with design runs', () => {
    const groups = buildDesignNavGroups()
    expect(groups.map(g => g.groupKey)).toEqual(['prepare', 'design', 'evaluate', 'record'])
    expect(groups[0]!.items.map(i => i.key)).toEqual(['structurePredict', 'pocketPredict'])
    expect(groups.at(-1)!.items.map(i => i.key)).toEqual(['designRuns'])
  })
})
```

- [ ] **Step 2: 运行确认失败** — `cd frontend && npm run test -- src/domain/design/navigation.spec.ts` → FAIL
- [ ] **Step 3: 实现 `navigation.ts`，并改 `AppShell.vue`**：把 `designNav` 常量替换为 `buildDesignNavGroups()`；模板在 `sidebar-design-nav` 内 `v-for group` 渲染 `group-label`（折叠态隐藏）与组内 `router-link`；图标用 `key→Component` 映射表。i18n 加 `nav.designPipeline/designGroupPrepare/designGroupDesign/designGroupEvaluate/designGroupRecord/structurePredict/pocketPredict` 及不同语言值。
- [ ] **Step 4: 运行测试 + 类型检查** — `npm run test -- src/domain/design/navigation.spec.ts` → PASS；`npx vue-tsc -b` 无错
- [ ] **Step 5: 提交**

```bash
git add frontend/src/domain/design/navigation.ts frontend/src/domain/design/navigation.spec.ts frontend/src/components/layout/AppShell.vue frontend/src/locales
git commit -m "feat(nav): group design sidebar into pipeline stages, add structure/pocket entries"
```

---

### Task 5: `/design` 流程总览页（含引导流程入口）

**Files:**
- Create: `frontend/src/views/design/Pipeline.vue`
- Modify: `frontend/src/router/index.ts`（新增 `/design` 路由，`name:'DesignPipeline'`，`meta.title:'design.pipeline.title'`）
- Modify: `frontend/src/locales/zh-CN/index.ts`、`en-US/index.ts`（`design.pipeline.*`）
- Test: `frontend/src/views/design/Pipeline.spec.ts`

**Interfaces:**
- Consumes: `listDesignProjects`(`api/design`)、`getProjectStage`(`api/decisions`)、`buildDesignStages`/`firstMissingStage`(`domain/design/pipeline`)、`GuidedWorkflow`(`views/workflow/GuidedWorkflow.vue`, props `{ projectId: string }`)。
- 关键 `data-testid`：`design-pipeline-page`、`design-pipeline-project`、`design-stage-card`（每卡）、`design-stage-missing-count`、`design-pipeline-continue`。
- 行为：进入读 query `project_id` → localStorage `design:lastProjectId` → 项目列表首项；选中项目后 `getProjectStage` 渲染 5 卡（状态徽标 ready/missing/empty、计数、主按钮 `primaryPath`）；「继续设计流程」把 `GuidedWorkflow` 展开在页内（同一 projectId）。

- [ ] **Step 1: 写失败测试**

```ts
// Pipeline.spec.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
vi.mock('@/api/design', () => ({ listDesignProjects: vi.fn() }))
vi.mock('@/api/decisions', () => ({ getProjectStage: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: { project_id: 'p1' } }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/views/workflow/GuidedWorkflow.vue', () => ({ default: { name: 'GuidedWorkflow', template: '<div data-testid="guided-stub" />' } }))
import { listDesignProjects } from '@/api/design'
import { getProjectStage } from '@/api/decisions'
import Pipeline from './Pipeline.vue'
describe('Pipeline', () => {
  beforeEach(() => {
    vi.mocked(listDesignProjects).mockResolvedValue([{ id: 'p1', name: 'P1' }] as never)
    vi.mocked(getProjectStage).mockResolvedValue({ data: {
      currentStage: 'S1', stageName: '靶点确立', reachedStages: ['S0','S1'], nextStage: 'S2',
      counters: { targets: 1, structures: 0, selected_pockets: 0, candidates: 0, submitted_tasks: 0, finished_tasks: 0, decisions: 0 },
      gaps: [{ code: 'NO_STRUCTURE', message: 'x', action: '预测结构', link: '/projects/p1/targets' }],
    } } as never)
  })
  it('renders five stage cards', async () => {
    const w = mount(Pipeline)
    await new Promise(r => setTimeout(r))
    expect(w.findAll('[data-testid="design-stage-card"]').length).toBe(5)
  })
})
```

- [ ] **Step 2: 运行确认失败** — `cd frontend && npm run test -- src/views/design/Pipeline.spec.ts` → FAIL
- [ ] **Step 3: 实现 `Pipeline.vue` + 路由 + i18n**（组件挂载时按上面优先级解析 projectId；`catch` 时空态给「选择/新建项目」；用 `buildDesignStages(stage, projectId)` 渲染；点「继续」切换 `showGuided`）
- [ ] **Step 4: 运行测试 + 类型检查** — 上述测试 PASS；`npx vue-tsc -b` 无错
- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/design/Pipeline.vue frontend/src/views/design/Pipeline.spec.ts frontend/src/router/index.ts frontend/src/locales
git commit -m "feat(design): add /design pipeline overview page"
```

---

### Task 6: GuidedWorkflow 前两步就地化（结构预测 / 口袋预测）

**Files:**
- Modify: `frontend/src/views/workflow/GuidedWorkflow.vue`
- Test: `frontend/src/views/workflow/GuidedWorkflow.spec.ts`

**Interfaces:**
- Consumes: `StructurePredictForm`、`PocketPredictPanel`（Task 3）；`listStructures`/`listPockets`（`api/targets`）。
- 行为：`structure` 步不再 `router.push('/proteins/:id/predict')`，改为内嵌 `<StructurePredictForm :protein-id>`；`@completed` → 重新 `listStructures(proteinId)` 取「新增的一条」（提交前记录 id 集合），更新 `structure`/`structureCount` 并 `current=1`。
- `pocket` 步不再跳 `/structures/:id/pockets`，改为内嵌 `<PocketPredictPanel :structure-id>`；`@selected` → 刷新口袋计数并 `current=2`；`@predicted` → `waitForTaskCompletion` 后刷新口袋列表。
- 保留「去结构详情/去口袋页」次链接（作为高级入口）。

- [ ] **Step 1: 写失败测试**

```ts
// GuidedWorkflow.spec.ts
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
vi.mock('@/api/targets', () => ({
  listTargets: vi.fn().mockResolvedValue({ data: { items: [{ id: 't1' }] } }),
  getTarget: vi.fn().mockResolvedValue({ data: { proteins: [{ id: 'pr1' }] } }),
  listStructures: vi.fn().mockResolvedValue({ data: { items: [{ id: 's1' }] } }),
  listPockets: vi.fn().mockResolvedValue({ data: { items: [] } }),
}))
vi.mock('@/api/compounds', () => ({ listCandidates: vi.fn().mockResolvedValue({ data: { total: 0 } }) }))
vi.mock('@/api/results', () => ({ listProjectResults: vi.fn().mockResolvedValue({ data: { total: 0 } }) }))
import GuidedWorkflow from './GuidedWorkflow.vue'
describe('GuidedWorkflow', () => {
  it('embeds the structure predict form instead of a link-out button', async () => {
    const w = mount(GuidedWorkflow, { props: { projectId: 'p1' } })
    await new Promise(r => setTimeout(r))
    expect(w.find('[data-testid="structure-predict-form"]').exists()).toBe(true)
    expect(w.text()).not.toContain('去结构预测')
  })
})
```

- [ ] **Step 2: 运行确认失败** — `cd frontend && npm run test -- src/views/workflow/GuidedWorkflow.spec.ts` → FAIL
- [ ] **Step 3: 实现改动**（替换两个 `stage-panel` 内容；新增「提交前记录 id 集合→完成后取新增」逻辑；删除/降级两个 `goProteinPredict`/`goPockets` 主按钮为次链接）
- [ ] **Step 4: 运行确认通过** — 上述测试 PASS；`npx vue-tsc -b` 无错
- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/workflow/GuidedWorkflow.vue frontend/src/views/workflow/GuidedWorkflow.spec.ts
git commit -m "feat(workflow): inline structure/pocket prediction in guided workflow"
```

---

### Task 7: 上游接力条 —— PocketPicker 改造为步骤条 + 就地补票

**Files:**
- Modify: `frontend/src/views/design/components/PocketPicker.vue`
- Test: `frontend/src/views/design/components/PocketPicker.spec.ts`

**Interfaces:**
- Consumes: 既有 `listDesignProjects/listProjectTargets/loadTargetProteins/listProteinStructures/listStructurePockets`；`StructurePredictForm`、`PocketPredictPanel`（Task 3）。
- 行为：顶部渲染 5 步 stepper（项目→靶点→蛋白→结构→口袋）；保留原有 5 个下拉作为「精确选择」；当 `selectedStructure && pockets.length===0` 时，不再只显示死提示，而是渲染 `<PocketPredictPanel :structure-id>`；当 `selectedProtein && structures.length===0` 时渲染 `<StructurePredictForm :protein-id>`，`@completed` 后重新拉结构并默认选中新增项，emit 更新。
- 选区过滤：口袋列表仍只显示 `pocket.selected`（保持与后端 `input_bindings` 语义一致）；`PocketPredictPanel` 内的「选定」可把某口袋设为 selected。
- 保留 `data-testid`：`pocket-picker`、`pocket-project`、`pocket-target`、`pocket-protein`、`pocket-structure`、`pocket-pocket`；新增 `pocket-stepper`、`pocket-missing-structure`、`pocket-missing-pocket`。

- [ ] **Step 1: 写失败测试**

```ts
// PocketPicker.spec.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
vi.mock('@/api/design', () => ({
  listDesignProjects: vi.fn().mockResolvedValue([{ id: 'p1', name: 'P1' }]),
  listProjectTargets: vi.fn().mockResolvedValue([{ id: 't1', name: 'T' }]),
  loadTargetProteins: vi.fn().mockResolvedValue([{ id: 'pr1', name: 'P' }]),
  listProteinStructures: vi.fn().mockResolvedValue([{ id: 's1', source_type: 'predicted' }]),
  listStructurePockets: vi.fn().mockResolvedValue([]),
}))
vi.mock('@/components/design/StructurePredictForm.vue', () => ({ default: { template: '<div data-testid="structure-predict-form" />' } }))
vi.mock('@/components/design/PocketPredictPanel.vue', () => ({ default: { template: '<div data-testid="pocket-predict-panel" />' } }))
import PocketPicker from './PocketPicker.vue'
describe('PocketPicker', () => {
  beforeEach(() => vi.clearAllMocks())
  it('renders a stepper', () => {
    const w = mount(PocketPicker, { props: { modelValue: null } })
    expect(w.find('[data-testid="pocket-stepper"]').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: 运行确认失败** — `cd frontend && npm run test -- src/views/design/components/PocketPicker.spec.ts` → FAIL
- [ ] **Step 3: 实现改造**（加 stepper 与就地面板；`handleStructureChange` 后若 `pockets.length===0` 显示 `PocketPredictPanel`；`handleProteinChange` 后若 `structures.length===0` 显示 `StructurePredictForm`）
- [ ] **Step 4: 运行确认通过** — 上述测试 PASS；`npx vue-tsc -b` 无错
- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/design/components/PocketPicker.vue frontend/src/views/design/components/PocketPicker.spec.ts
git commit -m "feat(design): turn pocket picker into upstream relay with inline predict/select"
```

---

### Task 8: 设计任务页增强（继续设计流程 + 下一步）

**Files:**
- Modify: `frontend/src/views/design/Runs.vue`
- Modify: `frontend/src/locales/zh-CN/index.ts`、`en-US/index.ts`（`design.runs.continueFlow`、`design.runs.nextStep`）
- Test: `frontend/src/views/design/Runs.spec.ts`

**Interfaces:**
- 类别页签已由 `DESIGN_RUN_CATEGORIES` 驱动（Task 1 自动含 structure/pocket），无需改 tabs 循环。
- 「新建设计任务」按钮文案改 `design.runs.continueFlow`，`goSubmit` 跳 `/design`。
- 新增 `nextStepPath(record)`：`findDesignRunCategory` → structure→`/design/pocket?project_id=`、pocket→`/design/molecules?project_id=`、molecule→`/predict?project_id=`、其余→`null`（无则隐藏）。列 `actions` 追加「下一步」链接。

- [ ] **Step 1: 写失败测试**

```ts
// Runs.spec.ts
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
vi.mock('@/api/tasks', () => ({ getTaskList: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }) }))
vi.mock('@/api/projects', () => ({ listProjects: vi.fn().mockResolvedValue({ data: { items: [] } }) }))
const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
import Runs from './Runs.vue'
describe('Runs', () => {
  it('routes to /design from continue button', async () => {
    const w = mount(Runs)
    await new Promise(r => setTimeout(r))
    await w.find('[data-testid="design-runs-continue"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/design')
  })
})
```

- [ ] **Step 2: 运行确认失败** — `cd frontend && npm run test -- src/views/design/Runs.spec.ts` → FAIL
- [ ] **Step 3: 实现**（按钮加 `data-testid="design-runs-continue"`、改文案与 `goSubmit`；`nextStepPath` 纯函数放组件内或 `domain/design/runs.ts` 并测试）
- [ ] **Step 4: 运行确认通过** — 上述测试 PASS；`npx vue-tsc -b` 无错
- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/design/Runs.vue frontend/src/views/design/Runs.spec.ts frontend/src/locales
git commit -m "feat(design): design runs continue-flow and next-step affordances"
```

---

### Task 9: 整体验证与原型截图核对

**Files:** 无（验证 + 截图）
- Test: 全量 `npm run test`；构建 `npm run build`

- [ ] **Step 1: 全量单测** — `cd frontend && npm run test` → 全部 PASS（含既有用例无回归）
- [ ] **Step 2: 类型检查 + 构建** — `cd frontend && npm run build` → 成功（`vue-tsc -b` 无错）
- [ ] **Step 3: 真机截图核对** — 用 `frontend/_shots/shoot_mockups.mjs` 同类脚本，对 `/design`、`/design/molecules`（无已选口袋的项目态）、`/design/runs` 截图，和 `docs/superpowers/specs/assets/*.png` 比对结构一致
- [ ] **Step 4: 更新设计状态** — 在 `specs/2026-11-04-design-pipeline-ux-design.md` 顶部把「设计待评审」改为「已实现」
- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "chore(design): verify design pipeline UX end-to-end"
```

---

## Self-Review

- **Spec 覆盖**：§7 侧栏分组→Task4；§7.2/§8.1 总览→Task5；§8.2 接力条→Task3+Task7；§8.3 设计任务→Task1+Task8；§8.4 GuidedWorkflow→Task3+Task6；§9 数据源（getProjectStage/slug/共享逻辑）→Task1/2/3；§10 状态与降级→Task3/5/7 的空态与错误步；§11 分期（P1+P2）→Task1-8；§12 取舍→贯穿；§14 验收→Task9。
- **类型一致性**：`DesignStageKey`/`DesignStageState`/`buildDesignStages`/`firstMissingStage` 在 Task2 定义，Task5 消费；`useStructurePrediction`/`usePocketPrediction`/`useStructurePockets`/`waitForTaskCompletion` 在 Task3 定义，Task6/7 消费；`STRUCTURE_PREDICT_TOOL_SLUG`/`POCKET_PREDICT_TOOL_SLUG` 在 Task1 定义，Task1/8 消费。
- **Review Focus 落点**：空数据/无项目→Task5 空态步；有结构无选定口袋→Task7 Step3；预测失败/超时→Task3 `waitForTaskCompletion` + 组件 error 态；并发取新增→Task6/7「提交前 id 集合」逻辑；i18n→各任务 Step3 与 Task9 检查。
- **比例**：本计划以接口签名 + 测试断言为主，未逐行转写实现体（组件模板细节留给执行者按现有 `Predict/Pockets` 模式实现）。
