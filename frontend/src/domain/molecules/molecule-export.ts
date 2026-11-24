/**
 * 结果页的本地导出助手：CSV 与 SDF。
 *
 * - CSV 直接由当前结果表构造，保留表头顺序与所有列；
 * - SDF 仅复用可通过显式来源或唯一 SMILES 确认的原始记录；无法确认时不伪造结构。
 */

export interface CsvColumnDefinition {
  key: string
  title: string
}

export type CsvRowRecord = Record<string, string | undefined>

function csvCell(value: string | undefined): string {
  const raw = value ?? ''
  if (!/[",\r\n]/.test(raw)) return raw
  return `"${raw.replace(/"/g, '""')}"`
}

export function buildMoleculeCsv(
  columns: readonly CsvColumnDefinition[],
  rows: readonly CsvRowRecord[]
): string {
  const header = columns.map(column => csvCell(column.title)).join(',')
  const body = rows.map(row =>
    columns.map(column => csvCell(row[column.key])).join(',')
  )
  return [header, ...body].join('\r\n') + '\r\n'
}

function normalizeSmiles(value: string | undefined | null): string {
  return (value ?? '').replace(/\s+/g, '').trim()
}

/** 从 SDF 记录里读 `> <SMILES>` / `> <smiles>` 属性。 */
export function readSdfRecordSmiles(record: string): string {
  const match = record.match(/^>\s*<[^>\n]*smiles[^>\n]*>\s*\r?\n([^\r\n]+)/im)
  return normalizeSmiles(match?.[1] ?? '')
}

function ensureSdfDelimiter(record: string): string {
  const trimmed = record.trimEnd()
  return trimmed.endsWith('$$$$') ? `${trimmed}\n` : `${trimmed}\n$$$$\n`
}

export interface SdfExportRow {
  smiles: string
}

/**
 * 按选中行生成 SDF 文本。只按唯一 SMILES 属性匹配；不使用数组位置推断，
 * 因为结果行可能已排序，而 SDF 记录仍保持生产顺序。
 */
export function buildSdfExportText(
  records: readonly string[],
  rows: readonly SdfExportRow[]
): string {
  const indexed = new Map<string, number[]>()
  records.forEach((record, index) => {
    const smiles = readSdfRecordSmiles(record)
    if (smiles) indexed.set(smiles, [...(indexed.get(smiles) ?? []), index])
  })
  const used = new Set<number>()
  const output: string[] = []
  for (const row of rows) {
    const target = normalizeSmiles(row.smiles)
    const matches = indexed.get(target) ?? []
    if (target && matches.length === 1 && !used.has(matches[0]!)) {
      used.add(matches[0]!)
      output.push(ensureSdfDelimiter(records[matches[0]!]!))
    }
  }
  return output.join('')
}
