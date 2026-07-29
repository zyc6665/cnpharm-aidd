import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工作台左栏应展示分组摘要与推荐工具数量', () => {
  const source = readSource('src/components/workflow/WorkflowStepSidebar.vue')

  assert.equal(source.includes('workflow.columns.groups'), true)
  assert.equal(source.includes('workflow.groups.toolCount'), true)
  assert.equal(source.includes('workflow.groups.recommendedCount'), true)
  assert.equal(source.includes('getRecommendedCount'), true)
})

test('节点运行面板应提供工具摘要和主动作区', () => {
  const source = readSource('src/components/workflow/WorkflowNodeRunPanel.vue')

  assert.equal(source.includes('run-tool-summary'), true)
  assert.equal(source.includes('node-run-actions'), true)
  assert.equal(source.includes('submitWorkflowForm'), true)
  assert.equal(source.includes('resetForm'), true)
})

test('产物面板应区分当前分组产物与最近产物，并展示来源信息', () => {
  const source = readSource('src/components/workflow/WorkflowArtifactPanel.vue')

  assert.equal(source.includes('workflow.artifacts.currentGroup'), true)
  assert.equal(source.includes('workflow.artifacts.recentGroup'), true)
  assert.equal(source.includes('workflow.artifacts.sourceTool'), true)
  assert.equal(source.includes('workflow.artifacts.generatedAt'), true)
})

test('中英文 locale 应补齐当前工作台打磨相关文案', () => {
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')

  for (const source of [zhSource, enSource]) {
    assert.equal(source.includes('groupsHint'), true)
    assert.equal(source.includes('toolsHint'), true)
    assert.equal(source.includes('artifactsHint'), true)
    assert.equal(source.includes('currentGroup'), true)
    assert.equal(source.includes('recentGroup'), true)
  }
})
