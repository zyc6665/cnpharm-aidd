import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('管理员任务页应支持按 Remote Recovery 告警筛选', () => {
  const source = readSource('src/views/admin/Tasks.vue')

  assert.equal(source.includes('remote_recovery_alerted'), true)
  assert.equal(source.includes('filters.remote_recovery_alerted = undefined'), true)
  assert.equal(source.includes(':value="true"'), true)
})
