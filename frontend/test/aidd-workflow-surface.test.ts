import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

function readSourceIfExists(relativePath: string): string | null {
  const absolutePath = resolve(rootDir, relativePath)

  if (!existsSync(absolutePath)) {
    return null
  }

  return readFileSync(absolutePath, 'utf8')
}

function hasWorkflowRoute(source: string): boolean {
  return /path\s*:\s*['"`]\/workflow['"`]/.test(source)
}

function hasWorkflowNavigationEntry(source: string): boolean {
  return (
    /router\.push\(\s*['"]\/workflow['"]\s*\)/.test(source) ||
    /router\.(push|replace)\(\s*\{[\s\S]*?name\s*:\s*['"]Workflow['"][\s\S]*?\}\s*\)/.test(source) ||
    /router\.push\(\s*\{[\s\S]*?path\s*:\s*['"]\/workflow['"][\s\S]*?\}\s*\)/.test(source) ||
    /to\s*=\s*['"]\/workflow['"]/.test(source) ||
    /:to\s*=\s*["']\{[\s\S]*?path\s*:\s*['"]\/workflow['"][\s\S]*?\}["']/.test(source) ||
    /:to\s*=\s*["']\{[\s\S]*?name\s*:\s*['"]Workflow['"][\s\S]*?\}["']/.test(source)
  )
}

test('前端路由中应新增流程工作台页面', () => {
  const routerSource = readSource('src/router/index.ts')

  assert.equal(hasWorkflowRoute(routerSource), true)
})

test('首页或工具列表页应提供流程工作台入口', () => {
  const candidateSources = [
    readSourceIfExists('src/views/home/index.vue'),
    readSourceIfExists('src/views/tools/List.vue')
  ].filter((source): source is string => source !== null)

  const hasWorkflowEntry = candidateSources.some(source => hasWorkflowNavigationEntry(source))

  assert.equal(hasWorkflowEntry, true)
})

test('流程工作台 store 模块文件应存在', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/stores/workflow.ts')), true)
})

test('store 入口应导出 useWorkflowStore', () => {
  const source = readSource('src/stores/index.ts')

  assert.equal(source.includes("export { useWorkflowStore } from './workflow'"), true)
})

test('工具工作台 store 应启用持久化并声明核心状态与动作', () => {
  const source = readSource('src/stores/workflow.ts')

  assert.equal(source.includes('persist:'), true)
  assert.equal(source.includes('sessionId'), true)
  assert.equal(source.includes('activeGroupId'), true)
  assert.equal(source.includes('selectedToolByGroup'), true)
  assert.equal(source.includes('toolFormDrafts'), true)
  assert.equal(source.includes('taskByTool'), true)
  assert.equal(source.includes('resetSession'), true)
  assert.equal(source.includes('selectTool'), true)
  assert.equal(source.includes('recordTask'), true)
  assert.equal(source.includes('setToolFormDraft'), true)
})

test('流程步骤 catalog 模块文件应存在', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/workflow/aidd-catalog.ts')), true)
})

test('流程步骤 catalog 应定义固定五步顺序', () => {
  const catalogSource = readSource('src/workflow/aidd-catalog.ts')

  assert.equal(catalogSource.includes('pocketExploration'), true)
  assert.equal(catalogSource.includes('moleculeGenerationOrVirtualScreening'), true)
  assert.equal(catalogSource.includes('molecularDockingAndAffinityPrediction'), true)
  assert.equal(catalogSource.includes('propertyPrediction'), true)
  assert.equal(catalogSource.includes('leadOptimization'), true)
  assert.equal(catalogSource.includes('toolSlugs'), true)
})

test('流程产物类型模块文件应存在并导出核心骨架', () => {
  const source = readSource('src/workflow/artifact-types.ts')

  assert.equal(source.includes('WorkflowStepKey'), true)
  assert.equal(source.includes('WorkflowStepStatus'), true)
  assert.equal(source.includes('WorkflowArtifactSemanticType'), true)
  assert.equal(source.includes('WorkflowSession'), true)
  assert.equal(source.includes('WorkflowStepRecord'), true)
})

test('流程工具绑定模块文件应存在并导出绑定配置', () => {
  const source = readSource('src/workflow/tool-bindings.ts')

  assert.equal(source.includes('WORKFLOW_TOOL_BINDINGS'), true)
  assert.equal(source.includes('acceptedInputTypes'), true)
  assert.equal(source.includes('fieldBindings'), true)
  assert.equal(source.includes('outputExtractors'), true)
})

test('公共模型类型中应提供轻量工具摘要类型', () => {
  const source = readSource('src/types/models.d.ts')

  assert.equal(source.includes('export interface ToolOptionSummary'), true)
  assert.equal(source.includes("status: Tool['status']"), true)
})

test('流程工作台页面文件应存在', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/views/workflow/index.vue')), true)
})

test('流程工作台应拆出三栏子组件文件', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/workflow/WorkflowStepSidebar.vue')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/components/workflow/WorkflowRunPanel.vue')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/components/workflow/WorkflowArtifactPanel.vue')), true)
})

test('流程工作台页面应组合侧栏、运行面板和产物面板组件', () => {
  const source = readSource('src/views/workflow/index.vue')

  assert.equal(source.includes('WorkflowStepSidebar'), true)
  assert.equal(source.includes('WorkflowRunPanel'), true)
  assert.equal(source.includes('WorkflowArtifactPanel'), true)
})

test('流程运行面板应复用 schema 扁平化与任务提交载荷构建工具', () => {
  const source = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(source.includes('flattenToolInputSchema'), true)
  assert.equal(source.includes('buildTaskSubmissionPayload'), true)
})

test('流程运行面板应提供产物选择、提交、重置和工具跳转操作', () => {
  const source = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(source.includes('ArtifactFilePicker'), true)
  assert.equal(source.includes('submitWorkflowForm'), true)
  assert.equal(source.includes('workflow.currentTool.runAction'), true)
  assert.equal(source.includes("t('common.reset')"), true)
  assert.equal(source.includes('openToolDetail'), true)
  assert.equal(source.includes('openTaskDetail'), true)
})
