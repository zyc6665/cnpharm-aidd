import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('管理页面只应由路由级后台容器负责渲染布局', () => {
  const appSource = readSource('src/App.vue')
  const routerSource = readSource('src/router/index.ts')

  assert.equal(routerSource.includes("component: () => import('@/views/admin/index.vue')"), true)
  assert.equal(appSource.includes("import AdminLayout from '@/components/layout/AdminLayout.vue'"), false)
  assert.equal(appSource.includes('return AdminLayout'), false)
})
