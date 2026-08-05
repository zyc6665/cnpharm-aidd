import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  buildToolListParams,
  formatToolCount,
  getToolSortLabelKey,
  getToolViewLabelKey
} from './listing'

test('工具列表请求参数统一处理搜索空值和分页排序字段', () => {
  assert.deepEqual(
    buildToolListParams({
      view: 'favorites',
      searchKeyword: '  pocket  ',
      selectedCategory: 'Pocket',
      selectedTag: 'biology',
      currentPage: 2,
      pageSize: 24,
      sortBy: 'newest'
    }),
    {
      view: 'favorites',
      search: 'pocket',
      category: 'Pocket',
      tag: 'biology',
      page: 2,
      page_size: 24,
      sort_by: 'newest'
    }
  )

  assert.deepEqual(
    buildToolListParams({
      view: 'public',
      searchKeyword: '   ',
      currentPage: 1,
      pageSize: 12,
      sortBy: 'popular'
    }),
    {
      view: 'public',
      search: undefined,
      category: undefined,
      tag: undefined,
      page: 1,
      page_size: 12,
      sort_by: 'popular'
    }
  )
})

test('工具列表排序和视图展示使用稳定 i18n key', () => {
  assert.equal(getToolSortLabelKey('popular'), 'tools.sortPopular')
  assert.equal(getToolSortLabelKey('newest'), 'tools.sortNewest')
  assert.equal(getToolSortLabelKey('name'), 'tools.sortName')
  assert.equal(getToolSortLabelKey('unknown'), 'tools.sortPopular')
  assert.equal(getToolViewLabelKey('favorites'), 'tools.favorites')
  assert.equal(getToolViewLabelKey('public'), 'tools.publicTools')
})

test('工具统计数字保持卡片旧格式', () => {
  assert.equal(formatToolCount(undefined), '0')
  assert.equal(formatToolCount(null), '0')
  assert.equal(formatToolCount(999), '999')
  assert.equal(formatToolCount(1000), '1.0k')
  assert.equal(formatToolCount(10000), '1.0w')
})
