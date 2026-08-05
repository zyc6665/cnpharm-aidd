import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工具列表筛选控件应使用页面样式类避免移动端固定内联宽度', () => {
  const source = readSource('src/views/tools/List.vue')

  assert.equal(source.includes('tool-search-input'), true)
  assert.equal(source.includes('tool-filter-select'), true)
  assert.equal(source.includes('style="max-width: 400px"'), false)
  assert.equal(source.includes('style="width: 200px"'), false)
})

test('工具列表应在列表前展示当前结果摘要', () => {
  const source = readSource('src/views/tools/List.vue')
  const domain = readSource('src/domain/tools/listing.ts')

  assert.equal(source.includes('tools-results-summary'), true)
  assert.equal(source.includes('currentViewLabel'), true)
  assert.equal(source.includes("t('common.totalItems', { total: displayTotal })"), true)
  assert.equal(source.includes('tools-results-sort'), true)
  assert.equal(source.includes("from '@/domain/tools'"), true)
  assert.equal(source.includes('buildToolListParams'), true)
  assert.equal(domain.includes('getToolSortLabelKey'), true)
})
