import { computed, getCurrentScope, onScopeDispose, ref, watch, type Ref } from 'vue'
import { getTaskLogs } from '@/api/tasks'
import { useWebSocket } from '@/composables/useWebSocket'
import type { Task, TaskLog, TaskStatus, WSMessage } from '@/types/models'
import {
  extractTaskLogs,
  isTaskWebSocketMessageForTask,
  normalizeTaskStatus,
  resolveTaskWebSocketLog,
  resolveTaskWebSocketProgressUpdate,
  shouldRefreshTaskAfterWebSocketMessage,
} from '@/domain/tasks'

export interface TaskDetailLiveUpdatesOptions {
  taskId: Ref<string>
  task: Ref<Task | null>
  fetchTaskDetail: () => Promise<unknown>
  updateTaskProgress: (taskId: string, progress: number, status?: TaskStatus) => void
  intervalMs?: number
  now?: () => number
  timestamp?: () => string
}

export function useTaskDetailLiveUpdates(options: TaskDetailLiveUpdatesOptions) {
  const websocket = useWebSocket()
  const logs = ref<TaskLog[]>([])
  const logsLoading = ref(false)
  const intervalMs = options.intervalMs ?? 5000
  const now = options.now ?? (() => Date.now())
  const timestamp = options.timestamp ?? (() => new Date().toISOString())
  const taskStatus = computed(() => normalizeTaskStatus(options.task.value?.status))
  let refreshTimer: number | null = null
  let unsubscribeMessages: (() => void) | null = null

  async function fetchLogs() {
    logsLoading.value = true
    try {
      const response = await getTaskLogs(options.taskId.value)
      logs.value = mergeTaskLogs(extractTaskLogs(response.data), logs.value)
    } catch {
      // Request errors are surfaced by the shared API layer.
    } finally {
      logsLoading.value = false
    }
  }

  async function refreshTaskAndLogs() {
    await Promise.allSettled([
      options.fetchTaskDetail(),
      fetchLogs(),
    ])
  }

  function stopRefresh() {
    if (refreshTimer) {
      window.clearInterval(refreshTimer)
      refreshTimer = null
    }
  }

  function startRefresh() {
    if (refreshTimer) {
      return
    }

    refreshTimer = window.setInterval(() => {
      if (taskStatus.value === 'running') {
        void options.fetchTaskDetail()
      }
    }, intervalMs)
  }

  function handleWebSocketMessage(message: WSMessage) {
    if (!isTaskWebSocketMessageForTask(message, options.taskId.value)) {
      return
    }

    const progressUpdate = resolveTaskWebSocketProgressUpdate(message, {
      taskId: options.taskId.value,
      currentProgress: options.task.value?.progress ?? 0,
    })
    if (progressUpdate) {
      options.updateTaskProgress(
        progressUpdate.taskId,
        progressUpdate.progress,
        progressUpdate.status,
      )
    }

    const logEntry = resolveTaskWebSocketLog(message, {
      taskId: options.taskId.value,
      id: now(),
      timestamp: timestamp(),
    })
    if (logEntry) {
      logs.value.push(logEntry)
    }

    if (shouldRefreshTaskAfterWebSocketMessage(message)) {
      void refreshTaskAndLogs()
    }
  }

  async function start() {
    await refreshTaskAndLogs()
    websocket.connect(`/api/v1/ws/tasks/${options.taskId.value}`)
    unsubscribeMessages?.()
    unsubscribeMessages = websocket.onMessage(handleWebSocketMessage)

    if (taskStatus.value === 'running') {
      startRefresh()
    }
  }

  function stop() {
    stopRefresh()
    unsubscribeMessages?.()
    unsubscribeMessages = null
    websocket.disconnect()
  }

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
    fetchLogs,
    start,
    stop,
  }
}

function mergeTaskLogs(primaryLogs: TaskLog[], fallbackLogs: TaskLog[]): TaskLog[] {
  const seen = new Set(primaryLogs.map(taskLogKey))
  return [
    ...primaryLogs,
    ...fallbackLogs.filter(log => !seen.has(taskLogKey(log))),
  ]
}

function taskLogKey(log: TaskLog): string {
  return `${log.id}:${log.task_id}:${log.timestamp}:${log.message}`
}
