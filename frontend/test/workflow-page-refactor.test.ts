import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工作台页面拆分后的 composable 与组件应存在', () => {
  const expectedFiles = [
    'src/composables/useWorkflowCanvas.ts',
    'src/composables/useWorkflowPersistence.ts',
    'src/composables/useWorkflowExecution.ts',
    'src/stores/workflow-session-store.ts',
    'src/stores/workflow-templates.ts',
    'src/stores/workflow-runs.ts',
    'src/components/workflow/WorkflowTemplateToolbar.vue',
    'src/components/workflow/WorkflowRunInputPanel.vue',
    'src/components/workflow/WorkflowToolPalette.vue',
    'src/stores/workflow-session.ts'
  ]

  for (const file of expectedFiles) {
    assert.equal(existsSync(resolve(rootDir, file)), true, `missing ${file}`)
  }
})

test('工作台页面应通过 composable 和子组件组装，而不是继续堆叠实现细节', () => {
  const pageSource = readSource('src/views/workflow/index.vue')

  assert.equal(pageSource.includes('useWorkflowCanvas'), true)
  assert.equal(pageSource.includes('useWorkflowPersistence'), true)
  assert.equal(pageSource.includes('useWorkflowExecution'), true)
  assert.equal(pageSource.includes('WorkflowTemplateToolbar'), true)
  assert.equal(pageSource.includes('WorkflowRunInputPanel'), true)
  assert.equal(pageSource.includes('WorkflowToolPalette'), true)
})

test('工作台页面应收敛到 700 行以内', () => {
  const pageSource = readSource('src/views/workflow/index.vue')
  assert.equal(pageSource.split('\n').length < 700, true)
})

test('workflow store 应将 session helper 抽离到独立模块', () => {
  const storeSource = readSource('src/stores/workflow.ts')

  assert.equal(storeSource.includes("from './workflow-session'"), true)
  assert.equal(storeSource.includes("from './workflow-session-store'"), true)
  assert.equal(storeSource.includes("from './workflow-templates'"), true)
  assert.equal(storeSource.includes("from './workflow-runs'"), true)
})

test('workflow facade store 应保持跨域协调，不再实现模板和运行 API 细节', () => {
  const storeSource = readSource('src/stores/workflow.ts')

  assert.equal(storeSource.includes('getWorkflowTemplates('), false)
  assert.equal(storeSource.includes('getWorkflowRuns('), false)
  assert.equal(storeSource.includes('createWorkflowRun('), false)
  assert.equal(storeSource.includes('createWorkflowTemplate('), false)
})

test('工作流持久化 composable 不应使用 any[] 描述画布节点和边', () => {
  const source = readSource('src/composables/useWorkflowPersistence.ts')

  assert.equal(source.includes('WorkflowCanvasNode'), true)
  assert.equal(source.includes('WorkflowCanvasEdge'), true)
  assert.equal(source.includes('nodes: any[]'), false)
  assert.equal(source.includes('edges: any[]'), false)
})
