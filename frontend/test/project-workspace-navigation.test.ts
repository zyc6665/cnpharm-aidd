import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('项目工作台应有统一导航组件和项目内 workflow 路由', () => {
  assert.equal(
    existsSync(resolve(rootDir, 'src/components/projects/ProjectWorkspaceNav.vue')),
    true
  )

  const router = readSource('src/router/index.ts')
  const overview = readSource('src/views/projects/Overview.vue')
  const settings = readSource('src/views/projects/Settings.vue')
  const lineage = readSource('src/views/projects/ArtifactLineage.vue')
  const taskList = readSource('src/views/tasks/List.vue')
  const workflow = readSource('src/views/workflow/index.vue')

  assert.equal(router.includes("path: '/projects/:projectId/workflow'"), true)
  assert.equal(router.includes("name: 'ProjectWorkflow'"), true)
  assert.equal(overview.includes('ProjectWorkspaceNav'), true)
  assert.equal(settings.includes('ProjectWorkspaceNav'), true)
  assert.equal(lineage.includes('ProjectWorkspaceNav'), true)
  assert.equal(taskList.includes('ProjectWorkspaceNav'), true)
  assert.equal(workflow.includes('route.params?.projectId'), true)
  assert.equal(overview.includes("`/projects/${projectId}/workflow`"), true)
})

test('项目工作台导航应覆盖总览、研究、白板、Workflow、任务、谱系和设置', () => {
  const nav = readSource('src/components/projects/ProjectWorkspaceNav.vue')

  assert.equal(nav.includes('项目总览'), true)
  assert.equal(nav.includes('智能体研究'), true)
  assert.equal(nav.includes('科研白板'), true)
  assert.equal(nav.includes('Workflow'), true)
  assert.equal(nav.includes('任务中心'), true)
  assert.equal(nav.includes('Artifact 谱系'), true)
  assert.equal(nav.includes('项目设置'), true)
  assert.equal(nav.includes('/tasks?project_id='), true)
})
