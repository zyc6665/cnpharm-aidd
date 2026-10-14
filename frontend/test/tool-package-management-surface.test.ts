import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('后台应提供 Tool Package 管理页入口', () => {
  const routerSource = readSource('src/router/index.ts')
  const adminToolsSource = readSource('src/views/admin/Tools.vue')
  const pagePath = resolve(rootDir, 'src/views/admin/ToolPackages.vue')

  assert.equal(existsSync(pagePath), true)
  assert.equal(routerSource.includes("path: 'tool-packages'"), true)
  assert.equal(routerSource.includes("name: 'AdminToolPackages'"), true)
  assert.equal(routerSource.includes("import('@/views/admin/ToolPackages.vue')"), true)
  assert.equal(adminToolsSource.includes('openToolPackages'), true)
  assert.equal(adminToolsSource.includes("router.push('/admin/tool-packages')"), true)
})

test('Tool Package 前端 API 和类型应覆盖列表、创建、读取与发布', () => {
  const apiPath = resolve(rootDir, 'src/api/tool-packages.ts')
  const typePath = resolve(rootDir, 'src/types/tool-packages.ts')
  assert.equal(existsSync(apiPath), true)
  assert.equal(existsSync(typePath), true)

  const apiSource = readSource('src/api/tool-packages.ts')
  const typeSource = readSource('src/types/tool-packages.ts')
  assert.equal(typeSource.includes('ToolPackage'), true)
  assert.equal(typeSource.includes('ToolPackageCreateInput'), true)
  assert.equal(apiSource.includes('listToolPackages'), true)
  assert.equal(apiSource.includes('createToolPackage'), true)
  assert.equal(apiSource.includes('getToolPackage'), true)
  assert.equal(apiSource.includes('publishToolPackage'), true)
  assert.equal(apiSource.includes('/tool-packages'), true)
})

test('Tool Package 管理页应把标准 Artifact 与模型侧 adapter 作为默认部署路径', () => {
  const source = readSource('src/views/admin/ToolPackages.vue')

  for (const marker of [
    'listToolPackages',
    'createToolPackage',
    'publishToolPackage',
    'manifestText',
    'signatureText',
    'Tool Package v2',
    '标准 Artifact',
    '模型侧 adapter',
    '旧语义映射'
  ]) {
    assert.equal(source.includes(marker), true, `missing marker ${marker}`)
  }
})
