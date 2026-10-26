import type { ComparisonPropertySource } from '@/types/compounds'

/** 7 项分子性质的固定展示顺序（docs/06 P-13 性质表）。 */
export type PropertyKey =
  | 'mol_weight'
  | 'logP'
  | 'TPSA'
  | 'HBD'
  | 'HBA'
  | 'RotB'
  | 'QED'

export interface PropertyColumn {
  key: PropertyKey
  /** i18n 键，页面用 `t(column.labelKey)` 渲染表头。 */
  labelKey: string
  digits: number
}

export const PROPERTY_COLUMNS: readonly PropertyColumn[] = [
  { key: 'mol_weight', labelKey: 'compounds.properties.molWeight', digits: 3 },
  { key: 'logP', labelKey: 'compounds.properties.logP', digits: 2 },
  { key: 'TPSA', labelKey: 'compounds.properties.tpsa', digits: 2 },
  { key: 'HBD', labelKey: 'compounds.properties.hbd', digits: 0 },
  { key: 'HBA', labelKey: 'compounds.properties.hba', digits: 0 },
  { key: 'RotB', labelKey: 'compounds.properties.rotB', digits: 0 },
  { key: 'QED', labelKey: 'compounds.properties.qed', digits: 3 }
]

const DIGITS_BY_KEY: Record<PropertyKey, number> = {
  mol_weight: 3,
  logP: 2,
  TPSA: 2,
  HBD: 0,
  HBA: 0,
  RotB: 0,
  QED: 3
}

/** 空值统一显示短横线，避免表格出现 `null`/`NaN`。 */
function formatNumber(value: number, digits: number): string {
  return value.toFixed(digits)
}

export function formatPropertyValue(
  key: PropertyKey,
  value: number | null | undefined
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '-'
  }

  return formatNumber(value, DIGITS_BY_KEY[key])
}

/**
 * 取候选物的某项性质。
 *
 * 对比接口把 7 项性质摊平到候选物顶层；候选物详情接口则把它们放在内联
 * `compound` 上（`mol_weight` 在 compound 顶层，其余在 `compound.props`）。
 * 两种形状都要支持，这里做一次归一。
 */
export function readPropertyValue(
  candidate: ComparisonPropertySource,
  key: PropertyKey
): number | null {
  const flat = candidate[key]
  if (typeof flat === 'number') {
    return flat
  }

  const compound = candidate.compound
  if (!compound) {
    return null
  }

  if (key === 'mol_weight') {
    return compound.mol_weight
  }

  const propertyValue = compound.props?.[key]
  return typeof propertyValue === 'number' ? propertyValue : null
}
