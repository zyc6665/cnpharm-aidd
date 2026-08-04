import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('任务类型定义应暴露 name 字段和可选创建参数', () => {
  const source = readSource('src/types/models.d.ts')

  assert.equal(source.includes('name?: string'), true)
  assert.equal(source.includes('name?: string\n  tool_id: string') || source.includes("name?: string\r\n  tool_id: string"), true)
})

test('普通工具详情页应提供任务名称输入并在创建任务时传递 name', () => {
  const source = readSource('src/views/tools/Detail.vue')

  assert.equal(source.includes("t('tasks.name')"), true)
  assert.equal(source.includes("t('tasks.namePlaceholder')"), true)
  assert.equal(source.includes('const taskName = ref('), true)
  assert.equal(source.includes('name: taskName.value.trim() || undefined'), true)
})

test('工作台已下线单任务运行面板，不再在面板内创建任务名称', () => {
  const source = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(source.includes('workflow-run-panel'), true)
  assert.equal(source.includes("t('tasks.name')"), false)
  assert.equal(source.includes('const taskName = ref('), false)
  assert.equal(source.includes('name: taskName.value.trim() || undefined'), false)
})

test('任务列表和详情页应优先展示任务名而不是只展示工具名或任务 ID', () => {
  const listSource = readSource('src/views/tasks/List.vue')
  const detailSource = readSource('src/views/tasks/Detail.vue')

  assert.equal(listSource.includes("task.name || task.tool?.name || t('tasks.unknownTool')"), true)
  assert.equal(detailSource.includes("task.value?.name || task.value?.tool?.name || t('tasks.taskDetail')"), true)
  assert.equal(detailSource.includes("task?.name || task?.tool?.name || t('tasks.taskDetail')"), true)
})

test('工作流任务引用和归一化逻辑应保留任务名', () => {
  const artifactSource = readSource('src/workflow/artifact-types.ts')
  const stateSource = readSource('src/workflow/task-state.ts')
  const normalizationSource = readSource('src/utils/task-normalization.ts')

  assert.equal(artifactSource.includes("| 'name'"), true)
  assert.equal(stateSource.includes('name: task.name,'), true)
  assert.equal(normalizationSource.includes('name: task.name,'), true)
})

test('中英文 locale 应补齐任务名称输入文案', () => {
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')

  assert.equal(zhSource.includes("name: '任务名称'"), true)
  assert.equal(zhSource.includes("namePlaceholder: '可选，留空将自动生成'"), true)
  assert.equal(enSource.includes("name: 'Task Name'"), true)
  assert.equal(enSource.includes("namePlaceholder: 'Optional, leave blank to auto-generate'"), true)
})
