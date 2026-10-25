import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('管理员任务页不再提供 Remote Recovery 告警筛选', () => {
  // 后端已随步骤 4 移除 remote_recovery 字段与过滤参数，前端筛选器一并退场。
  const source = readSource('src/views/admin/Tasks.vue')

  assert.equal(source.includes('remote_recovery_alerted'), false)
  assert.equal(source.includes('tasks.remoteRecovery'), false)
})
