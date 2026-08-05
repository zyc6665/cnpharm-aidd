import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('任务列表应按用户和项目角色隐藏不可用操作，并展示项目上下文', () => {
  const source = readSource('src/views/tasks/List.vue')
  const navigationSource = readSource('src/domain/tasks/navigation.ts')

  assert.equal(source.includes('useUserStore'), true)
  assert.equal(source.includes("from '@/domain/tasks'"), true)
  assert.equal(source.includes('taskActor'), true)
  assert.equal(source.includes('projectMembershipRole'), true)
  assert.equal(source.includes('canCancelTaskForActor(task, taskActor.value)'), true)
  assert.equal(source.includes('canRetryTaskForActor(task, taskActor.value)'), true)
  assert.equal(source.includes('canDeleteTaskForActor(task, taskActor.value)'), true)
  assert.equal(source.includes('canDeleteTask(task)'), true)
  assert.equal(source.includes('task.progress_message'), true)
  assert.equal(source.includes('getTaskProjectContextLabel(task'), true)
  assert.equal(source.includes('getTaskArtifactLineagePath'), true)
  assert.equal(navigationSource.includes('/lineage'), true)
})
