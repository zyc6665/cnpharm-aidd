/**
 * 等待一个任务到达终态（用于「就地预测后自动推进」）。
 *
 * 优先走既有 SSE（`openTaskEventStream`）；在没有 EventSource 的环境或连接失败时，
 * 回退到 `getTaskDetail` 轮询。无论走哪条通道，都以 `timeoutMs` 兜底，
 * 避免任务停滞时 Promise 永远挂起、界面卡在 loading。
 */
import {
  openTaskEventStream,
  type TaskEventPayload,
  type TaskEventStreamHandle,
} from '@/api/task-events'
import { getTaskDetail } from '@/api/tasks'
import { isTerminalTask } from '@/domain/tasks/status'
import type { TaskStatus } from '@/types/models'

export interface TaskCompletionResult {
  status: TaskStatus
  ok: boolean
}

export interface TaskCompletionOptions {
  /** 轮询间隔（ms），默认 3000。 */
  pollMs?: number
  /** 超时上限（ms），默认 600000（10 分钟）。 */
  timeoutMs?: number
  /** 便于测试注入；默认 `getTaskDetail`。 */
  detailFetcher?: (taskId: string) => Promise<{ data: { status: TaskStatus } }>
}

export function waitForTaskCompletion(
  taskId: string,
  options: TaskCompletionOptions = {}
): Promise<TaskCompletionResult> {
  const pollMs = options.pollMs ?? 3000
  const timeoutMs = options.timeoutMs ?? 600000
  const fetchDetail = options.detailFetcher ?? getTaskDetail

  return new Promise<TaskCompletionResult>(resolve => {
    let settled = false
    let pollTimer: ReturnType<typeof setTimeout> | null = null
    let timeoutTimer: ReturnType<typeof setTimeout> | null = null
    let handle: TaskEventStreamHandle = { close: () => undefined, available: false }

    const finish = (status: TaskStatus) => {
      if (settled) return
      settled = true
      if (pollTimer) {
        clearTimeout(pollTimer)
        pollTimer = null
      }
      if (timeoutTimer) {
        clearTimeout(timeoutTimer)
        timeoutTimer = null
      }
      handle.close()
      resolve({ status, ok: status === 'success' })
    }

    const poll = async () => {
      if (settled) return
      try {
        const response = await fetchDetail(taskId)
        const status = response.data.status
        if (isTerminalTask({ status })) {
          finish(status)
          return
        }
      } catch {
        // 单次拉取失败不终止，按轮询继续。
      }
      if (!settled) {
        pollTimer = setTimeout(() => void poll(), pollMs)
      }
    }

    const onEvent = (payload: TaskEventPayload) => {
      if (payload.terminal && payload.status) {
        finish(payload.status)
      }
    }

    handle = openTaskEventStream(taskId, {
      onStatus: onEvent,
      onDone: onEvent,
      onError: () => {
        // SSE 不可用/中断 → 回退轮询。
        if (!settled && !pollTimer) {
          pollTimer = setTimeout(() => void poll(), pollMs)
        }
      },
    })

    if (!handle.available) {
      pollTimer = setTimeout(() => void poll(), pollMs)
    }

    // 无论 SSE 是否可用都必须有超时兜底（SSE 可能连上但任务停滞、一直非终态）。
    timeoutTimer = setTimeout(() => finish('timeout' as TaskStatus), timeoutMs)
  })
}
