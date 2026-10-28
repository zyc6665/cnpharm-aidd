/**
 * 虚拟筛选漏斗（P-23 预览 / P-24 实际统计）的纯计算，便于单测。
 *
 * P-23（配置页）用 `estimateFunnel`：根据「输入配体数 + 阈值」做确定性预估，
 *   每个参数都真实参与计算，页面不写死任何掉队数字。
 * P-24（结果页）用 `funnelFromRankedRows`：直接统计 ranked 里
 *   `stage_pharmacophore` / `stage_docking` / `stage_rescore` 三个布尔列的真实通过数。
 */

export type FunnelStageKey = 'input' | 'pharmacophore' | 'docking' | 'rescore'

export interface FunnelStage {
  key: FunnelStageKey
  remaining: number
}

export interface FunnelEstimateInput {
  ligandCount: number
  pharmacophoreMinFeatures: number
  dockingScoreCutoff: number
  exhaustiveness: number
  topN: number
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/**
 * 药效团层通过率：药效团最大特征数按 6 计，每多要求 1 个特征通过率下降 15 个百分点。
 * 最小特征数 3（默认）→ 70% 通过；5 → 40%。
 */
export function pharmacophorePassRate(minFeatures: number): number {
  return clamp(1 - (minFeatures - 1) * 0.15, 0.05, 1)
}

/**
 * 对接层通过率：阈值越负越严格。-4 kcal/mol 最宽松（≈95%），-12 最严格（≈5%），线性插值。
 * 默认 -8 → 50%。
 */
export function dockingPassRate(cutoff: number): number {
  return clamp(0.95 + 0.1125 * (cutoff + 4), 0.02, 0.98)
}

/**
 * 穷举度修正：exhaustiveness 以 8 为基准，采样越充分对接成功率略升，30 封顶。
 * 8 → 0.94；1 → 0.73；32 → 1.0。
 */
export function exhaustivenessFactor(exhaustiveness: number): number {
  return clamp(0.7 + exhaustiveness * 0.03, 0.55, 1)
}

/** 依据输入配体数与阈值计算每层预计剩余数量。 */
export function estimateFunnel(input: FunnelEstimateInput): FunnelStage[] {
  const total = Math.max(0, Math.floor(input.ligandCount))

  const afterPharmacophore = Math.round(
    total * pharmacophorePassRate(input.pharmacophoreMinFeatures)
  )

  const dockingRate = clamp(
    dockingPassRate(input.dockingScoreCutoff) * exhaustivenessFactor(input.exhaustiveness),
    0.02,
    0.98
  )
  const afterDocking = Math.round(afterPharmacophore * dockingRate)

  const topN = Math.max(0, Math.floor(input.topN))
  const afterRescore = Math.min(afterDocking, topN)

  return [
    { key: 'input', remaining: total },
    { key: 'pharmacophore', remaining: afterPharmacophore },
    { key: 'docking', remaining: afterDocking },
    { key: 'rescore', remaining: afterRescore }
  ]
}

function isTruthyFlag(raw: string | undefined): boolean {
  const value = (raw ?? '').trim().toLowerCase()
  return value === 'true' || value === '1' || value === 'yes' || value === 't'
}

/**
 * 从 ranked 行真实统计漏斗：input = 行数；pharmacophore/docking/rescore =
 * 对应布尔列取 true 的行数。
 */
export function funnelFromRankedRows(rows: Array<Record<string, string>>): FunnelStage[] {
  const total = rows.length
  const afterPharmacophore = rows.filter(row => isTruthyFlag(row.stage_pharmacophore)).length
  const afterDocking = rows.filter(row => isTruthyFlag(row.stage_docking)).length
  const afterRescore = rows.filter(row => isTruthyFlag(row.stage_rescore)).length

  return [
    { key: 'input', remaining: total },
    { key: 'pharmacophore', remaining: afterPharmacophore },
    { key: 'docking', remaining: afterDocking },
    { key: 'rescore', remaining: afterRescore }
  ]
}

/** 统计 passes 为真的行数（最终保留数量）。 */
export function countPasses(rows: Array<Record<string, string>>): number {
  return rows.filter(row => isTruthyFlag(row.passes)).length
}
