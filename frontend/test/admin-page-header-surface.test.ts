import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('后台管理核心页面应复用统一页面标题组件', () => {
  const adminPages = [
    'src/views/admin/Tools.vue',
    'src/views/admin/Users.vue',
    'src/views/admin/Tasks.vue',
    'src/views/admin/ToolCategories.vue',
    'src/views/admin/WorkbenchGroups.vue',
    'src/views/admin/System.vue'
  ]

  for (const relativePath of adminPages) {
    const source = readSource(relativePath)

    assert.equal(source.includes('AppPageHeader'), true, relativePath)
    assert.equal(source.includes('class="page-header"'), false, relativePath)
    assert.equal(source.includes('.page-header'), false, relativePath)
  }
})
