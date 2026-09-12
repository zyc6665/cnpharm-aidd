import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('task center supports project-scoped task filtering from project overview', () => {
  const apiSource = readSource('src/api/tasks.ts')
  const storeSource = readSource('src/stores/tasks.ts')
  const taskPageSource = readSource('src/views/tasks/List.vue')
  const projectOverviewSource = readSource('src/views/projects/Overview.vue')
  const projectNavigationSource = readSource('src/domain/projects/navigation.ts')

  assert.equal(apiSource.includes('project_id?: string'), true)
  assert.equal(storeSource.includes("'tool_id' | 'keyword' | 'project_id'"), true)
  assert.equal(taskPageSource.includes("from '@/domain/tasks'"), true)
  assert.equal(taskPageSource.includes('filterTasksForTab(tasks.value, currentTab.value)'), true)
  assert.equal(taskPageSource.includes('filterTasksByKeyword(filteredByTab, searchKeyword.value)'), true)
  assert.equal(taskPageSource.includes('route.query.project_id'), true)
  assert.equal(taskPageSource.includes('projectId: projectId.value'), true)
  assert.equal(taskPageSource.includes('useAgentsStore'), false)
  assert.equal(taskPageSource.includes('AgentRunTaskCard'), false)
  assert.equal(taskPageSource.includes('agent-task-grouping'), false)
  assert.equal(projectOverviewSource.includes('buildProjectTaskPath(projectId.value)'), true)
  assert.equal(projectNavigationSource.includes('/tasks?project_id='), true)
})
