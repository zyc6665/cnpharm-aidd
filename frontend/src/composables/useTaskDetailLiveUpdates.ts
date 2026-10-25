import { computed, getCurrentScope, onScopeDispose, ref, watch, type Ref } from 'vue'
import { getTaskLogs } from '@/api/tasks'
import { openTaskEventStream, type TaskEventPayload, type TaskLogEventPayload } from '@/api/task-events'
import type { Task, TaskLog, TaskStatus } from '@/types/models'
import { extractTaskLogs, normalizeTaskLogLevel, normalizeTaskStatus } from '@/domain/tasks'

export interface TaskDetailLiveUpdatesOptions {
  taskId: Ref<string>
  task: Ref<Task | null>
  fetchTaskDetail: () => Promise<unknown>
  updateTaskProgress: (taskId: string, progress: number, status?: TaskStatus) => void
  /** SSE 不可用（EventSource 缺失）时的兜底轮询间隔。 */
  intervalMs?: number
  now?: () => number
  timestamp?: () => string
}

/**
 * 任务详情页的实时更新（docs/10 API-08：实时进度走 SSE，禁止前端轮询 < 2s）。
 *
 * 正常情况下由 `GET /api/v1/tasks/{id}/events` 推送状态、进度与日志；只有在
 * 运行环境没有 `EventSource` 或连接失败时才退回 5s 轮询，且轮询仅在运行中启用。
 */
export function useTaskDetailLiveUpdates(options: TaskDetailLiveUpdatesOptions) {
  const logs = ref<TaskLog[]>([])
  const logsLoading = ref(false)
  const streamConnected = ref(false)
  const intervalMs = options.intervalMs ?? 5000
  const now = options.now ?? (() => Date.now())
  const timestamp = options.timestamp ?? (() => new Date().toISOString())
  const taskStatus = computed(() => normalizeTaskStatus(options.task.value?.status))
  let refreshTimer: number | null = null
  let closeStream: (() => void) | null = null
  let logSequence = 0
  let started = false

  async function fetchLogs(taskId = options.taskId.value) {
    logsLoading.value = true
    try {
      const response = await getTaskLogs(taskId)
      if (taskId !== options.taskId.value) {
        return
      }

      logs.value = mergeTaskLogs(extractTaskLogs(response.data), logs.value)
    } catch {
      // Request errors are surfaced by the shared API layer.
    } finally {
      logsLoading.value = false
    }
  }

  async function refreshTaskAndLogs(taskId = options.taskId.value) {
    await Promise.allSettled([options.fetchTaskDetail(), fetchLogs(taskId)])
  }

  function stopRefresh() {
    if (refreshTimer) {
      window.clearInterval(refreshTimer)
      refreshTimer = null
    }
  }

  function startRefresh() {
    if (refreshTimer || streamConnected.value) {
      return
    }

    refreshTimer = window.setInterval(() => {
      if (taskStatus.value === 'running') {
        void options.fetchTaskDetail()
      }
    }, intervalMs)
  }

  function applyEventPayload(payload: TaskEventPayload, behavior: { refreshOnTerminal: boolean }) {
    if (payload.taskId !== options.taskId.value) {
      return
    }

    updateProgress(payload)

    if (payload.terminal) {
      stopRefresh()
      if (behavior.refreshOnTerminal) {
        void refreshTaskAndLogs()
      }
    }
  }

  function updateProgress(payload: TaskEventPayload) {
    options.updateTaskProgress(
      payload.taskId,
      Math.round(payload.progress ?? 0),
      payload.status ? normalizeTaskStatus(payload.status) : undefined,
    )
  }

  function appendStreamLog(payload: TaskLogEventPayload) {
    if (payload.taskId !== options.taskId.value) {
      return
    }

    logSequence += 1
    logs.value.push({
      id: logSequence,
      task_id: payload.taskId,
      level: normalizeTaskLogLevel(payload.level),
      message: payload.message,
      timestamp: payload.timestamp || timestamp(),
    })
  }

  function openCurrentTaskChannel() {
    const currentTaskId = options.taskId.value
    logs.value = []
    logSequence = 0
    void refreshTaskAndLogs(currentTaskId)

    const handle = openTaskEventStream(currentTaskId, {
      onSnapshot: (payload) => applyEventPayload(payload, { refreshOnTerminal: false }),
      onStatus: (payload) => applyEventPayload(payload, { refreshOnTerminal: true }),
      onProgress: (payload) => applyEventPayload(payload, { refreshOnTerminal: false }),
      onLog: appendStreamLog,
      onDone: (payload) => applyEventPayload(payload, { refreshOnTerminal: true }),
      onError: () => {
        // 连接失败（代理不支持流式、网络抖动）时退回轮询，保证页面不僵死。
        streamConnected.value = false
        startRefresh()
      },
    })

    streamConnected.value = handle.available
    closeStream = handle.close

    if (!handle.available && taskStatus.value === 'running') {
      startRefresh()
    }
  }

  async function start() {
    started = true
    openCurrentTaskChannel()
  }

  function closeCurrentTaskChannel() {
    stopRefresh()
    closeStream?.()
    closeStream = null
    streamConnected.value = false
  }

  function stop() {
    started = false
    closeCurrentTaskChannel()
  }

  watch(
    () => options.taskId.value,
    (taskId, previousTaskId) => {
      if (!started || taskId === previousTaskId) {
        return
      }

      closeCurrentTaskChannel()
      openCurrentTaskChannel()
    }
  )

  watch(taskStatus, (status) => {
    if (status === 'running') {
      startRefresh()
      return
    }

    stopRefresh()

    if (['success', 'failure', 'canceled'].includes(status)) {
      void fetchLogs()
    }
  })

  if (getCurrentScope()) {
    onScopeDispose(stop)
  }

  return {
    logs,
    logsLoading,
    streamConnected,
    fetchLogs,
    start,
    stop,
  }
}

function mergeTaskLogs(primaryLogs: TaskLog[], fallbackLogs: TaskLog[]): TaskLog[] {
  const seen = new Set(primaryLogs.map(taskLogKey))
  return [...primaryLogs, ...fallbackLogs.filter((log) => !seen.has(taskLogKey(log)))]
}

function taskLogKey(log: TaskLog): string {
  return `${log.id}:${log.task_id}:${log.timestamp}:${log.message}`
}
