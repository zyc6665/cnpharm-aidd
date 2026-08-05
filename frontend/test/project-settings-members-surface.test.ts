import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('项目设置页应成为成员管理入口', () => {
  const routerSource = readSource('src/router/index.ts')
  const overviewSource = readSource('src/views/projects/Overview.vue')
  const pagePath = resolve(rootDir, 'src/views/projects/Settings.vue')

  assert.equal(existsSync(pagePath), true)
  assert.equal(routerSource.includes("path: '/projects/:projectId/settings'"), true)
  assert.equal(routerSource.includes("name: 'ProjectSettings'"), true)
  assert.equal(overviewSource.includes("`/projects/${projectId}/settings`"), true)
  assert.equal(overviewSource.includes('项目设置'), true)
})

test('项目成员 API 与类型应覆盖列表、添加、改角色和移除', () => {
  const apiSource = readSource('src/api/projects.ts')
  const typeSource = readSource('src/types/projects.ts')

  assert.equal(typeSource.includes('ProjectMember'), true)
  assert.equal(typeSource.includes('ProjectMemberCreateInput'), true)
  assert.equal(typeSource.includes('ProjectMemberUpdateInput'), true)
  assert.equal(apiSource.includes('listProjectMembers'), true)
  assert.equal(apiSource.includes('addProjectMember'), true)
  assert.equal(apiSource.includes('updateProjectMember'), true)
  assert.equal(apiSource.includes('removeProjectMember'), true)
  assert.equal(apiSource.includes("`/projects/${projectId}/members`"), true)
})

test('项目设置页应调用成员接口并按 owner 权限展示管理操作', () => {
  const source = readSource('src/views/projects/Settings.vue')

  assert.equal(source.includes('listProjectMembers'), true)
  assert.equal(source.includes('addProjectMember'), true)
  assert.equal(source.includes('updateProjectMember'), true)
  assert.equal(source.includes('removeProjectMember'), true)
  assert.equal(source.includes('canManageMembers'), true)
  assert.equal(source.includes("membership.role === 'owner'"), true)
})
