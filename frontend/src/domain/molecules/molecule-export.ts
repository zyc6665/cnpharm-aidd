/**
 * 结果页的本地导出助手：CSV 与 SDF。
 *
 * - CSV 直接由当前结果表构造，保留表头顺序与所有列；
 * - SDF 优先复用任务产物里的原始记录（顺序或 SMILES 属性匹配），
 *   找不到对应记录时退化为「仅属性」的 SDF 记录（0 原子 + SMILES 属性），
 *   保证用户至少拿到一个可被下游工具读取的文件，而不是静默失败。
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

function buildPropertyOnlyRecord(smiles: string): string {
  // 0 原子 molfile + SMILES 属性：结构由 SMILES 列承载，属性块保留可检索的标识。
  return [
    smiles || 'molecule',
    '  AIDD-Export',
    '',
    '  0  0  0  0  0  0  0  0  0  0999 V2000',
    'M  END',
    '> <SMILES>',
    smiles,
    '',
    '$$$$',
    '',
  ].join('\n')
}

export interface SdfExportRow {
  smiles: string
}

/**
 * 按选中行生成 SDF 文本。
 *
 * 匹配顺序：
 * 1. 有 SMILES 时先在原始记录中按 `<SMILES>` 属性精确匹配（避免用户重新排序后错位）；
 * 2. 若记录缺少 SMILES 属性且原始记录数与行数一致，按原始下标对应；
 * 3. 仍未匹配的行生成仅属性记录。
 */
export function buildSdfExportText(
  records: readonly string[],
  rows: readonly SdfExportRow[]
): string {
  const used = new Set<number>()
  const sameLength = records.length === rows.length

  return rows
    .map((row, index) => {
      const target = normalizeSmiles(row.smiles)

      if (target) {
        const matchIndex = records.findIndex(
          (record, recordIdx) => !used.has(recordIdx) && readSdfRecordSmiles(record) === target
        )
        if (matchIndex >= 0) {
          used.add(matchIndex)
          const record = records[matchIndex]
          if (record) return ensureSdfDelimiter(record)
        }
      }

      if (sameLength && !used.has(index)) {
        const record = records[index]
        if (record && (!target || !readSdfRecordSmiles(record))) {
          used.add(index)
          return ensureSdfDelimiter(record)
        }
      }

      return buildPropertyOnlyRecord(target)
    })
    .join('')
}
