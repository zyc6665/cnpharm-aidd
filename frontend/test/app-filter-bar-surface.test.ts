import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('应提供统一筛选栏组件承载列表页筛选控件', () => {
  const componentPath = resolve(rootDir, 'src/components/common/AppFilterBar.vue')

  assert.equal(existsSync(componentPath), true)

  const source = readFileSync(componentPath, 'utf8')
  assert.equal(source.includes('app-filter-bar'), true)
  assert.equal(source.includes('<slot />'), true)
})

test('工具列表和任务列表应复用 AppFilterBar 而不是各自维护 filter-bar 样式', () => {
  for (const relativePath of ['src/views/tools/List.vue', 'src/views/tasks/List.vue']) {
    const source = readSource(relativePath)

    assert.equal(source.includes('AppFilterBar'), true, relativePath)
    assert.equal(source.includes('class="filter-bar"'), false, relativePath)
    assert.equal(source.includes('.filter-bar'), false, relativePath)
  }
})
