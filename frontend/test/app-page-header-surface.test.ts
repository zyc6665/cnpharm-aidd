import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('应提供统一的页面标题组件承载标题、副标题和操作区', () => {
  const componentPath = resolve(rootDir, 'src/components/common/AppPageHeader.vue')

  assert.equal(existsSync(componentPath), true)

  const source = readFileSync(componentPath, 'utf8')
  assert.equal(source.includes('app-page-header'), true)
  assert.equal(source.includes("defineProps<{"), true)
  assert.equal(source.includes('title: string'), true)
  assert.equal(source.includes('subtitle?: string'), true)
  assert.equal(source.includes("align?: 'start' | 'center'"), true)
  assert.equal(source.includes('app-page-header--center'), true)
  assert.equal(source.includes('<slot name="actions"'), true)
})

test('核心工作页应复用 AppPageHeader，避免重复页面头样式', () => {
  for (const relativePath of [
    'src/views/workflow/index.vue',
    'src/views/tools/List.vue',
    'src/views/tasks/List.vue'
  ]) {
    const source = readSource(relativePath)

    assert.equal(source.includes('AppPageHeader'), true, relativePath)
    assert.equal(source.includes('class="page-header"'), false, relativePath)
    assert.equal(source.includes('.page-header'), false, relativePath)
    assert.equal(source.includes('.page-title'), false, relativePath)
    assert.equal(source.includes('.page-subtitle'), false, relativePath)
  }
})
