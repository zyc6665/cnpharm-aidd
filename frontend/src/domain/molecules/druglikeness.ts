/**
 * 类药性评估（Lipinski 五规则 + QED）。
 *
 * 结果表里的理化性质是字符串单元格，页面把它们转成数字后交给这里：
 * - `evaluateLipinski` 给出每条规则的取值、上限、是否越界，供雷达图与明细列表共用；
 * - `druglikenessStars` 给出 1~5 星摘要：有 QED 时按 QED 映射，没有 QED 时按越界条数回退。
 *
 * 这里不依赖 i18n：规则文案由组件按 `design.results.druglikeness.rules.<id>` 取名，
 * 保证同一套判定在结果卡片、详情面板和单测里口径一致。
 */

export interface LipinskiProperties {
  mw: number | null
  logp: number | null
  hbd: number | null
  hba: number | null
  tpsa: number | null
  qed: number | null
}

export type LipinskiRuleId = 'mw' | 'logp' | 'hbd' | 'hba' | 'tpsa'

export interface LipinskiRuleDefinition {
  id: LipinskiRuleId
  /** 规则上限（含等于，即 value <= limit）。 */
  limit: number
}

export interface LipinskiRuleResult extends LipinskiRuleDefinition {
  value: number | null
  /** 取值是否满足规则；缺值时返回 null（未知，不算越界）。 */
  passed: boolean | null
  /** 归一化到 [0,1] 的比例，用于雷达图顶点；缺值为 0。 */
  ratio: number
}

/** Lipinski 五规则的上限口径（TPSA 为常用的 140 Å² 扩展阈值）。 */
export const LIPINSKI_RULES: readonly LipinskiRuleDefinition[] = [
  { id: 'mw', limit: 500 },
  { id: 'logp', limit: 5 },
  { id: 'hbd', limit: 5 },
  { id: 'hba', limit: 10 },
  { id: 'tpsa', limit: 140 },
]

export function emptyLipinskiProperties(): LipinskiProperties {
  return { mw: null, logp: null, hbd: null, hba: null, tpsa: null, qed: null }
}

function finiteOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(1, Math.max(0, value))
}

export function evaluateLipinski(
  properties: LipinskiProperties | null | undefined
): LipinskiRuleResult[] {
  return LIPINSKI_RULES.map(rule => {
    const value = finiteOrNull(properties?.[rule.id])
    return {
      ...rule,
      value,
      passed: value === null ? null : value <= rule.limit,
      ratio: value === null ? 0 : clamp01(value / rule.limit),
    }
  })
}

/** 越界条数；缺值不计入越界。 */
export function countLipinskiViolations(
  properties: LipinskiProperties | null | undefined
): number {
  return evaluateLipinski(properties).filter(rule => rule.passed === false).length
}

/** Classic Lipinski Rule-of-Five violations; null means all four inputs are missing. */
export function countRo5Violations(
  properties: LipinskiProperties | null | undefined
): number | null {
  const values = [
    finiteOrNull(properties?.mw),
    finiteOrNull(properties?.logp),
    finiteOrNull(properties?.hbd),
    finiteOrNull(properties?.hba),
  ]
  if (values.every(value => value === null)) return null
  const limits = [500, 5, 5, 10]
  return values.reduce<number>(
    (count, value, index) => count + (value !== null && value > (limits[index] ?? 0) ? 1 : 0),
    0
  )
}

export function hasLipinskiData(properties: LipinskiProperties | null | undefined): boolean {
  return evaluateLipinski(properties).some(rule => rule.value !== null)
}

/**
 * 1~5 星类药性摘要。
 *
 * 有 QED 时按 `round(qed * 5)` 映射（QED 0.8 以上基本是 4~5 星）；
 * 没有 QED 时用「5 - 越界条数」近似。完全没有任何性质数据时返回 null，
 * 让页面显示「暂无数据」而不是伪造一个 3 星。
 */
export function druglikenessStars(
  properties: LipinskiProperties | null | undefined
): number | null {
  const qed = finiteOrNull(properties?.qed)
  if (qed !== null) {
    return Math.min(5, Math.max(1, Math.round(qed * 5)))
  }
  if (!hasLipinskiData(properties)) {
    return null
  }
  return Math.min(5, Math.max(1, 5 - countLipinskiViolations(properties)))
}

