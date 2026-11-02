import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const ROOT = resolve(__dirname, '..')
const component = readFileSync(resolve(ROOT, 'src/components/tasks/TaskOutputSummary.vue'), 'utf-8')

test('输出摘要先给关键指标与产物清单，原始 JSON 收进折叠', () => {
  assert.ok(component.includes('buildOutputOverview'))
  assert.ok(component.includes('data-testid="task-output-metrics"'))
  assert.ok(component.includes('data-testid="task-output-artifacts"'))
  assert.ok(component.includes('tasks.outputRawJson'), '排障时仍要能看到原始 JSON')
  assert.ok(
    component.indexOf('task-output-metrics') < component.indexOf('task-output-raw'),
    '指标必须在原始 JSON 之前，先给结论再给证据',
  )
})

test('产物类型用中文名而不是类型码', () => {
  assert.ok(component.includes('artifactTypeLabelKey'), '类型码应转成中文名')
  assert.equal(component.includes("dataIndex: 'type'"), false, '不应直接展示 type 原值')
})
