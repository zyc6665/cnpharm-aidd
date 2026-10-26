/**
 * 决策记录域（P-39）：纯函数层。
 *
 * 页面只做编排，业务判断全部下沉到这里——分组、计数、分页守卫、提交载荷组装、
 * 「未记录」的判定。所有对外文案一律返回 i18n key，由页面负责翻译，函数保持纯净。
 *
 * 与 `domain/targets` 同构：`index.ts` 只是 barrel，实现集中在本文件，便于单测覆盖。
 */
import {
  SCORE_SOURCE_MISSING,
  type DecisionCreateParams,
  type DecisionItem,
  type DecisionPoint,
  type DecisionRecord,
  type DecisionSnapshotInput,
  type DecisionSubjectType
} from '@/types/decisions'

/** 缺省占位符：与 targets/compounds 域一致。 */
export const PLACEHOLDER = '-'

/** 「未记录」的 i18n key：`snapshot_score` 缺失时页面显示这句，不能显示 `0` 或 `-`。 */
export const SNAPSHOT_NOT_RECORDED_KEY = 'decisions.snapshot.notRecorded'

/* ------------------------------------------------------------------ */
/* 决策点 / 对象类型 / 分页档位                                          */
/* ------------------------------------------------------------------ */

/** 决策点选项：`value` 是后端枚举，`labelKey` 是 i18n key（含义见 docs/03 §3.6.2）。 */
export interface DecisionPointOption {
  value: DecisionPoint
  labelKey: string
}

/** DP1~DP5；顺序即研发主线顺序（docs/03 §3.6.2 的 S1→S2 … S5→S6）。 */
export const DECISION_POINT_OPTIONS: readonly DecisionPointOption[] = [
  { value: 'DP1', labelKey: 'decisions.points.DP1' },
  { value: 'DP2', labelKey: 'decisions.points.DP2' },
  { value: 'DP3', labelKey: 'decisions.points.DP3' },
  { value: 'DP4', labelKey: 'decisions.points.DP4' },
  { value: 'DP5', labelKey: 'decisions.points.DP5' }
]

/** 决策对象类型选项。 */
export const DECISION_SUBJECT_TYPE_OPTIONS: readonly {
  value: DecisionSubjectType
  labelKey: string
}[] = [
  { value: 'TARGET', labelKey: 'decisions.subjectTypes.TARGET' },
  { value: 'POCKET', labelKey: 'decisions.subjectTypes.POCKET' },
  { value: 'CANDIDATE_SET', labelKey: 'decisions.subjectTypes.CANDIDATE_SET' },
  { value: 'STRUCTURE', labelKey: 'decisions.subjectTypes.STRUCTURE' }
]

/**
 * `page_size` 可选档位。
 *
 * 后端 `page_size: int = Query(20, ge=1, le=100)`——超过 100 直接 422，所以
 * 选择器里不能出现 200/500 这类档位；`clampDecisionPageSize` 再兜一次底。
 */
export const DECISION_PAGE_SIZE_OPTIONS: readonly number[] = [10, 20, 50, 100]

/** 默认页大小，与后端默认值一致。 */
export const DEFAULT_DECISION_PAGE_SIZE = 20

/** `page >= 1`；非法值（NaN/0/负数/小数）回落到 1。 */
export function clampDecisionPage(value: number): number {
  if (!Number.isFinite(value)) {
    return 1
  }
  const floored = Math.floor(value)
  return floored >= 1 ? floored : 1
}

/** `1 <= page_size <= 100`；越界值夹到边界，非法值回落到默认页大小。 */
export function clampDecisionPageSize(value: number): number {
  if (!Number.isFinite(value)) {
    return DEFAULT_DECISION_PAGE_SIZE
  }
  const floored = Math.floor(value)
  if (floored < 1) {
    return 1
  }
  return floored > 100 ? 100 : floored
}

/* ------------------------------------------------------------------ */
/* 快照行的展示                                                         */
/* ------------------------------------------------------------------ */

