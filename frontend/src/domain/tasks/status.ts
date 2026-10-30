import type { Task, TaskStatus } from '@/types/models'

export type TaskProgressStatus = 'normal' | 'active' | 'exception' | 'success'
export type TaskStatusTextKey =
  | 'tasks.statusPending'
  | 'tasks.statusRejected'
  | 'tasks.statusQueued'
  | 'tasks.statusRunning'
  | 'tasks.statusSuccess'
  | 'tasks.statusFailure'
  | 'tasks.statusTimeout'
  | 'tasks.statusCanceled'

/**
 * 「进行中」列表页签的口径：任务已创建但还没有出结果，用户需要在这里看到它。
 *
 * - `pending`：新建未调度（docs/03 §3.4 的 CREATED，API 词表沿用 `pending`）。
 * - `queued`：排队中，等 worker/GPU 资源。
 * - `running`：真正在执行。
 *
 * 判断依据：只有 `running` 算「正在执行」（progress 会走、可以实时看日志）；
 * `pending`/`queued` 都属于「未开始」。但任务中心 P-31 的「进行中」页签是
 * 「还没出结果的任务」而不是「正在跑的任务」—— 排队中的任务如果不在这个页签
 * 出现，用户会以为任务丢了，所以 `runningStatuses` 三者都收。
 * 需要严格判定「正在执行」时请用 `isExecutingTask`，不要用 `isRunningTask`。
 */
export const runningStatuses: readonly TaskStatus[] = ['pending', 'queued', 'running']

/**
 * 终态：不会再自行流转，只能重试或留在历史里。
 *
 * `rejected`（准入被拒）也是终态：它从未入队，状态机里只有
 * `PENDING -> REJECTED` 这一条入边，且**没有出边**（不可重试——重试接口不做
 * 配额准入，允许重试等于给「提交被拒 → 点重试」开一条绕过配额的路；正确做法是
 * 重新提交，走完整准入）。
 * 归入终态而不是 `runningStatuses`，否则任务中心会把它算进「进行中」，
 * 用户会等一个永远不会开始的任务。
 */
export const terminalStatuses: readonly TaskStatus[] = ['success', 'failure', 'timeout', 'canceled', 'rejected']

/**
 * 「结果异常」终态：执行没有产出可用结果，预览面板按错误态展示。
 *
 * `timeout`（超时）必须包含在内——否则超时任务在预览里会停留在「进行中」的骨架屏。
 * 与 `terminalStatuses` 的区别是排除 `success`（成功）和 `rejected`
 * （从未入队，没有执行过程可展示）。
 */
export const failureStatuses: readonly TaskStatus[] = ['failure', 'timeout', 'canceled']
const historyStatuses: readonly TaskStatus[] = terminalStatuses
const taskStatusSet = new Set<TaskStatus>([
  'pending',
  'rejected',
  'queued',
  'running',
  'success',
  'failure',
  'timeout',
  'canceled'
])

export function normalizeTaskStatus(status?: string): TaskStatus {
  const normalizedStatus = status?.toLowerCase()
  return taskStatusSet.has(normalizedStatus as TaskStatus)
    ? (normalizedStatus as TaskStatus)
    : 'pending'
}

export function getTaskStatusColor(status: TaskStatus): string {
  const colors: Record<TaskStatus, string> = {
    pending: 'orange',
    // 被拒用 `default`（灰）而不是 `error`（红）：红色留给「跑失败了」，
    // 被拒是「没让你跑」，语义上更接近取消，不该和失败同一个视觉权重。
    rejected: 'default',
    queued: 'blue',
    running: 'processing',
    success: 'success',
    failure: 'error',
    timeout: 'warning',
    canceled: 'default'
  }

  return colors[status]
}

export function getTaskStatusTextKey(status: TaskStatus): TaskStatusTextKey {
  const keys: Record<TaskStatus, TaskStatusTextKey> = {
    pending: 'tasks.statusPending',
    rejected: 'tasks.statusRejected',
    queued: 'tasks.statusQueued',
    running: 'tasks.statusRunning',
    success: 'tasks.statusSuccess',
    failure: 'tasks.statusFailure',
    timeout: 'tasks.statusTimeout',
    canceled: 'tasks.statusCanceled',
  }

  return keys[status]
}

export function getTaskProgressStatus(status: TaskStatus): TaskProgressStatus {
  if (status === 'running') return 'active'
  if (status === 'failure' || status === 'timeout') return 'exception'
  if (status === 'success') return 'success'
  // `rejected` 走 normal：进度条停在 0 是事实（它从未开始），
  // 标成 exception 会让人以为执行到一半炸了。
  return 'normal'
}

export function getTaskProgressColor(status: TaskStatus): string {
  if (status === 'running') return '#1890ff'
  if (status === 'failure' || status === 'timeout') return '#ff4d4f'
  // 被拒与取消一样用中性灰：绿色会让人以为「已完成」。
  if (status === 'rejected' || status === 'canceled') return '#8c8c8c'
  return '#52c41a'
}

export function isRunningTask(task: Pick<Task, 'status'>): boolean {
  return runningStatuses.includes(task.status)
}

/** 任务是否真的在执行（进度会前进、可看实时日志）。 */
export function isExecutingTask(task: Pick<Task, 'status'>): boolean {
  return task.status === 'running'
}

export function isHistoryTask(task: Pick<Task, 'status'>): boolean {
  return historyStatuses.includes(task.status)
}

/** 任务是否已进入终态（成功/失败/超时/已取消/被拒）。 */
export function isTerminalTask(task: Pick<Task, 'status'>): boolean {
  return terminalStatuses.includes(task.status)
}