/* -------------------------------------------------------------------------- */
/* 阈值语义着色（结果表格 / 详情 / 对比抽屉共用同一套口径）                    */
/* -------------------------------------------------------------------------- */

/** 单元格语义色：good=绿、warn=琥珀、bad=红；未知列或缺失值返回 null（中性展示）。 */
export type MetricTone = 'good' | 'warn' | 'bad'

/** 目前有公认阈值的理化/类药性指标。 */
export type MetricKind =
  | 'mw'
  | 'logp'
  | 'hbd'
  | 'hba'
  | 'tpsa'
  | 'qed'
  | 'violations'
  | 'rotatable'

interface MetricThresholdRule {
  kind: MetricKind
  /** 列 key 或标题是否命中该指标（大小写不敏感，允许中文列名）。 */
  matches: (raw: string, normalized: string) => boolean
  /** 给定数值返回语义色；「接近上限」给 warn，明显越界才给 bad。 */
  tone: (value: number) => MetricTone
}

function upperBoundTone(value: number, good: number, warn: number): MetricTone {
  if (value <= good) return 'good'
  if (value <= warn) return 'warn'
  return 'bad'
}

/**
 * 规则顺序即匹配优先级：`violations` / `rotatable` 等复合名先匹配，
 * 短名（`mw`）放最后，避免把 `molecular_weight` 之类误判。
 */
const METRIC_THRESHOLD_RULES: readonly MetricThresholdRule[] = [
  {
    kind: 'violations',
    matches: (_raw, n) => n.includes('violation'),
    tone: value => upperBoundTone(value, 0, 1),
  },
  {
    kind: 'rotatable',
    matches: (_raw, n) =>
      n.includes('rotatable') || n.includes('rotbonds') || n.includes('rotors'),
    tone: value => upperBoundTone(value, 10, 12),
  },
  {
    kind: 'qed',
    matches: (_raw, n) => n.includes('qed'),
    tone: value => (value >= 0.5 ? 'good' : value >= 0.35 ? 'warn' : 'bad'),
  },
  {
    kind: 'tpsa',
    matches: (raw, n) => n.includes('tpsa') || raw.includes('极性表面积'),
    tone: value => upperBoundTone(value, 140, 160),
  },
  {
    kind: 'logp',
    matches: (raw, n) => n.includes('logp') || raw.includes('脂水'),
    tone: value => upperBoundTone(value, 5, 6),
  },
  {
    kind: 'hbd',
    matches: (raw, n) => n.startsWith('hbd') || n.includes('donor') || raw.includes('氢键供体'),
    tone: value => upperBoundTone(value, 5, 7),
  },
  {
    kind: 'hba',
    matches: (raw, n) => n.startsWith('hba') || n.includes('acceptor') || raw.includes('氢键受体'),
    tone: value => upperBoundTone(value, 10, 12),
  },
  {
    kind: 'mw',
    matches: (raw, n) =>
      n.startsWith('mw') ||
      n.includes('molecularweight') ||
      n.includes('molweight') ||
      raw.includes('分子量'),
    tone: value => upperBoundTone(value, 500, 600),
  },
]

/** 解析列 key/标题属于哪个指标；未知列返回 null（不强行着色）。 */
export function metricKind(columnKey: string | null | undefined): MetricKind | null {
  const raw = (columnKey ?? '').trim().toLowerCase()
  if (!raw) return null
  const normalized = raw.replace(/[^a-z0-9]+/g, '')
  const rule = METRIC_THRESHOLD_RULES.find(item => item.matches(raw, normalized))
  return rule?.kind ?? null
}

/**
 * 按列名与取值判定语义色。
 *
 * - 缺失值（null / 空串 / `-` / 非数字）返回 null，绝不把「未计算」染成红色；
 * - 未知列（如 docking score）返回 null，由页面决定是否自行着色。
 */
export function classifyMetricTone(
  columnKey: string | null | undefined,
  value: number | string | null | undefined
): MetricTone | null {
  const kind = metricKind(columnKey)
  if (!kind) return null
  const numeric = finiteOrNull(value)
  if (numeric === null) return null
  const rule = METRIC_THRESHOLD_RULES.find(item => item.kind === kind)
  return rule ? rule.tone(numeric) : null
}