/**
 * 这一行快照当时是否**没录到分**。
 *
 * 两种形态都算缺失，缺一不可：
 *
 * 1. `snapshot_score === null` 且 `snapshot_attrs.score_source === 'missing'` ——
 *    后端为「结论里有、快照里没有」的成员补的占位行（`app.services.decisions`）。
 * 2. 只是 `snapshot_score === null` —— 前端提交时给每个成员都补了快照行（`score: null`），
 *    此时后端不再额外打 `score_source` 标记（只有整行缺失才打），但语义同样是「没录分」。
 *
 * `0` 是有效分数，不能落进这两条：只追加表里「当时 0 分」与「当时没录分」一旦混淆
 * 就再也分不开。
 */
export function isSnapshotScoreMissing(item: DecisionItem): boolean {
  if (item.snapshot_attrs?.score_source === SCORE_SOURCE_MISSING) {
    return true
  }
  return item.snapshot_score === null || item.snapshot_score === undefined
}

/** 数字分数格式化；`null`/`undefined`/非有限数回退占位符。 */
export function formatScoreNumber(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return PLACEHOLDER
  }
  // `Numeric(10, 4)`（docs/04 §9.5）最多四位小数；去掉无意义的尾零，避免 `0.8500`。
  return value.toFixed(4).replace(/\.?0+$/, '')
}

/** 快照分数展示：缺失 → 「未记录」的 key；有效分数 → 最多四位小数、不留尾零。 */
export function formatSnapshotScore(item: DecisionItem): string {
  if (isSnapshotScoreMissing(item)) {
    return SNAPSHOT_NOT_RECORDED_KEY
  }
  return formatScoreNumber(item.snapshot_score)
}

/** 快照排名展示；缺失显示占位符。 */
export function formatSnapshotRank(item: DecisionItem): string {
  const rank = item.snapshot_rank
  if (typeof rank !== 'number' || !Number.isFinite(rank)) {
    return PLACEHOLDER
  }
  return String(rank)
}

/** verdict 的 i18n key。 */
export function resolveVerdictKey(item: DecisionItem): string {
  return `decisions.verdicts.${item.verdict}`
}

/** 决策对象的展示信息：类型走 i18n key，对象 ID 原样透出（字段名由后端定）。 */
export interface DecisionSubjectLabel {
  typeKey: string
  subjectId: string
}

/** 决策对象标签：`{ typeKey: 'decisions.subjectTypes.POCKET', subjectId: 'pocket-9' }`。 */
export function resolveDecisionSubjectLabel(record: DecisionRecord): DecisionSubjectLabel {
  return {
    typeKey: `decisions.subjectTypes.${record.subject_type}`,
    subjectId: record.subject_id
  }
}

/** 决策点的 i18n key（DP1~DP5 的中文含义见 docs/03 §3.6.2）。 */
export function resolveDecisionPointKey(record: DecisionRecord): string {
  return `decisions.points.${record.decision_point}`
}

/** 决策时间的解析；无法解析返回 `null`。 */
export function toDecisionTimestamp(value: string | null | undefined): number | null {
  if (!value) {
    return null
  }
  const text = value.trim()
  if (!text) {
    return null
  }
  // 后端时间列是不带时区的 UTC（`backend/app/common/time.py`），补 `Z` 再解析。
  const normalized = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(text)
    ? `${text.replace(' ', 'T')}Z`
    : text
  const parsed = Date.parse(normalized)
  return Number.isNaN(parsed) ? null : parsed
}

/** `basis_metrics` 的 JSON 折叠展示；空对象给出占位符。 */
export function formatBasisMetrics(metrics: Record<string, unknown> | null | undefined): string {
  if (!metrics || Object.keys(metrics).length === 0) {
    return PLACEHOLDER
  }
  try {
    return JSON.stringify(metrics, null, 2)
  } catch {
    return PLACEHOLDER
  }
}

