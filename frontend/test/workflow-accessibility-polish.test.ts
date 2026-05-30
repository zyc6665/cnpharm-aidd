import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工作台工具选项应使用原生按钮承载选择交互', () => {
  const source = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(source.includes('<button'), true)
  assert.equal(source.includes('type="button"'), true)
  assert.equal(source.includes('class="tool-option-card"'), true)
  assert.equal(source.includes('&:focus-visible'), true)
})

test('工作台浅色任务摘要应使用浅色主题文字变量', () => {
  const runPanelSource = readSource('src/components/workflow/WorkflowRunPanel.vue')
  const artifactPanelSource = readSource('src/components/workflow/WorkflowArtifactPanel.vue')

  assert.equal(runPanelSource.includes('color: @text-color-light-primary'), true)
  assert.equal(artifactPanelSource.includes('color: @text-color-light-primary'), true)
  assert.equal(runPanelSource.includes('color: @text-color-primary'), false)
  assert.equal(artifactPanelSource.includes('color: @text-color-primary'), false)
})
