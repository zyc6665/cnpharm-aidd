import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * 分页双绑回归守卫。
 *
 * `a-pagination` 改页大小时会连发 `showSizeChange(current, size)` 与
 * `change(current, size)` 两个事件，且第二个事件的页码是**旧页码**。
 * 两个 handler 并存会导致：一次操作打两次请求 + 「回第 1 页」被覆盖回旧页码。
 *
 * 这类缺陷在单元测试里很难暴露（要模拟 antd 的事件顺序），因此直接扫源码断言语义：
 * 分页组件只允许绑 `@change`，页大小变化由 `resolvePaginationChange` 判别。
 */

const FRONTEND_ROOT = resolve(__dirname, '..')

const PAGINATED_PAGES = [
  'src/views/tasks/List.vue',
  'src/views/tools/List.vue',
  'src/views/projects/Decisions.vue',
]

function read(relativePath: string): string {
  return readFileSync(resolve(FRONTEND_ROOT, relativePath), 'utf-8')
}

test('分页组件不得同时绑定 show-size-change（会把回第 1 页覆盖掉）', () => {
  for (const page of PAGINATED_PAGES) {
    const source = read(page)
    assert.equal(
      /@show-size-change\s*=/.test(source),
      false,
      `${page} 仍绑定了 @show-size-change；改页大小应由 @change 里的 resolvePaginationChange 处理`
    )
    assert.equal(
      /@showSizeChange\s*=/.test(source),
      false,
      `${page} 仍绑定了 @showSizeChange；改页大小应由 @change 里的 resolvePaginationChange 处理`
    )
  }
})

test('分页组件必须绑定 @change', () => {
  for (const page of PAGINATED_PAGES) {
    assert.match(read(page), /@change="handlePageChange"/, `${page} 缺少 @change 处理`)
  }
})

test('分页变更必须经共享的 resolvePaginationChange，不在页面里各写一套', () => {
  for (const page of PAGINATED_PAGES) {
    const source = read(page)
    if (page.endsWith('Decisions.vue')) {
      // 决策页在本次修复前已自带等价逻辑（`clampDecisionPageSize` 等），
      // 这里只要求它不出现双绑即可（已由前两个用例覆盖）。
      continue
    }
    assert.match(
      source,
      /resolvePaginationChange\s*\(/,
      `${page} 未使用 resolvePaginationChange，可能又写了一套页大小判断`
    )
  }
})

test('共享分页工具本身覆盖「旧页码 + 新页大小」的核心场景', () => {
  const source = read('src/utils/pagination.ts')
  assert.match(source, /export function resolvePaginationChange/)
  assert.match(source, /return \{ page: 1, size \}/, '页大小变化时未回到第 1 页')
})
