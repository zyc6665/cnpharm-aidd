import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('管理员统计页不再展示 Remote Recovery 告警任务数', () => {
  // 交付线移除了外部 API 工具与远程工具恢复机制，Admin 侧不应再暴露对应统计位。
  const modelSource = readSource('src/types/models.d.ts')
  const tasksSource = readSource('src/views/admin/Tasks.vue')
  const systemSource = readSource('src/views/admin/System.vue')

  assert.equal(modelSource.includes('remote_recovery_alerted_tasks'), false)
  assert.equal(tasksSource.includes('remote_recovery_alerted_tasks'), false)
  assert.equal(systemSource.includes('remote_recovery_alerted_tasks'), false)
})
