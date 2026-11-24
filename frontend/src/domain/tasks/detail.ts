import { formatDateTimeSeconds, parseServerDate } from '@/utils/datetime'
import type { Task, TaskStatus } from '@/types/models'
import { formatBytes } from '@/domain/common/format'

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
  // 任务产物文件大小：缺省按 0 字节显示（不是「无值」），其余交给共用原语，
  // 保证与资产页、产物页的 KB/MB/GB 口径一致。
  return formatBytes(bytes ?? 0)
}

/* ------------------------------------------------------------------ */
/* 排队信息                                                            */
/* ------------------------------------------------------------------ */

export interface TaskQueueInfo {
  queue: string | null
  queuePosition: number | null
  estimatedWaitSeconds: number | null
}

function readFiniteNumber(source: unknown, keys: string[]): number | null {
  if (!isRecord(source)) return null
  for (const key of keys) {
    const raw = source[key]
    const parsed = typeof raw === 'number' ? raw : Number(raw)
    if (raw !== null && raw !== undefined && raw !== '' && Number.isFinite(parsed)) {
      return Math.max(0, parsed)
    }
  }
  return null
}

function readString(source: unknown, keys: string[]): string | null {
  if (!isRecord(source)) return null
  for (const key of keys) {
    const raw = source[key]
    if (typeof raw === 'string' && raw.trim()) return raw.trim()
  }
  return null
}

/**
 * 排队位置与预计等待时间。
 *
 * 后端目前不保证这些字段存在（`dispatch` / `resource_wait` 的扩展字段），
 * 所以按「有则显示、无则优雅降级」读取：字段可能在 dispatch、resource_wait
 * 或任务根对象上，命名也存在 camel/snake 两种历史口径。
 */
export function readTaskQueueInfo(task: unknown): TaskQueueInfo {
  const record = isRecord(task) ? task : null
  const dispatch = record && isRecord(record.dispatch) ? record.dispatch : null
  const resourceWait = record && isRecord(record.resource_wait) ? record.resource_wait : null

  return {
    queue:
      readString(dispatch, ['queue', 'queue_name']) ??
      readString(resourceWait, ['queue', 'queue_name']),
    queuePosition:
      readFiniteNumber(dispatch, ['queue_position', 'queuePosition', 'position', 'queue_index']) ??
      readFiniteNumber(resourceWait, ['queue_position', 'queuePosition', 'position']) ??
      readFiniteNumber(record, ['queue_position', 'queuePosition']),
    estimatedWaitSeconds:
      readFiniteNumber(dispatch, [
        'estimated_wait_seconds',
        'estimatedWaitSeconds',
        'eta_seconds',
        'estimated_seconds',
      ]) ??
      readFiniteNumber(resourceWait, [
        'estimated_wait_seconds',
        'estimatedWaitSeconds',
        'eta_seconds',
      ]) ??
      readFiniteNumber(record, ['estimated_wait_seconds', 'estimatedWaitSeconds']),
  }
}

