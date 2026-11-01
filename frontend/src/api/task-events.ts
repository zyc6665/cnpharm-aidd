import type { TaskStatus } from '@/types/models'

/**
 * 任务事件流客户端（docs/05 §1.5、§9；docs/10 API-08）。
 *
 * 为什么用 SSE 而不是 WebSocket：
 * - SSE 是普通 HTTP 响应，能穿过任何 Nginx/Ingress 而不需要额外配置 upgrade；
 * - 断线由浏览器自动重连，服务端按 `id:` 重放，不需要自定义重连协议；
 * - 交付线只需要「服务端 → 浏览器」单向推送，用双向通道是多余的能力。
 *
 * 认证：依赖 httpOnly Cookie（同源/携带凭据的 EventSource 会自动带上），
 * 不再把 token 拼进查询参数。
 */

export type TaskEventName = 'snapshot' | 'status' | 'progress' | 'log' | 'done'

export interface TaskEventPayload {
  taskId: string
  status: TaskStatus | null
  rawStatus: string | null
  progress: number
  progressMessage: string | null
  errorMessage: string | null
  updatedAt: string | null
  terminal: boolean
}

export interface TaskLogEventPayload {
  id: string
  taskId: string
  level: string
  message: string
  timestamp: string
}

export interface TaskEventStreamHandlers {
  onSnapshot?: (payload: TaskEventPayload) => void
  onStatus?: (payload: TaskEventPayload) => void
  onProgress?: (payload: TaskEventPayload) => void
  onLog?: (payload: TaskLogEventPayload) => void
  onDone?: (payload: TaskEventPayload) => void
  onError?: (error: unknown) => void
}

export interface TaskEventStreamOptions {
  baseUrl?: string
  includeLogs?: boolean
  maxSeconds?: number
}

export interface TaskEventStreamHandle {
  close: () => void
  available: boolean
}

const TASK_EVENT_NAMES: TaskEventName[] = ['snapshot', 'status', 'progress', 'log', 'done']

function resolveBaseUrl(baseUrl?: string): string {
  const configured = baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? ''
  return configured.replace(/\/+$/, '')
}

export function buildTaskEventStreamUrl(
  taskId: string,
  options: TaskEventStreamOptions = {}
): string {
  const params: string[] = []
  if (options.includeLogs === false) {
    params.push('include_logs=false')
  }
  if (typeof options.maxSeconds === 'number') {
    params.push(`max_seconds=${options.maxSeconds}`)
  }
  const query = params.length > 0 ? `?${params.join('&')}` : ''
  const base = resolveBaseUrl(options.baseUrl)
  // VITE_API_BASE_URL 已包含 API 前缀；不能再重复拼接。
  const prefix = base || '/api/v1'
  return `${prefix}/tasks/${taskId}/events${query}`
}

function parsePayload<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export function openTaskEventStream(
  taskId: string,
  handlers: TaskEventStreamHandlers,
  options: TaskEventStreamOptions = {}
): TaskEventStreamHandle {
  if (typeof EventSource === 'undefined') {
    // 测试环境或极旧浏览器：调用方回退到轮询。
    return { close: () => undefined, available: false }
  }

  const source = new EventSource(buildTaskEventStreamUrl(taskId, options), { withCredentials: true })
  let closed = false

  const close = () => {
    if (!closed) {
      closed = true
      source.close()
    }
  }

  const bind = <T>(name: TaskEventName, handler?: (payload: T) => void) => {
    if (!handler) {
      return
    }
    source.addEventListener(name, (event: MessageEvent<string>) => {
      const payload = parsePayload<T>(event.data)
      if (payload !== null) {
        handler(payload)
      }
    })
  }

  bind<TaskEventPayload>('snapshot', handlers.onSnapshot)
  bind<TaskEventPayload>('status', handlers.onStatus)
  bind<TaskEventPayload>('progress', handlers.onProgress)
  bind<TaskLogEventPayload>('log', handlers.onLog)
  bind<TaskEventPayload>('done', (payload) => {
    handlers.onDone?.(payload)
    // 终态后服务端已关流，主动 close 避免浏览器自动重连。
    close()
  })

  source.onerror = (error) => {
    handlers.onError?.(error)
  }

  return { close, available: true }
}

export { TASK_EVENT_NAMES }
