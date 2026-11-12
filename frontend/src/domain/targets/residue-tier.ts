import type { PocketResidueTier } from '@/types/targets'

/**
 * 残基分级的展示口径。
 *
 * 分级由后端从 `contribution` 派生（`pocket_residue_scoring.tier_for`），
 * 前端只负责翻译成中文与颜色——**不要在界面上重新算阈值**，
 * 否则同一份数据在结果页和成果页可能落进不同分级。
 */
export function tierLabel(tier: PocketResidueTier | null | undefined): string {
  if (tier === 'core') return '核心残基'
  if (tier === 'key') return '关键残基'
  if (tier === 'peripheral') return '外围残基'
  return '未评分'
}

export function tierTagColor(tier: PocketResidueTier | null | undefined): string {
  if (tier === 'core') return 'orange'
  if (tier === 'key') return 'gold'
  return 'default'
}
