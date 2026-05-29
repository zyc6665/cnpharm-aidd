import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { normalizeTaskSummary } from '../src/utils/task-normalization.ts'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

test('normalizeTaskSummary 应将任务列表接口返回的 tool_name 映射为可显示的 tool.name', () => {
  const normalized = normalizeTaskSummary({
    id: 'task-1',
    tool_id: 'tool-1',
    tool_name: 'GCDM Pocket Generation',
    tool_slug: 'gcdm-pocket-generation',
    status: 'success',
    progress: 1,
    created_at: '2026-05-27T09:00:00Z'
  })

  assert.equal(normalized.tool?.name, 'GCDM Pocket Generation')
  assert.equal(normalized.tool?.slug, 'gcdm-pocket-generation')
  assert.equal(normalized.tool?.id, 'tool-1')
})

test('任务 store 应对列表结果执行工具摘要归一化', () => {
  const storeSource = readFileSync(resolve(rootDir, 'src/stores/tasks.ts'), 'utf8')

  assert.equal(storeSource.includes("import { normalizeTaskSummaries, normalizeTaskSummary } from '@/utils/task-normalization'"), true)
  assert.equal(storeSource.includes('tasks.value = normalizeTaskSummaries(res.data.items)'), true)
})
