/**
 * 虚拟筛选漏斗（P-23 规则说明 / P-24 实际统计）的纯计算，便于单测。
 *
 * 结果页 `funnelFromRankedRows` 直接统计 Vina 1.1.0 输出里的真实阶段标记：
 *   `stage_pharmacophore` / `stage_docking` / `stage_cutoff` / `passes`。
 * 配置页不再做「预估掉队数字」，只展示真实执行规则。
 */

export type FunnelStageKey = 'input' | 'pharmacophore' | 'docking' | 'cutoff' | 'kept'

export interface FunnelStage {
  key: FunnelStageKey
  remaining: number
}

function isTruthyFlag(raw: string | undefined): boolean {
  const value = (raw ?? '').trim().toLowerCase()
  return value === 'true' || value === '1' || value === 'yes' || value === 't'
}

/**
 * 从 ranked 行真实统计漏斗：input = 行数；pharmacophore/docking/cutoff/kept =
 * 对应布尔列取 true 的行数。
 */
export function funnelFromRankedRows(rows: Array<Record<string, string>>): FunnelStage[] {
  const total = rows.length
  const afterPharmacophore = rows.filter(row => isTruthyFlag(row.stage_pharmacophore)).length
  const afterDocking = rows.filter(row => isTruthyFlag(row.stage_docking)).length
  const afterCutoff = rows.filter(row => isTruthyFlag(row.stage_cutoff)).length
  const kept = rows.filter(row => isTruthyFlag(row.passes)).length

  return [
    { key: 'input', remaining: total },
    { key: 'pharmacophore', remaining: afterPharmacophore },
    { key: 'docking', remaining: afterDocking },
    { key: 'cutoff', remaining: afterCutoff },
    { key: 'kept', remaining: kept }
  ]
}

/** 统计 passes 为真的行数（最终保留数量）。 */
export function countPasses(rows: Array<Record<string, string>>): number {
  return rows.filter(row => isTruthyFlag(row.passes)).length
}
