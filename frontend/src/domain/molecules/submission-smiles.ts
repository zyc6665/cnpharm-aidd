export interface InlineSmilesRow {
  smiles: string
  name?: string
}

export interface InlineSmilesParseResult {
  validRows: InlineSmilesRow[]
  totalNonEmptyLines: number
  skippedCount: number
  previewRows: InlineSmilesRow[]
}

function parseCsvRows(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []; let field = ''; let quoted = false
  const source = text.replace(/^\uFEFF/, '')
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i]
    if (quoted) {
      if (char === '"' && source[i + 1] === '"') { field += '"'; i += 1 }
      else if (char === '"') quoted = false
      else field += char
    } else if (char === '"' && field.length === 0) quoted = true
    else if (char === ',') { row.push(field); field = '' }
    else if (char === '\n') { row.push(field); if (row.some(cell => cell.trim())) rows.push(row); row = []; field = '' }
    else if (char !== '\r') field += char
  }
  row.push(field); if (row.some(cell => cell.trim())) rows.push(row)
  return rows
}

const PLACEHOLDERS = new Set(['-', '--', 'n/a', 'na', 'null', 'none', 'undefined', 'smiles'])

function likelySmiles(value: string): boolean {
  const text = value.trim()
  if (!text || PLACEHOLDERS.has(text.toLowerCase()) || /\s/.test(text)) return false
  if (/^(?:[=#:.]|\.|.*[=#:.])$/.test(text)) return false
  let brackets = 0
  let parentheses = 0
  let escaped = false
  let hasAtom = false
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i]!
    if (escaped) { escaped = false; continue }
    if (char === '\\') { escaped = true; continue }
    if (char === '[') { brackets += 1; hasAtom = true; continue }
    if (char === ']') { brackets -= 1; if (brackets < 0) return false; continue }
    if (brackets > 0) {
      if (!/[A-Za-z0-9@+\-*=.:H]/.test(char)) return false
      continue
    }
    if (char === '(') { parentheses += 1; continue }
    if (char === ')') { parentheses -= 1; if (parentheses < 0) return false; continue }
    if ((char === 'C' && text[i + 1] === 'l') || (char === 'B' && text[i + 1] === 'r')) {
      hasAtom = true; i += 1; continue
    }
    if (/[BCNOPSFHIbcnops]/.test(char)) { hasAtom = true; continue }
    if (!/[0-9@+\-=#$:/%.*]/.test(char)) return false
  }
  return !escaped && brackets === 0 && parentheses === 0 && hasAtom
}

export function parseInlineSmiles(text: string): InlineSmilesParseResult {
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/)
  const nonEmpty = lines.filter(line => line.trim()).length
  const csvRows = parseCsvRows(text)
  const headers = (csvRows[0] ?? []).map(value => value.trim().toLowerCase())
  const smilesColumn = headers.findIndex(value => value === 'smiles' || value === 'canonical_smiles')
  const nameColumn = headers.findIndex(value => ['name', 'id', 'molecule_id', 'ligand_id'].includes(value))
  const records: InlineSmilesRow[] = []
  if (smilesColumn >= 0) {
    for (const cells of csvRows.slice(1)) {
      const smiles = (cells[smilesColumn] ?? '').trim()
      if (likelySmiles(smiles)) records.push({ smiles, name: (cells[nameColumn] ?? '').trim() || undefined })
    }
  } else {
    for (const line of lines) {
      const trimmed = line.trim(); if (!trimmed) continue
      const cells = trimmed.split(/[\t ]+/)
      const smiles = (cells.length > 1 ? cells[0] : trimmed) ?? ''
      if (likelySmiles(smiles)) records.push({ smiles, name: cells.length > 1 ? cells.slice(1).join(' ') : undefined })
    }
  }
  const skippedCount = smilesColumn >= 0
    ? Math.max(0, csvRows.slice(1).length - records.length)
    : Math.max(0, nonEmpty - records.length)
  return { validRows: records, totalNonEmptyLines: nonEmpty, skippedCount, previewRows: records.slice(0, 12) }
}

export function escapeCsvCell(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value
}

export function buildInlineSmilesCsv(rows: InlineSmilesRow[]): string {
  return ['smiles', ...rows.map(row => escapeCsvCell(row.smiles))].join('\n')
}

export function buildInlineSmilesFile(rows: InlineSmilesRow[], filename = `inline_smiles_${Date.now()}.csv`): File {
  return new File([buildInlineSmilesCsv(rows)], filename, { type: 'text/csv' })
}

export function rewriteSdfRecordsWithTitle(text: string, fallbackTitlePrefix: string): string[] {
  const records = text.split(/^\$\$\$\$\s*$/m).filter(record => record.trim())
  return records.map((record, index) => {
    const lines = record.replace(/\r?\n$/, '').split(/\r?\n/)
    if (lines.length < 4) return record
    if (!(lines[0] ?? '').trim()) lines[0] = `${fallbackTitlePrefix}_${index + 1}`
    return `${lines.join('\n')}\n$$$$`
  })
}
