import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getTaskDetail } from '@/api/tasks'
import { useWorkflowNodeTaskPolling } from './useWorkflowNodeTaskPolling'

vi.mock('@/api/tasks', () => ({
  getTaskDetail: vi.fn(),
  isTaskTerminalStatus: (status: string) => ['success', 'failure', 'canceled'].includes(status),
}))

describe('useWorkflowNodeTaskPolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(getTaskDetail).mockReset()
  })

  it('polls all non-terminal node tasks and stops terminal tasks', async () => {
    const taskByNode = ref({
      a: {
        id: 'task-a',
        tool_id: 'tool-a',
        status: 'running' as const,
        progress: 10,
        created_at: '2026-08-20T00:00:00Z',
      },
      b: {
        id: 'task-b',
        tool_id: 'tool-b',
        status: 'success' as const,
        progress: 100,
        created_at: '2026-08-20T00:00:00Z',
      },
    })
    const recordNodeTask = vi.fn()
    vi.mocked(getTaskDetail).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: { id: 'task-a', status: 'success', progress: 100 },
    } as never)

    const polling = useWorkflowNodeTaskPolling({
      taskByNode,
      recordNodeTask,
      intervalMs: 1000,
    })

    await vi.advanceTimersByTimeAsync(1000)

    expect(getTaskDetail).toHaveBeenCalledWith('task-a')
    expect(getTaskDetail).not.toHaveBeenCalledWith('task-b')
    expect(recordNodeTask).toHaveBeenCalledWith('a', expect.objectContaining({ id: 'task-a' }))

    polling.stop()
  })
})