/**
 * 从请求异常里取用户可读的错误文案。
 *
 * 与 `domain/targets/display.ts` 的 `resolveTargetErrorMessage` 同构：axios 的原始
 * message 是 `Request failed with status code 422`，没有信息量；后端 `ApiResponse.message`
 * 才是真正的业务原因（如「决策理由不能为空」）。
 */
export function resolveDecisionErrorMessage(cause: unknown, fallback: string): string {
  const responseMessage = (cause as { response?: { data?: { message?: unknown } } })?.response?.data
    ?.message
  if (typeof responseMessage === 'string' && responseMessage.trim()) {
    return responseMessage.trim()
  }

  const message = (cause as { message?: unknown })?.message
  if (typeof message === 'string' && message.trim()) {
    return message.trim()
  }

  return fallback
}

/* ------------------------------------------------------------------ */
/* 分组与计数                                                           */
/* ------------------------------------------------------------------ */

/** 按决策点分组后的一组记录。 */
export interface DecisionPointGroup {
  point: DecisionPoint
  labelKey: string
  /** 组内记录，按决策时间倒序。 */
  records: DecisionRecord[]
}

/**
 * 按决策点分组，用于时间线渲染。
 *
 * 两份顺序都保证倒序：**组内**按 `decided_at` 降序（无有效时间戳的排最后，同级保持
 * 传入顺序），**组间**按组内最新一条的时间降序——时间线读起来就是「最近发生了什么」，
 * 而不是被决策点编号打散。
 */
export function groupDecisionsByPoint(records: readonly DecisionRecord[]): DecisionPointGroup[] {
  const buckets = new Map<DecisionPoint, DecisionRecord[]>()

  for (const record of records) {
    const bucket = buckets.get(record.decision_point)
    if (bucket) {
      bucket.push(record)
    } else {
      buckets.set(record.decision_point, [record])
    }
  }

  const groups: Array<DecisionPointGroup & { latest: number }> = []
  for (const [point, bucket] of buckets) {
    const sorted = bucket
      .map((record, index) => ({
        record,
        index,
        timestamp:
          toDecisionTimestamp(record.decided_at) ?? toDecisionTimestamp(record.created_at)
      }))
      .sort((left, right) => {
        if (left.timestamp === null && right.timestamp === null) {
          return left.index - right.index
        }
        if (left.timestamp === null) {
          return 1
        }
        if (right.timestamp === null) {
          return -1
        }
        return right.timestamp - left.timestamp
      })
      .map(entry => entry.record)

    groups.push({
      point,
      labelKey: `decisions.points.${point}`,
      records: sorted,
      latest: toDecisionTimestamp(sorted[0]?.decided_at) ?? Number.NEGATIVE_INFINITY
    })
  }

  return groups
    .sort((left, right) => right.latest - left.latest)
    .map(({ point, labelKey, records: groupRecords }) => ({
      point,
      labelKey,
      records: groupRecords
    }))
}

/** 入选/淘汰计数：`selected`/`excluded` 按成员累加，`total` 是记录条数。 */
export interface DecisionCounts {
  selected: number
  excluded: number
  total: number
}

/**
 * 统计入选与淘汰数量。
 *
 * 直接数 `items[].verdict`（成员快照是权威），而不是 `selected_ids.length`——
 * 两者本应一致，但快照才是决策当时的真相，页面不该在数据不一致时替后端挑一个。
 */
export function summarizeDecisionCounts(records: readonly DecisionRecord[]): DecisionCounts {
  let selected = 0
  let excluded = 0

  for (const record of records) {
    for (const item of record.items ?? []) {
      if (item.verdict === 'SELECTED') {
        selected += 1
      } else if (item.verdict === 'EXCLUDED') {
        excluded += 1
      }
    }
  }

  return { selected, excluded, total: records.length }
}

/** 单条记录里入选/淘汰的成员数，用于时间线卡片头。 */
export function summarizeRecordCounts(record: DecisionRecord): {
  selected: number
  excluded: number
} {
  const items = record.items ?? []
  return {
    selected: items.filter(item => item.verdict === 'SELECTED').length,
    excluded: items.filter(item => item.verdict === 'EXCLUDED').length
  }
}

