import { nextTick, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getTaskLogs } from '@/api/tasks'
import { openTaskEventStream } from '@/api/task-events'
import type { Task, TaskLog } from '@/types/models'
import type { TaskEventPayload, TaskLogEventPayload } from '@/api/task-events'
import { useTaskDetailLiveUpdates } from './useTaskDetailLiveUpdates'

const stream = vi.hoisted(() => ({
  close: vi.fn(),
}))

const handlers = vi.hoisted(() => ({
  onSnapshot: undefined as ((payload: never) => void) | undefined,
  onStatus: undefined as ((payload: never) => void) | undefined,
  onProgress: undefined as ((payload: never) => void) | undefined,
  onLog: undefined as ((payload: never) => void) | undefined,
  onDone: undefined as ((payload: never) => void) | undefined,
  onError: undefined as ((payload: never) => void) | undefined,
}))

type StreamHandlers = {
  onSnapshot?: (payload: TaskEventPayload) => void
  onStatus?: (payload: TaskEventPayload) => void
  onProgress?: (payload: TaskEventPayload) => void
  onLog?: (payload: TaskLogEventPayload) => void
  onDone?: (payload: TaskEventPayload) => void
  onError?: (payload: unknown) => void
  [key: string]: unknown
}

vi.mock('@/api/tasks', () => ({
  getTaskLogs: vi.fn(),
}))

vi.mock('@/api/task-events', () => ({
  openTaskEventStream: vi.fn(),
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

function eventPayload(overrides: Record<string, unknown> = {}) {
  return {
    taskId: 'task-1',
    status: null,
    rawStatus: null,
    progress: 0,
    progressMessage: null,
    errorMessage: null,
    updatedAt: null,
    terminal: false,
    ...overrides,
  }
}

describe('useTaskDetailLiveUpdates', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(getTaskLogs).mockReset()
    vi.mocked(openTaskEventStream).mockReset()
    stream.close.mockReset()
    handlers.onSnapshot = undefined
    handlers.onStatus = undefined
    handlers.onProgress = undefined
    handlers.onLog = undefined
    handlers.onDone = undefined
    handlers.onError = undefined

    vi.mocked(openTaskEventStream).mockImplementation((_taskId, nextHandlers) => {
      const captured = nextHandlers as StreamHandlers
      handlers.onSnapshot = captured.onSnapshot as never
      handlers.onStatus = captured.onStatus as never
      handlers.onProgress = captured.onProgress as never
      handlers.onLog = captured.onLog as never
      handlers.onDone = captured.onDone as never
      handlers.onError = captured.onError as never
      return { close: stream.close, available: true }
    })
    mockLogs()
  })

  it('reports the backend total separately from the logs it keeps in memory', async () => {
    // 长任务动辄几百上千行，面板只保留最近 200 行；「共 N 条」必须说后端总量，
    // 否则界面会显示「共 200 条」，用户以为日志被截断（docs/17 §5.64）。
    const items: TaskLog[] = Array.from({ length: 200 }, (_, index) => ({
      id: index + 102,
      task_id: 'task-1',
      level: 'info',
      message: `line-${String(index + 101).padStart(3, '0')}`,
      timestamp: `2026-11-12T03:${String(Math.floor(index / 60)).padStart(2, '0')}:${String(index % 60).padStart(2, '0')}Z`,
    }))
    vi.mocked(getTaskLogs).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: { items, total: 301, page: 1, page_size: 200 },
    } as never)

    const updates = useTaskDetailLiveUpdates({
      taskId: ref('task-1'),
      task: ref<Task | null>(buildTask('success', 100)),
      fetchTaskDetail: vi.fn(),
      updateTaskProgress: vi.fn(),
    })

    await updates.start()

    expect(updates.logs.value).toHaveLength(200)
    expect(updates.logsTotal.value).toBe(301)
  })

  it('loads detail and logs, opens the SSE stream, and does not double-poll while connected', async () => {
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
    expect(getTaskLogs).toHaveBeenCalledWith('task-1', { page_size: 200, order: 'desc' })
    expect(openTaskEventStream).toHaveBeenCalledTimes(1)
    expect(updates.streamConnected.value).toBe(true)

    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchTaskDetail).toHaveBeenCalledTimes(1)
  })

  it('applies stream progress, appends stream logs, and refreshes on terminal events', async () => {
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
      timestamp: () => '2026-08-20T00:00:01Z',
    })

    await updates.start()
    vi.mocked(getTaskLogs).mockClear()
    fetchTaskDetail.mockClear()

    handlers.onProgress?.(eventPayload({ status: 'running', progress: 42 }) as never)
    handlers.onLog?.({ id: 'log-1', taskId: 'task-1', level: 'info', message: 'started', timestamp: '2026-08-20T00:00:01Z' } as never)
    handlers.onDone?.(eventPayload({ status: 'success', progress: 100, terminal: true }) as never)
    await vi.runAllTimersAsync()

    expect(updateTaskProgress).toHaveBeenCalledWith('task-1', 42, 'running')
    expect(updateTaskProgress).toHaveBeenCalledWith('task-1', 100, 'success')
    expect(updates.logs.value).toContainEqual({
      id: 1,
      task_id: 'task-1',
      level: 'info',
      message: 'started',
      timestamp: '2026-08-20T00:00:01Z',
    })
    expect(fetchTaskDetail).toHaveBeenCalledTimes(1)
    expect(getTaskLogs).toHaveBeenCalledWith('task-1', { page_size: 200, order: 'desc' })
  })

  it('ignores events addressed to another task', async () => {
    const task = ref<Task | null>(buildTask('running', 10))
    const updateTaskProgress = vi.fn()
    const updates = useTaskDetailLiveUpdates({
      taskId: ref('task-1'),
      task,
      fetchTaskDetail: vi.fn(),
      updateTaskProgress,
    })

    await updates.start()
    handlers.onProgress?.({ ...eventPayload(), taskId: 'task-2', progress: 99 } as never)

    expect(updateTaskProgress).not.toHaveBeenCalled()
    expect(updates.logs.value).toEqual([])
  })

  it('falls back to polling when the stream cannot be opened', async () => {
    vi.mocked(openTaskEventStream).mockImplementation(() => ({ close: vi.fn(), available: false }))
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
    expect(updates.streamConnected.value).toBe(false)

    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchTaskDetail).toHaveBeenCalledTimes(2)
  })

  it('closes the previous stream and opens a new one when the task id changes', async () => {
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

    expect(stream.close).toHaveBeenCalledTimes(1)
    expect(fetchTaskDetail).toHaveBeenCalledTimes(2)
    expect(getTaskLogs).toHaveBeenLastCalledWith('task-2', { page_size: 200, order: 'desc' })
    const calls = vi.mocked(openTaskEventStream).mock.calls
    expect(calls[calls.length - 1]?.[0]).toBe('task-2')
    expect(updates.logs.value).toEqual([
      { id: 2, task_id: 'task-2', level: 'info', message: 'new', timestamp: '2026-08-20T00:00:01Z' },
    ])
  })
})
