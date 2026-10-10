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
  const nav = readSource('src/components/projects/ProjectWorkspaceNav.vue')

  assert.equal(router.includes("path: '/projects/:projectId/workflow'"), true)
  assert.equal(router.includes("name: 'ProjectWorkflow'"), true)
  assert.equal(nav.includes("from '@/domain/projects'"), true)
  assert.equal(overview.includes("from '@/domain/projects'"), true)
  assert.equal(overview.includes('ProjectWorkspaceNav'), true)
  assert.equal(settings.includes('ProjectWorkspaceNav'), true)
  assert.equal(lineage.includes('ProjectWorkspaceNav'), true)
  assert.equal(taskList.includes('ProjectWorkspaceNav'), true)
  assert.equal(workflow.includes('route.params?.projectId'), true)
  assert.equal(overview.includes('buildProjectWorkflowPath(projectId.value)'), true)
})

test('项目工作台导航应覆盖当前项目内主要入口', () => {
  const navDomain = readSource('src/domain/projects/navigation.ts')

  assert.equal(navDomain.includes('项目总览'), true)
  assert.equal(navDomain.includes('智能体研究'), true)
  assert.equal(navDomain.includes('Workflow'), true)
  assert.equal(navDomain.includes('任务中心'), true)
  assert.equal(navDomain.includes('Artifact 谱系'), true)
  assert.equal(navDomain.includes('项目设置'), true)
  assert.equal(navDomain.includes('/tasks?project_id='), true)
})
