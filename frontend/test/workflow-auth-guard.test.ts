import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工作台恢复持久化模板和运行记录前应确认已登录', () => {
  const source = readSource('src/views/workflow/index.vue')

  assert.equal(source.includes('userStore.authReady'), true)
  assert.equal(
    source.includes(
      'if (!userStore.authReady || !userStore.isLoggedIn || !workflowStore.activeWorkflowTemplateId)'
    ),
    true
  )
  assert.equal(
    source.includes(
      'if (!userStore.authReady || !userStore.isLoggedIn || !workflowStore.activeWorkflowRunId)'
    ),
    true
  )
})
