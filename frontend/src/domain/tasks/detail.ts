import { formatDateTimeSeconds, parseServerDate } from '@/utils/datetime'
import type { Task, TaskStatus } from '@/types/models'

export type TaskCompletedTitleKey =
  | 'tasks.completed'
  | 'tasks.failed'
  | 'tasks.timedOut'
  | 'tasks.canceled'

export interface TaskFailureDiagnostics {
  errorMessage: string
  stdout: string
  stderr: string
  standardArtifactMessage: string
  hasDetails: boolean
}

const MAX_FAILURE_STREAM_LENGTH = 4000

const STANDARD_ARTIFACT_ERROR_PATTERNS = [
  /required standard artifacts/i,
  /standard artifacts?[^\n]*(missing|required)/i,
  /missing required output artifact/i,
  /result manifest/i,
  /standard artifact persistence/i,
]

export function getTaskCompletedTitleKey(status: TaskStatus): TaskCompletedTitleKey {
  if (status === 'failure') return 'tasks.failed'
  if (status === 'timeout') return 'tasks.timedOut'
  if (status === 'canceled') return 'tasks.canceled'
  return 'tasks.completed'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function normalizeDiagnosticText(value: unknown): string {
  if (typeof value !== 'string') {
    return ''
  }

  const trimmed = value.trim()
  if (trimmed.length <= MAX_FAILURE_STREAM_LENGTH) {
    return trimmed
  }

  return `${trimmed.slice(0, MAX_FAILURE_STREAM_LENGTH)}...`
}

function readDiagnosticField(source: unknown, key: 'stdout' | 'stderr', depth = 0): string {
  if (!isRecord(source) || depth > 2) {
    return ''
  }

  const direct = normalizeDiagnosticText(source[key])
  if (direct) {
    return direct
  }

  const fromDetails = readDiagnosticField(source.details, key, depth + 1)
  if (fromDetails) {
    return fromDetails
  }

  return readDiagnosticField(source.result, key, depth + 1)
}

function findStandardArtifactMessage(messages: string[]): string {
  return (
    messages.find(message =>
      message && STANDARD_ARTIFACT_ERROR_PATTERNS.some(pattern => pattern.test(message))
    ) ?? ''
  )
}

export function buildTaskFailureDiagnostics(
  task:
    | Pick<Task, 'error_message' | 'failure_diagnostics' | 'outputs' | 'output_data'>
    | null
    | undefined
): TaskFailureDiagnostics {
  const serverDiagnostics = task?.failure_diagnostics
  if (serverDiagnostics) {
    const errorMessage = normalizeDiagnosticText(serverDiagnostics.error_message)
    const stdout = normalizeDiagnosticText(serverDiagnostics.stdout)
    const stderr = normalizeDiagnosticText(serverDiagnostics.stderr)
    const standardArtifactMessage =
      normalizeDiagnosticText(serverDiagnostics.standard_artifact_message) ||
      findStandardArtifactMessage([errorMessage, stderr, stdout])

    return {
      errorMessage,
      stdout,
      stderr,
      standardArtifactMessage,
      hasDetails: Boolean(errorMessage || stdout || stderr || standardArtifactMessage),
    }
  }

  const errorMessage = normalizeDiagnosticText(task?.error_message)
  const sources = [task?.outputs?.result, task?.output_data]
  const stdout = sources.map(source => readDiagnosticField(source, 'stdout')).find(Boolean) ?? ''
  const stderr = sources.map(source => readDiagnosticField(source, 'stderr')).find(Boolean) ?? ''
  const standardArtifactMessage = findStandardArtifactMessage([errorMessage, stderr, stdout])

  return {
    errorMessage,
    stdout,
    stderr,
    standardArtifactMessage,
    hasDetails: Boolean(errorMessage || stdout || stderr || standardArtifactMessage),
  }
}

export function formatTaskDetailTime(time: string): string {
  return formatDateTimeSeconds(time)
}

/**
 * 运行时长。
 *
 * 起止时间都过 `parseServerDate`：后端返回的是「不带时区的 UTC」，
 * 直接 `dayjs(...)` 会按本地时区解释。两端都错 8 小时看似能抵消，
 * 但 `nowTime` 缺省时用的是本机真实时间，一端错一端对，差值就偏 8 小时。
 */
export function formatTaskRunningDuration(startTime: string, nowTime?: string | Date): string {
  const start = parseServerDate(startTime)
  if (!start) {
    return '-'
  }

  const now = nowTime ? parseServerDate(nowTime instanceof Date ? nowTime.toISOString() : nowTime) : new Date()
  if (!now) {
    return '-'
  }

  const diff = Math.max(0, Math.floor((now.getTime() - start.getTime()) / 1000))

  if (diff < 60) {
    return `${diff}s`
  }

  if (diff < 3600) {
    return `${Math.floor(diff / 60)}m ${diff % 60}s`
  }

  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`
}

export function formatTaskFileSize(bytes?: number): string {
  if (!bytes || bytes === 0) {
    return '0 B'
  }

  const unit = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(unit)), sizes.length - 1)
  return `${parseFloat((bytes / Math.pow(unit, index)).toFixed(2))} ${sizes[index]}`
}