/* ------------------------------------------------------------------ */
/* 新建决策：草稿 → 载荷                                                 */
/* ------------------------------------------------------------------ */

/** 新建决策抽屉的表单草稿：多值字段是逗号分隔的原始文本。 */
export interface DecisionDraft {
  decisionPoint: DecisionPoint
  subjectType: DecisionSubjectType
  subjectId: string
  reason: string
  selectedIdsText: string
  excludedIdsText: string
  basisTaskIdsText: string
  basisMetricsText?: string
}

/** 组装结果：成功给载荷，失败给 i18n key（页面直接 `t(errorKey)`）。 */
export type DecisionPayloadResult =
  | { ok: true; payload: DecisionCreateParams }
  | { ok: false; errorKey: string }

/** 逗号/顿号/空白分隔的 ID 文本 → 去重后的 ID 数组（保持输入顺序）。 */
export function parseIdList(text: string | null | undefined): string[] {
  if (!text) {
    return []
  }
  const parts = text
    .split(/[,，、\s]+/)
    .map(part => part.trim())
    .filter(part => part.length > 0)
  return Array.from(new Set(parts))
}

/**
 * `basis_metrics` 文本 → 对象。
 *
 * 留空 → `{}`（后端默认就是空 dict）；不是合法 JSON 或是数组/标量 → 也回落到 `{}`，
 * 不因为一个可选字段把整次提交废掉。
 */
export function parseBasisMetrics(text: string | null | undefined): Record<string, unknown> {
  const trimmed = (text ?? '').trim()
  if (!trimmed) {
    return {}
  }
  try {
    const parsed: unknown = JSON.parse(trimmed)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    return {}
  }
  return {}
}

/**
 * 把抽屉草稿组装成 `DecisionCreate` 载荷。
 *
 * 服务端（`app/schemas/decisions.py` 的 `validate_verdicts`）要求：理由非空白、
 * 入选与淘汰不能同时为空、同一候选物不能既入选又淘汰、快照不能为空且每行都在结论里。
 * 这里先在 UI 侧挡一遍，用户不必等一次 422 才知道「理由没填」。
 *
 * **快照的生成**：本次按结论自动生成 `score: null` 的行（不臆造分数）。后端会给缺分的
 * 成员补 `score_source = "missing"`，页面因此显示「未记录」——抽屉里也明确提示了这一点。
 */
export function buildDecisionCreatePayload(draft: DecisionDraft): DecisionPayloadResult {
  const subjectId = draft.subjectId.trim()
  if (!subjectId) {
    return { ok: false, errorKey: 'decisions.drawer.subjectRequired' }
  }

  const reason = draft.reason.trim()
  if (!reason) {
    return { ok: false, errorKey: 'decisions.drawer.reasonRequired' }
  }

  const selectedIds = parseIdList(draft.selectedIdsText)
  const excludedIds = parseIdList(draft.excludedIdsText)
  if (selectedIds.length === 0 && excludedIds.length === 0) {
    return { ok: false, errorKey: 'decisions.drawer.verdictRequired' }
  }

  const selected = new Set(selectedIds)
  if (excludedIds.some(id => selected.has(id))) {
    return { ok: false, errorKey: 'decisions.drawer.verdictDuplicated' }
  }

  const snapshot: DecisionSnapshotInput[] = [...selectedIds, ...excludedIds].map(candidateId => ({
    candidate_id: candidateId,
    score: null
  }))

  return {
    ok: true,
    payload: {
      decision_point: draft.decisionPoint,
      subject_type: draft.subjectType,
      subject_id: subjectId,
      selected_ids: selectedIds,
      excluded_ids: excludedIds,
      basis_task_ids: parseIdList(draft.basisTaskIdsText),
      basis_metrics: parseBasisMetrics(draft.basisMetricsText),
      reason,
      snapshot
    }
  }
}
