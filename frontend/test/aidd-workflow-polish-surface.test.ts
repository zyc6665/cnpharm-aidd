import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('步骤侧栏应展示步骤状态与阻断原因摘要', () => {
  const source = readSource('src/components/workflow/WorkflowStepSidebar.vue')

  assert.equal(source.includes('workflow.stepStatus.'), true)
  assert.equal(source.includes('workflow.stepHints.'), true)
})

test('运行面板应提供主动作区与下一步引导文案', () => {
  const source = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(source.includes('workflow.actions.'), true)
  assert.equal(source.includes('workflow.statusSummary.'), true)
  assert.equal(source.includes('workflow.invalidations.notice'), true)
})

test('产物面板应区分当前有效产物与已失效产物，并展示来源信息', () => {
  const source = readSource('src/components/workflow/WorkflowArtifactPanel.vue')

  assert.equal(source.includes('workflow.artifacts.currentGroup'), true)
  assert.equal(source.includes('workflow.artifacts.invalidatedGroup'), true)
  assert.equal(source.includes('workflow.artifacts.sourceStep'), true)
  assert.equal(source.includes('workflow.artifacts.sourceTool'), true)
  assert.equal(source.includes('workflow.artifacts.generatedAt'), true)
})

test('中英文 locale 应补齐 workflow 打磨相关文案', () => {
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')

  for (const source of [zhSource, enSource]) {
    assert.equal(source.includes('stepHints'), true)
    assert.equal(source.includes('actions'), true)
    assert.equal(source.includes('statusSummary'), true)
    assert.equal(source.includes('currentGroup'), true)
    assert.equal(source.includes('invalidatedGroup'), true)
  }
})
