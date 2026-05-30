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
  assert.equal(pageSource.includes('grid-template-columns: minmax(240px, 280px) minmax(420px, 1fr) minmax(300px, 340px)'), true)
  assert.equal(pageSource.includes('align-items: start'), true)
  assert.equal(pageSource.includes('order:'), true)
  assert.equal(runPanelSource.includes('form-action-buttons'), true)
  assert.equal(runPanelSource.includes(':deep(.ant-space-item)'), true)
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
