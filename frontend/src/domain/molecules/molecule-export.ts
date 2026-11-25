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
  moleculeId?: string
}

function readSdfRecordIdentity(record: string): string {
  const tagMatch = record.match(/^>\s*<(?:molecule_id|pose_id|ligand_id|id)>\s*\r?\n([^\r\n]+)/im)
  const tagValue = (tagMatch?.[1] ?? '').trim()
  if (tagValue) return tagValue
  return (record.split(/\r?\n/, 1)[0] ?? '').trim()
}

/**
 * 按选中行生成 SDF 文本。默认按唯一 SMILES 属性匹配；若同 SMILES 存在多条记录（如多构象）
 * 且行具备显式 `moleculeId`，则按唯一记录标识进一步消歧；无法确认时不伪造结构。
 */
export function buildSdfExportText(
  records: readonly string[],
  rows: readonly SdfExportRow[]
): string {
  const bySmiles = new Map<string, number[]>()
  const byIdentity = new Map<string, number[]>()
  records.forEach((record, index) => {
    const smiles = readSdfRecordSmiles(record)
    if (smiles) bySmiles.set(smiles, [...(bySmiles.get(smiles) ?? []), index])
    const identity = readSdfRecordIdentity(record)
    if (identity) byIdentity.set(identity, [...(byIdentity.get(identity) ?? []), index])
  })
  const used = new Set<number>()
  const output: string[] = []
  for (const row of rows) {
    const target = normalizeSmiles(row.smiles)
    const smilesMatches = target ? (bySmiles.get(target) ?? []) : []
    let picked: number | undefined
    if (smilesMatches.length === 1) {
      picked = smilesMatches[0]
    } else if (row.moleculeId?.trim()) {
      const idMatches = (byIdentity.get(row.moleculeId.trim()) ?? []).filter(index => {
        if (!target) return true
        const recSmiles = readSdfRecordSmiles(records[index]!)
        return !recSmiles || recSmiles === target
      })
      if (idMatches.length === 1) picked = idMatches[0]
    }
    if (picked !== undefined && !used.has(picked)) {
      used.add(picked)
      output.push(ensureSdfDelimiter(records[picked]!))
    }
  }
  return output.join('')
}
