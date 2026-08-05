import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('管理员系统页应展示健康检查服务与数据库 schema 状态', () => {
  const systemApi = readSource('src/api/system.ts')
  const page = readSource('src/views/admin/System.vue')
  const domain = readSource('src/domain/admin/system-health.ts')
  const types = readSource('src/types/models.d.ts')

  assert.equal(systemApi.includes('getSystemHealth'), true)
  assert.equal(types.includes('export interface SystemHealth'), true)
  assert.equal(page.includes('systemHealth'), true)
  assert.equal(page.includes('healthServices'), true)
  assert.equal(page.includes("from '@/domain/admin'"), true)
  assert.equal(page.includes('healthStatusColor'), true)
  assert.equal(domain.includes('database_schema'), true)
  assert.equal(domain.includes('tool_package_runtime'), true)
})
