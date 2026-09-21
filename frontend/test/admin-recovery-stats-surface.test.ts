import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('管理员统计页应展示 Remote Recovery 告警任务数', () => {
  const modelSource = readSource('src/types/models.d.ts')
  const tasksSource = readSource('src/views/admin/Tasks.vue')
  const systemSource = readSource('src/views/admin/System.vue')

  assert.equal(modelSource.includes('remote_recovery_alerted_tasks: number'), true)
  assert.equal(tasksSource.includes('systemStats?.remote_recovery_alerted_tasks'), true)
  assert.equal(systemSource.includes('systemStats?.remote_recovery_alerted_tasks'), true)
})