/** 秒数 → 紧凑可读文本（与页面语言无关，由外层拼接文案）。 */
export function formatWaitSeconds(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return ''
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.round((seconds % 3600) / 60)
  return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`
}

/* ------------------------------------------------------------------ */
/* 运行中进度细节                                                      */
/* ------------------------------------------------------------------ */

export interface TaskProgressDetail {
  generated: number | null
  total: number | null
  bestScore: number | null
  /** 已解析过的原始进度文本，便于页面在无结构化字段时直接展示。 */
  text: string | null
}

function stringifyProgressSource(value: unknown): string {
  if (typeof value === 'string') return value
  if (!value || typeof value !== 'object') return ''
  try {
    return JSON.stringify(value)
  } catch {
    return ''
  }
}

function readProgressNumber(source: unknown, keys: string[]): number | null {
  if (!isRecord(source)) return null
  for (const key of keys) {
    const raw = source[key]
    const parsed = typeof raw === 'number' ? raw : Number(raw)
    if (raw !== null && raw !== undefined && raw !== '' && Number.isFinite(parsed)) {
      return parsed
    }
  }
  return null
}

/**
 * 解析「已生成 X / Y、最佳评分」这类中间进度。
 *
 * 生成类工具的进度文本五花八门（`Generated 32/100`、`已生成 32/100 个分子`、
 * `best score: 0.72`），这里只做保守提取：解析不到就返回 null，页面回退到
 * 原来的进度条 + `progress_message`，不会因为格式不认识而报错。
 */
export function parseTaskProgressDetail(
  task:
    | Pick<Task, 'progress_message' | 'outputs' | 'output_data'>
    | null
    | undefined
): TaskProgressDetail {
  const text = typeof task?.progress_message === 'string' && task.progress_message.trim()
    ? task.progress_message.trim()
    : null

  const structuredSources = [task?.output_data, task?.outputs?.result]
  let generated: number | null = null
  let total: number | null = null
  let bestScore: number | null = null

  for (const source of structuredSources) {
    generated ??= readProgressNumber(source, [
      'generated',
      'generated_count',
      'num_generated',
      'completed',
      'current',
    ])
    total ??= readProgressNumber(source, ['total', 'num_samples', 'requested', 'target'])
    bestScore ??= readProgressNumber(source, ['best_score', 'bestScore', 'top_score'])
  }

  if (text) {
    const pair = text.match(/(\d+)\s*\/\s*(\d+)/)
    if (pair) {
      generated ??= Number(pair[1])
      total ??= Number(pair[2])
    } else {
      const generatedOnly = text.match(/(?:generated|completed|已生成|已完成)\D{0,6}(\d+)/i)
      if (generatedOnly) generated ??= Number(generatedOnly[1])
      const totalOnly = text.match(/(?:total|of|共|目标)\D{0,6}(\d+)/i)
      if (totalOnly) total ??= Number(totalOnly[1])
    }

    const score = text.match(/(?:best|top)[ _-]?score\s*[:=]?\s*(-?\d+(?:\.\d+)?)/i)
      ?? text.match(/(?:最佳|最高)(?:评分|分数|得分)?\s*[:=]?\s*(-?\d+(?:\.\d+)?)/)
    if (score) bestScore ??= Number(score[1])
  }

  // 结构化字段缺失时再扫一眼 output_data 的文本化结果，容忍嵌套 JSON。
  if (generated === null || total === null || bestScore === null) {
    const haystack = stringifyProgressSource(task?.output_data)
    if (haystack) {
      const pair = haystack.match(/(\d+)\s*\/\s*(\d+)/)
      if (pair && generated === null && total === null) {
        generated = Number(pair[1])
        total = Number(pair[2])
      }
    }
  }

  return {
    generated: Number.isFinite(generated) ? generated : null,
    total: Number.isFinite(total) ? total : null,
    bestScore: Number.isFinite(bestScore) ? bestScore : null,
    text,
  }
}

/* ------------------------------------------------------------------ */
/* 失败原因与重试建议                                                  */
/* ------------------------------------------------------------------ */

export type TaskFailureCauseId =
  | 'pocket_too_small'
  | 'invalid_protein'
  | 'gpu_oom'
  | 'timeout'
  | 'missing_artifact'
  | 'input_missing'
  | 'unknown'

export interface TaskFailureAdvice {
  cause: TaskFailureCauseId
  /** i18n key：一句话原因。 */
  messageKey: string
  /** i18n key：可执行的修复建议。 */
  suggestionKey: string
  /** i18n key：重试策略说明。 */
  retryKey: string
  /** 建议带上的参数（分子生成等页面可预填）。 */
  suggestedParams: Record<string, number> | null
  /** 是否适合「调整参数后重试」，而不是原样重试。 */
  canAdjustParams: boolean
}

const ADVICE_BY_CAUSE: Record<TaskFailureCauseId, Omit<TaskFailureAdvice, 'cause'>> = {
  pocket_too_small: {
    messageKey: 'tasks.failureAdvice.causes.pocketTooSmall',
    suggestionKey: 'tasks.failureAdvice.suggestions.pocketTooSmall',
    retryKey: 'tasks.failureAdvice.retry.pocketTooSmall',
    suggestedParams: { pocket_radius: 12 },
    canAdjustParams: true,
  },
  invalid_protein: {
    messageKey: 'tasks.failureAdvice.causes.invalidProtein',
    suggestionKey: 'tasks.failureAdvice.suggestions.invalidProtein',
    retryKey: 'tasks.failureAdvice.retry.invalidProtein',
    suggestedParams: null,
    canAdjustParams: false,
  },
  gpu_oom: {
    messageKey: 'tasks.failureAdvice.causes.gpuOom',
    suggestionKey: 'tasks.failureAdvice.suggestions.gpuOom',
    retryKey: 'tasks.failureAdvice.retry.gpuOom',
    suggestedParams: { num_samples: 20 },
    canAdjustParams: true,
  },
  timeout: {
    messageKey: 'tasks.failureAdvice.causes.timeout',
    suggestionKey: 'tasks.failureAdvice.suggestions.timeout',
    retryKey: 'tasks.failureAdvice.retry.timeout',
    suggestedParams: { num_samples: 20 },
    canAdjustParams: true,
  },
  missing_artifact: {
    messageKey: 'tasks.failureAdvice.causes.missingArtifact',
    suggestionKey: 'tasks.failureAdvice.suggestions.missingArtifact',
    retryKey: 'tasks.failureAdvice.retry.missingArtifact',
    suggestedParams: null,
    canAdjustParams: false,
  },
  input_missing: {
    messageKey: 'tasks.failureAdvice.causes.inputMissing',
    suggestionKey: 'tasks.failureAdvice.suggestions.inputMissing',
    retryKey: 'tasks.failureAdvice.retry.inputMissing',
    suggestedParams: null,
    canAdjustParams: false,
  },
  unknown: {
    messageKey: 'tasks.failureAdvice.causes.unknown',
    suggestionKey: 'tasks.failureAdvice.suggestions.unknown',
    retryKey: 'tasks.failureAdvice.retry.unknown',
    suggestedParams: null,
    canAdjustParams: false,
  },
}

const CAUSE_PATTERNS: Array<{ cause: TaskFailureCauseId; patterns: RegExp[] }> = [
  {
    cause: 'gpu_oom',
    patterns: [
      /out of memory/i,
      /cuda\s*error\s*:\s*out of memory/i,
      /\boom\b/i,
      /显存不足/,
      /内存不足/,
    ],
  },
  {
    cause: 'pocket_too_small',
    patterns: [
      /pocket[^\n]{0,40}(too small|smaller than|empty)/i,
      /no atoms[^\n]{0,30}pocket/i,
      /口袋[^\n]{0,20}(过小|太小|为空)/,
    ],
  },
  {
    cause: 'invalid_protein',
    patterns: [
      /invalid[^\n]{0,20}protein/i,
      /protein[^\n]{0,20}invalid/i,
      /invalid[^\n]{0,20}(pdb|structure)/i,
      /(结构|蛋白)[^\n]{0,20}(无效|解析失败)/,
    ],
  },
  {
    cause: 'input_missing',
    patterns: [
      /file not found/i,
      /no such file/i,
      /missing (input|file)/i,
      /(输入|文件)[^\n]{0,20}(缺失|不存在)/,
    ],
  },
]

function classifyFailureCause(text: string, diagnostics: TaskFailureDiagnostics): TaskFailureCauseId {
  if (diagnostics.standardArtifactMessage) return 'missing_artifact'
  for (const { cause, patterns } of CAUSE_PATTERNS) {
    if (patterns.some(pattern => pattern.test(text))) return cause
  }
  return 'unknown'
}

/**
 * 把错误码 / 文本 / stderr 归类成可读原因 + 修复建议 + 重试策略。
 *
 * 超时优先按任务状态判定（`timeout` 状态本身比日志里出现 "timeout" 更可信），
 * 其后按「GPU 显存 → 口袋过小 → 结构无效 → 输入缺失 → 标准产物缺失」的顺序匹配。
 */
export function buildTaskFailureAdvice(
  task:
    | Pick<Task, 'status' | 'error_message' | 'failure_diagnostics' | 'outputs' | 'output_data'>
    | null
    | undefined
): TaskFailureAdvice {
  let cause: TaskFailureCauseId

  if (task?.status === 'timeout') {
    cause = 'timeout'
  } else if (/timeout|timed out|超时/i.test(String(task?.error_message ?? ''))) {
    cause = 'timeout'
  } else {
    const diagnostics = buildTaskFailureDiagnostics(task)
    const haystack = [
      diagnostics.errorMessage,
      diagnostics.stderr,
      diagnostics.stdout,
      stringifyProgressSource(task?.output_data),
    ]
      .filter(Boolean)
      .join('\n')
    cause = classifyFailureCause(haystack, diagnostics)
  }

  return { cause, ...ADVICE_BY_CAUSE[cause] }
}
