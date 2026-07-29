import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('后台列表页应复用统一筛选栏组件', () => {
  const adminListPages = [
    'src/views/admin/Tools.vue',
    'src/views/admin/Users.vue',
    'src/views/admin/Tasks.vue'
  ]

  for (const relativePath of adminListPages) {
    const source = readSource(relativePath)

    assert.equal(source.includes('AppFilterBar'), true, relativePath)
    assert.equal(source.includes('class="filter-card"'), false, relativePath)
    assert.equal(source.includes('.filter-card'), false, relativePath)
  }
})

test('统一筛选栏应兼容 Ant Design 表单筛选控件', () => {
  const source = readSource('src/components/common/AppFilterBar.vue')

  assert.equal(source.includes(':deep(.ant-form)'), true)
  assert.equal(source.includes(':deep(.ant-form-item)'), true)
})
