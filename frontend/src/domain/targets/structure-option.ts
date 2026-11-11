import { formatDateTimeMinutes, parseServerDate } from '@/utils/datetime'
import type { ProteinStructureDetail } from '@/types/targets'

/**
 * 结构下拉的显示文案。
 *
 * 同一蛋白经常有多个结构（重复预测、导入的复合物、准备后的结构），
 * 它们的 `id` 是 UUID，直接给用户看没有任何区分度。这里按「来源 · 模型 · pLDDT ·
 * 是否已准备 · 创建时间」拼一行，最后附 id 前 8 位，便于在日志与工单里对齐。
 */
const SOURCE_LABELS: Record<string, string> = {
  PREDICTED: '预测结构',
  IMPORTED: '导入结构',
  PREPARED: '准备结构'
}

export function structureOptionLabel(structure: ProteinStructureDetail): string {
  const parts: string[] = []
  const source = structure.source_type
    ? SOURCE_LABELS[structure.source_type] ?? structure.source_type
    : '结构'
  const model = structure.model?.name || structure.tool?.name || ''
  parts.push(model ? `${source} · ${model}` : source)
  if (typeof structure.plddt_mean === 'number' && Number.isFinite(structure.plddt_mean)) {
    parts.push(`pLDDT ${structure.plddt_mean.toFixed(1)}`)
  }
  if (structure.prepared_urn) {
    parts.push('已准备')
  }
  const created = formatDateTimeMinutes(structure.created_at)
  if (created) {
    parts.push(created)
  }
  return `${parts.join(' · ')}（${structure.id.slice(0, 8)}）`
}

/**
 * 按创建时间倒序，最新的排在最前。
 *
 * 「默认看最新」本身没错，错的是**只能**看最新：多结构时用户必须能切回去，
 * 否则早先那个结构上的口袋与残基就永远看不到（它们挂在旧结构 id 上）。
 */
export function sortStructuresByNewest(
  structures: ProteinStructureDetail[]
): ProteinStructureDetail[] {
  return [...structures].sort((left, right) => {
    const leftTime = parseServerDate(left.created_at)?.getTime() ?? 0
    const rightTime = parseServerDate(right.created_at)?.getTime() ?? 0
    if (leftTime === rightTime) return left.id.localeCompare(right.id)
    return rightTime - leftTime
  })
}
