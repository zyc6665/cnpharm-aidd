import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工作台恢复持久化运行记录前应确认已登录', () => {
  const pageSource = readSource('src/views/workflow/index.vue')
  const persistenceSource = readSource('src/composables/useWorkflowPersistence.ts')

  assert.equal(pageSource.includes('userStore.authReady'), true)
  assert.equal(
    persistenceSource.includes(
      'if (!userStore.authReady || !userStore.isLoggedIn || !workflowStore.activeWorkflowRunId)'
    ),
    true
  )
  assert.equal(persistenceSource.includes('activeWorkflowCanvasPresetId'), false)
})
