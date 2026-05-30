import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工作台产物条目应分离内容列和操作列，避免查看详情按钮与信息重叠', () => {
  const source = readSource('src/components/workflow/WorkflowArtifactPanel.vue')

  assert.equal(source.includes('artifact-action'), true)
  assert.equal(source.includes('artifact-action-button'), true)
  assert.equal(source.includes('grid-template-columns: minmax(0, 1fr) auto'), true)
  assert.equal(source.includes('overflow-wrap: anywhere'), true)
  assert.equal(source.includes('align-self: start'), true)
})

test('工作台页面应提供更稳的三栏布局和窄屏顺序', () => {
  const pageSource = readSource('src/views/workflow/index.vue')
  const runPanelSource = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(pageSource.includes('workflow-shell'), true)
  assert.equal(pageSource.includes('class="workflow-shell"'), true)
  assert.equal(pageSource.includes('container workflow-shell'), false)
  assert.equal(pageSource.includes('max-width: none'), true)
  assert.equal(pageSource.includes('width: min(100%, calc(100vw - 32px))'), true)
  assert.equal(pageSource.includes('grid-template-columns: minmax(260px, 320px) minmax(0, 1fr) minmax(320px, 380px)'), true)
  assert.equal(pageSource.includes('align-items: start'), true)
  assert.equal(pageSource.includes('order:'), true)
  assert.equal(runPanelSource.includes('form-action-buttons'), true)
  assert.equal(runPanelSource.includes(':deep(.ant-space-item)'), true)
})

test('工作台工具卡片应在宽屏使用更舒展的响应式网格', () => {
  const runPanelSource = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(runPanelSource.includes('grid-template-columns: repeat(auto-fit, minmax(280px, 1fr))'), true)
  assert.equal(runPanelSource.includes('gap: @spacing-lg'), true)
  assert.equal(runPanelSource.includes('min-height: 132px'), true)
  assert.equal(runPanelSource.includes('padding: @spacing-lg'), true)
  assert.equal(runPanelSource.includes('align-content: start'), true)
})

test('工作台左右栏应支持桌面吸顶和长列表内部滚动', () => {
  const sidebarSource = readSource('src/components/workflow/WorkflowStepSidebar.vue')
  const artifactPanelSource = readSource('src/components/workflow/WorkflowArtifactPanel.vue')

  assert.equal(sidebarSource.includes('position: sticky'), true)
  assert.equal(artifactPanelSource.includes('position: sticky'), true)
  assert.equal(sidebarSource.includes('max-height: calc(100vh'), true)
  assert.equal(artifactPanelSource.includes('max-height: calc(100vh'), true)
  assert.equal(sidebarSource.includes('overflow-y: auto'), true)
  assert.equal(artifactPanelSource.includes('overflow-y: auto'), true)
  assert.equal(sidebarSource.includes('&:focus-visible'), true)
})

test('工作台产物应按任务归类并限制每个任务的预览数量', () => {
  const artifactPanelSource = readSource('src/components/workflow/WorkflowArtifactPanel.vue')
  const zhLocaleSource = readSource('src/locales/zh-CN/index.ts')
  const enLocaleSource = readSource('src/locales/en-US/index.ts')

  assert.equal(artifactPanelSource.includes('groupArtifactsByTask'), true)
  assert.equal(artifactPanelSource.includes('currentGroupTaskGroups'), true)
  assert.equal(artifactPanelSource.includes('recentTaskGroups'), true)
  assert.equal(artifactPanelSource.includes('ARTIFACT_TASK_PREVIEW_LIMIT'), true)
  assert.equal(artifactPanelSource.includes('visibleArtifacts'), true)
  assert.equal(artifactPanelSource.includes('artifact-task-card'), true)
  assert.equal(artifactPanelSource.includes('artifact-task-count'), true)
  assert.equal(artifactPanelSource.includes('workflow.artifacts.taskCount'), true)
  assert.equal(artifactPanelSource.includes('workflow.artifacts.moreArtifacts'), true)
  assert.equal(zhLocaleSource.includes('taskCount'), true)
  assert.equal(zhLocaleSource.includes('moreArtifacts'), true)
  assert.equal(enLocaleSource.includes('taskCount'), true)
  assert.equal(enLocaleSource.includes('moreArtifacts'), true)
})
