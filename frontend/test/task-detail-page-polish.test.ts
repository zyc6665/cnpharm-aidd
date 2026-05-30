import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('任务详情页应使用统一页头承载标题和主要操作', () => {
  const source = readSource('src/views/tasks/Detail.vue')

  assert.equal(source.includes('AppPageHeader'), true)
  assert.equal(source.includes(':title="detailTitle"'), true)
  assert.equal(source.includes(':subtitle="detailSubtitle"'), true)
  assert.equal(source.includes('task-detail-actions'), true)
  assert.equal(source.includes('<a-space class="task-detail-actions" wrap>'), true)
})

test('任务详情页状态卡和侧栏应优化移动端可读性', () => {
  const source = readSource('src/views/tasks/Detail.vue')

  assert.equal(source.includes('status-label'), true)
  assert.equal(source.includes('status-line'), true)
  assert.equal(source.includes('word-break: break-all'), true)
  assert.equal(source.includes('position: sticky'), true)
})
