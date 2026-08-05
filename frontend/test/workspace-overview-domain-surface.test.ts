import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工作台首页应通过 domain 模块生成概览展示数据', () => {
  const page = readSource('src/views/workspace/index.vue')
  const domain = readSource('src/domain/workspace/overview.ts')

  assert.equal(page.includes("from '@/domain/workspace'"), true)
  assert.equal(page.includes('getRecentWorkspaceProjects(projects.value)'), true)
  assert.equal(page.includes('buildRecentWorkspaceArtifactRows'), true)
  assert.equal(page.includes("import dayjs from 'dayjs'"), false)
  assert.equal(domain.includes('hasWorkspaceSchemaMigrationHealthIssue'), true)
  assert.equal(domain.includes('database_schema'), true)
})
