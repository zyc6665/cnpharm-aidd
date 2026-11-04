import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
vi.mock('@/api/tasks', () => ({ getTaskDetail: vi.fn() }))
import { getTaskDetail } from '@/api/tasks'
import { waitForTaskCompletion } from './useTaskCompletion'

describe('waitForTaskCompletion', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(getTaskDetail).mockReset()
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
})
