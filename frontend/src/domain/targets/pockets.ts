/**
 * 口袋（pocket）域计算。
 *
 * 页面只做编排，排序/选定/格式化/评分分档全部收敛在这里，
 * 便于单测覆盖并保证 P-09 / P-10 / P-11 的口径一致。
 */
import type { AxisVector, PocketSummary } from '@/types/targets'

/** 口袋评分强度分档。 */
export type PocketScoreTone = 'strong' | 'medium' | 'weak'

/** 缺少数值时的占位符。 */
export const POCKET_PLACEHOLDER = '-'

function toComparableScore(score: number | null | undefined): number {
  return typeof score === 'number' && Number.isFinite(score) ? score : Number.NEGATIVE_INFINITY
}

/**
 * 按 `score` 降序排序（不修改入参）。
 *
 * `score` 为 null/非有限值视作最低分排到末尾；同分时保持后端给的 `rank` 次序。
 */
export function sortPocketsByScore(pockets: readonly PocketSummary[]): PocketSummary[] {
  return [...pockets].sort((left, right) => {
    const leftScore = toComparableScore(left.score)
    const rightScore = toComparableScore(right.score)
    if (leftScore !== rightScore) {
      // 分数缺失（-Infinity）统一排到末尾；其余按数值降序。
      return rightScore > leftScore ? 1 : -1
    }
    const leftRank = typeof left.rank === 'number' ? left.rank : Number.MAX_SAFE_INTEGER
    const rightRank = typeof right.rank === 'number' ? right.rank : Number.MAX_SAFE_INTEGER
    return leftRank - rightRank
  })
}

/**
 * 返回唯一选定的口袋。
 *
 * 后端保证 `selected` 至多一个为 true，但为防御脏数据，出现多个时返回 null，
 * 由页面提示用户重新选定，而不是随意挑一个。
 */
export function findSelectedPocket(pockets: readonly PocketSummary[]): PocketSummary | null {
  const selected = pockets.filter((pocket) => pocket.selected)
  return selected.length === 1 ? (selected[0] ?? null) : null
}

function formatAxis(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(3) : POCKET_PLACEHOLDER
}

/** 把 `center` 坐标格式化成三位小数的 `x, y, z`；任一分量缺失用 `-` 占位。 */
export function formatPocketCenter(center: AxisVector | null | undefined): string {
  if (!center) {
    return POCKET_PLACEHOLDER
  }

  const parts = [center.x, center.y, center.z]
  if (parts.every((value) => typeof value !== 'number' || !Number.isFinite(value))) {
    return POCKET_PLACEHOLDER
  }

  return parts.map(formatAxis).join(', ')
}

/**
 * 口袋评分分档阈值（结合自由能口径，单位 kcal/mol，越负越强）。
 *
 * ⚠️ 阈值待 LVpocket 输出契约确认：`docs/05` §5.2 的示例 score 是正值（18.42），
 * 若后端最终确认是正值体系（越大越好），这三个阈值需整体反转，`pocketScoreTone`
 * 的比较方向也要同步改。此处不预先定案，只把口径集中到具名常量。
 */
export const POCKET_SCORE_STRONG_THRESHOLD = -8
export const POCKET_SCORE_MEDIUM_THRESHOLD = -6

/** 按 `<= -8` / `<= -6` / 其他 分成 strong / medium / weak 三档。 */
export function pocketScoreTone(score: number | null | undefined): PocketScoreTone {
  if (typeof score !== 'number' || !Number.isFinite(score)) {
    return 'weak'
  }
  if (score <= POCKET_SCORE_STRONG_THRESHOLD) {
    return 'strong'
  }
  if (score <= POCKET_SCORE_MEDIUM_THRESHOLD) {
    return 'medium'
  }
  return 'weak'
}

/** 评分数值的展示文案（两位小数，缺失用占位符）。 */
export function formatPocketScore(score: number | null | undefined): string {
  return typeof score === 'number' && Number.isFinite(score) ? score.toFixed(2) : POCKET_PLACEHOLDER
}

/** 体积的展示文案（两位小数，缺失用占位符）。 */
export function formatPocketVolume(volume: number | null | undefined): string {
  return typeof volume === 'number' && Number.isFinite(volume)
    ? volume.toFixed(2)
    : POCKET_PLACEHOLDER
}

/** 残基贡献值的展示文案（三位小数，缺失用占位符）。 */
export function formatResidueContribution(contribution: number | null | undefined): string {
  return typeof contribution === 'number' && Number.isFinite(contribution)
    ? contribution.toFixed(3)
    : POCKET_PLACEHOLDER
}
