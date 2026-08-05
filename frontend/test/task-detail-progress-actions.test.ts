import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('任务详情页应展示远端进度文本并按管理员权限显示删除动作', () => {
  const source = readSource('src/views/tasks/Detail.vue')

  assert.equal(source.includes('useUserStore'), true)
  assert.equal(source.includes("from '@/domain/tasks'"), true)
  assert.equal(source.includes('canDeleteTask'), true)
  assert.equal(source.includes('canDeleteTaskForActor'), true)
  assert.equal(source.includes('resolveTaskWebSocketProgressUpdate'), true)
  assert.equal(source.includes('resolveTaskWebSocketLog'), true)
  assert.equal(source.includes('v-if="canDeleteTask"'), true)
  assert.equal(source.includes('task.progress_message'), true)
})
