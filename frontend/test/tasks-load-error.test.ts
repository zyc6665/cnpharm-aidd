import { beforeEach, describe, expect, it, vi } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createPinia, setActivePinia } from 'pinia'

const mockGetTaskList = vi.fn()

vi.mock('@/api/tasks', () => ({
  getTaskList: (...args: unknown[]) => mockGetTaskList(...args),
  getTaskCounts: vi.fn(),
  getTaskDetail: vi.fn(),
  createTask: vi.fn(),
  prepareTaskRun: vi.fn(),
  cancelTask: vi.fn(),
  retryTask: vi.fn(),
  deleteTask: vi.fn(),
}))

import { useTasksStore } from '@/stores/tasks'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const readSource = (relativePath: string) =>
  readFileSync(resolve(rootDir, relativePath), 'utf8')

describe('任务列表加载失败不再伪装成空态', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockGetTaskList.mockReset()
  })

  it('fetchTasks 失败时设置 loadError，并保留可重试信号', async () => {
    mockGetTaskList.mockRejectedValueOnce(new Error('network down'))

    const store = useTasksStore()
    await expect(store.fetchTasks()).rejects.toThrow('network down')

    assert.equal(store.loadError, true)
    assert.deepEqual(store.tasks, [])
  })

  it('成功加载后清除 loadError', async () => {
    mockGetTaskList.mockResolvedValueOnce({ data: { items: [], total: 0 } })

    const store = useTasksStore()
    await store.fetchTasks()

    assert.equal(store.loadError, false)
  })

  it('任务列表页在 loadError 为真时渲染行内错误并提供重试按钮', () => {
    const source = readSource('src/views/tasks/List.vue')

    assert.equal(source.includes('AppInlineError'), true)
    assert.equal(source.includes('loadError'), true)
    // 重试走同一个加载函数
    assert.equal(source.includes('@click="fetchTasksSafely"'), true)
  })
})
