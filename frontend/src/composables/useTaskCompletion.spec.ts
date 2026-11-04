import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
vi.mock('@/api/tasks', () => ({ getTaskDetail: vi.fn() }))
vi.mock('@/api/task-events', () => ({ openTaskEventStream: vi.fn() }))
import { getTaskDetail } from '@/api/tasks'
import { openTaskEventStream } from '@/api/task-events'
import { waitForTaskCompletion } from './useTaskCompletion'

describe('waitForTaskCompletion', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(getTaskDetail).mockReset()
    vi.mocked(openTaskEventStream).mockReset()
    vi.mocked(openTaskEventStream).mockReturnValue({ available: false, close: vi.fn() } as never)
  })
  afterEach(() => vi.useRealTimers())

  it('resolves when polled status becomes success', async () => {
    vi.mocked(getTaskDetail)
      .mockResolvedValueOnce({ data: { status: 'running' } } as never)
      .mockResolvedValueOnce({ data: { status: 'success' } } as never)
    const promise = waitForTaskCompletion('t1', { pollMs: 10 })
    await vi.advanceTimersByTimeAsync(30)
    expect((await promise).ok).toBe(true)
  })

  it('times out even when SSE is connected but the task stalls', async () => {
    vi.mocked(openTaskEventStream).mockReturnValue({ available: true, close: vi.fn() } as never)
    const promise = waitForTaskCompletion('t1', { timeoutMs: 50 })
    await vi.advanceTimersByTimeAsync(80)
    const result = await promise
    expect(result.ok).toBe(false)
    expect(result.status).toBe('timeout')
  })
})
