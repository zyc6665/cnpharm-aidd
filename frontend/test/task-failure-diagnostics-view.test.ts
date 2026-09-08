import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('任务详情页应接入失败诊断摘要', () => {
  const source = readSource('src/views/tasks/Detail.vue')

  assert.equal(source.includes('buildTaskFailureDiagnostics'), true)
  assert.equal(source.includes('task-failure-diagnostics'), true)
  assert.equal(source.includes('task-stderr'), true)
  assert.equal(source.includes('task-stdout'), true)
  assert.equal(source.includes('tasks.standardArtifactsMissing'), true)
})
