import { test } from 'vitest'
import assert from 'node:assert/strict'
import { resolvePaginationChange } from './pagination'

test('改页大小时回到第 1 页，并返回新的页大小', () => {
  assert.deepEqual(
    resolvePaginationChange({ nextPage: 4, nextSize: 50, currentSize: 10 }),
    { page: 1, size: 50 }
  )
})

test('只翻页时保留页码，不返回页大小', () => {
  assert.deepEqual(
    resolvePaginationChange({ nextPage: 3, nextSize: 10, currentSize: 10 }),
    { page: 3, size: null }
  )
})

test('事件没带页大小时按翻页处理', () => {
  assert.deepEqual(
    resolvePaginationChange({ nextPage: 2, nextSize: undefined, currentSize: 10 }),
    { page: 2, size: null }
  )
  assert.deepEqual(
    resolvePaginationChange({ nextPage: 2, nextSize: null, currentSize: 10 }),
    { page: 2, size: null }
  )
})

test('页大小非法时视为未变化', () => {
  for (const invalid of [Number.NaN, 0, -5, 1.9e3 * 0]) {
    assert.deepEqual(
      resolvePaginationChange({ nextPage: 5, nextSize: invalid, currentSize: 10 }),
      { page: 5, size: null },
      `nextSize=${invalid}`
    )
  }
})

test('页码非法时收敛到第 1 页，避免请求带 page=NaN', () => {
  for (const invalid of [Number.NaN, 0, -3]) {
    assert.deepEqual(
      resolvePaginationChange({ nextPage: invalid, nextSize: 10, currentSize: 10 }),
      { page: 1, size: null },
      `nextPage=${invalid}`
    )
  }
})

test('页码与页大小的小数部分向零截断', () => {
  assert.deepEqual(
    resolvePaginationChange({ nextPage: 3.7, nextSize: 10, currentSize: 10 }),
    { page: 3, size: null }
  )
  assert.deepEqual(
    resolvePaginationChange({ nextPage: 1, nextSize: 20.9, currentSize: 10 }),
    { page: 1, size: 20 }
  )
})

test('当前页大小非法时，任何合法新页大小都算变化', () => {
  assert.deepEqual(
    resolvePaginationChange({ nextPage: 7, nextSize: 20, currentSize: Number.NaN }),
    { page: 1, size: 20 }
  )
})

test('「改页大小」事件携带旧页码是本次修复的核心场景', () => {
  // antd 在改页大小时第二个事件传的 nextPage 是改动前的页码（这里是 4），
  // 若直接采信就会停在第 4 页——而新页大小下可能只有 1 页。
  const result = resolvePaginationChange({ nextPage: 4, nextSize: 20, currentSize: 10 })
  assert.equal(result.page, 1)
  assert.equal(result.size, 20)
})
