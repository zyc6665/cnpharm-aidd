import { nextTick, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getTaskLogs } from '@/api/tasks'
import { useWebSocket } from '@/composables/useWebSocket'
import type { Task, TaskLog, WSMessage } from '@/types/models'
import { useTaskDetailLiveUpdates } from './useTaskDetailLiveUpdates'

const websocket = vi.hoisted(() => ({
  connect: vi.fn(),
  disconnect: vi.fn(),
  onMessage: vi.fn(),
}))

vi.mock('@/api/tasks', () => ({
  getTaskLogs: vi.fn(),
}))

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: vi.fn(() => websocket),
}))

function buildTask(status: Task['status'], progress = 0): Task {
  return {
    id: 'task-1',
    tool_id: 'tool-1',
    status,
    progress,
    created_at: '2026-08-20T00:00:00Z',
  }
}

function mockLogs(logs: TaskLog[] = []) {
  vi.mocked(getTaskLogs).mockResolvedValue({
    code: 200,
    message: 'ok',
    data: logs,
  } as never)
}

describe('useTaskDetailLiveUpdates', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(getTaskLogs).mockReset()
    vi.mocked(useWebSocket).mockClear()
    websocket.connect.mockReset()
    websocket.disconnect.mockReset()
    websocket.onMessage.mockReset()
    websocket.onMessage.mockReturnValue(vi.fn())
    mockLogs()
  })

  it('loads detail and logs, connects task websocket, and refreshes running tasks', async () => {
    const task = ref<Task | null>(buildTask('running', 10))
    const fetchTaskDetail = vi.fn()
    const updates = useTaskDetailLiveUpdates({
      taskId: ref('task-1'),
      task,
      fetchTaskDetail,
      updateTaskProgress: vi.fn(),
      intervalMs: 1000,
    })

    await updates.start()

    expect(fetchTaskDetail).toHaveBeenCalledTimes(1)
    expect(getTaskLogs).toHaveBeenCalledWith('task-1')
    expect(websocket.connect).toHaveBeenCalledWith('/api/v1/ws/tasks/task-1')
    expect(websocket.onMessage).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1000)

    expect(fetchTaskDetail).toHaveBeenCalledTimes(2)
  })

  it('applies websocket progress, appends logs, and refreshes terminal messages', async () => {
    let handler: ((message: WSMessage) => void) | undefined
    websocket.onMessage.mockImplementation((nextHandler: (message: WSMessage) => void) => {
      handler = nextHandler
      return vi.fn()
    })
    const task = ref<Task | null>(buildTask('running', 10))
    const fetchTaskDetail = vi.fn()
    const updateTaskProgress = vi.fn((taskId: string, progress: number, status?: Task['status']) => {
      task.value = {
        ...task.value!,
        id: taskId,
        progress,
        status: status ?? task.value!.status,
      }
    })
    const updates = useTaskDetailLiveUpdates({
      taskId: ref('task-1'),
      task,
      fetchTaskDetail,
      updateTaskProgress,
      now: () => 101,
      timestamp: () => '2026-08-20T00:00:01Z',
    })

    await updates.start()
    vi.mocked(getTaskLogs).mockClear()
    fetchTaskDetail.mockClear()

    handler?.({ type: 'task_progress', task_id: 'task-1', progress_percent: 42, status: 'running' })
    handler?.({ type: 'task_log', task_id: 'task-1', log: 'started', level: 'info' })
    handler?.({ type: 'task_complete', task_id: 'task-1' })
    await vi.runAllTimersAsync()

    expect(updateTaskProgress).toHaveBeenCalledWith('task-1', 42, 'running')
    expect(updateTaskProgress).toHaveBeenCalledWith('task-1', 100, 'success')
    expect(updates.logs.value).toContainEqual({
      id: 101,
      task_id: 'task-1',
      level: 'info',
      message: 'started',
      timestamp: '2026-08-20T00:00:01Z',
    })
    expect(fetchTaskDetail).toHaveBeenCalledTimes(1)
    expect(getTaskLogs).toHaveBeenCalledWith('task-1')
  })

  it('restarts the live channel when the task id changes', async () => {
    const unsubscribe = vi.fn()
    websocket.onMessage.mockReturnValue(unsubscribe)
    vi.mocked(getTaskLogs)
      .mockResolvedValueOnce({
        code: 200,
        message: 'ok',
        data: [{ id: 1, task_id: 'task-1', level: 'info', message: 'old', timestamp: '2026-08-20T00:00:00Z' }],
      } as never)
      .mockResolvedValueOnce({
        code: 200,
        message: 'ok',
        data: [{ id: 2, task_id: 'task-2', level: 'info', message: 'new', timestamp: '2026-08-20T00:00:01Z' }],
      } as never)
    const taskId = ref('task-1')
    const task = ref<Task | null>(buildTask('success', 100))
    const fetchTaskDetail = vi.fn()
    const updates = useTaskDetailLiveUpdates({
      taskId,
      task,
      fetchTaskDetail,
      updateTaskProgress: vi.fn(),
    })

    await updates.start()

    taskId.value = 'task-2'
    await nextTick()
    await flushPromises()

    expect(unsubscribe).toHaveBeenCalledTimes(1)
    expect(websocket.disconnect).toHaveBeenCalledTimes(1)
    expect(fetchTaskDetail).toHaveBeenCalledTimes(2)
    expect(getTaskLogs).toHaveBeenLastCalledWith('task-2')
    expect(websocket.connect).toHaveBeenLastCalledWith('/api/v1/ws/tasks/task-2')
    expect(updates.logs.value).toEqual([
      { id: 2, task_id: 'task-2', level: 'info', message: 'new', timestamp: '2026-08-20T00:00:01Z' },
    ])
  })
})
