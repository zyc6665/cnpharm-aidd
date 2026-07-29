import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('任务列表卡片应支持键盘访问和可见焦点态', () => {
  const source = readSource('src/views/tasks/List.vue')

  assert.equal(source.includes('role="button"'), true)
  assert.equal(source.includes('tabindex="0"'), true)
  assert.equal(source.includes(':aria-label='), true)
  assert.equal(source.includes('@keydown.enter="goToDetail(task.id)"'), true)
  assert.equal(source.includes('@keydown.space.prevent="goToDetail(task.id)"'), true)
  assert.equal(source.includes('&:focus-visible'), true)
})

test('任务列表卡片应在窄屏下稳定换行操作区', () => {
  const source = readSource('src/views/tasks/List.vue')

  assert.equal(source.includes('task-action-space'), true)
  assert.equal(source.includes('<a-space class="task-action-space" wrap>'), true)
  assert.equal(source.includes('flex-wrap: wrap'), true)
  assert.equal(source.includes('word-break: break-word'), true)
})

test('任务列表卡片不应展示成功任务运行时长', () => {
  const source = readSource('src/views/tasks/List.vue')

  assert.equal(source.includes('class="duration"'), false)
  assert.equal(source.includes('FieldTimeOutlined'), false)
  assert.equal(source.includes('calculateDuration('), false)
})
