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
