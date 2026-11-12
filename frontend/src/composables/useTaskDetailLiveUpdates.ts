import { computed, getCurrentScope, onScopeDispose, ref, watch, type Ref } from 'vue'
import { getTaskLogs } from '@/api/tasks'
import { openTaskEventStream, type TaskEventPayload, type TaskLogEventPayload } from '@/api/task-events'
import type { Task, TaskLog, TaskStatus } from '@/types/models'
import { extractTaskLogs, normalizeTaskLogLevel, normalizeTaskStatus, terminalStatuses } from '@/domain/tasks'

/** 每次拉取的日志条数（后端上限 200）。 */
const LOG_PAGE_SIZE = 200

/** 内存里保留的最大日志条数，防止一次超长任务把页面拖慢。 */
const LOG_MAX_ITEMS = 500

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
      // 从**最新**一段开始取（order=desc），而不是从任务开头那一页。
      // 长任务日志上千行，取第 1 页升序等于把界面钉死在「刚开始」，
      // 看上去就是「日志不再更新」（docs/17 §5.64）。
      const response = await getTaskLogs(taskId, {
        page_size: LOG_PAGE_SIZE,
        order: 'desc',
      })
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

    if (terminalStatuses.includes(status)) {
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
  const byKey = new Map<string, TaskLog>()
  for (const log of [...fallbackLogs, ...primaryLogs]) {
    byKey.set(taskLogKey(log), log)
  }
  const merged = [...byKey.values()].sort(compareTaskLogOrder)
  // 只保留最近的一段：日志面板是「看现在在干什么」的地方，不是归档。
  return merged.slice(-LOG_MAX_ITEMS)
}

function compareTaskLogOrder(left: TaskLog, right: TaskLog): number {
  const leftTime = Date.parse(left.timestamp)
  const rightTime = Date.parse(right.timestamp)
  if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) {
    return leftTime - rightTime
  }
  return String(left.id).localeCompare(String(right.id))
}

function taskLogKey(log: TaskLog): string {
  return `${log.id}:${log.task_id}:${log.timestamp}:${log.message}`
}
