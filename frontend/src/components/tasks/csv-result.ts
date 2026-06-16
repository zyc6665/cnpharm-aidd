import Papa from 'papaparse'

export interface CsvTaskFileReference {
  filename?: string
  original_name?: string
  content_type?: string
  url?: string
}

export interface CsvPreviewColumn {
  key: string
  title: string
  originalKey: string
}

export type CsvPreviewRow = Record<string, string>

export interface CsvPreview {
  columns: CsvPreviewColumn[]
  rows: CsvPreviewRow[]
  smilesColumnKey: string | null
}

interface PapaParseModule {
  parse(input: string, config?: { skipEmptyLines?: boolean | 'greedy' }): {
    data: unknown[]
  }
}

const CSV_CONTENT_TYPES = new Set(['text/csv', 'application/csv', 'application/vnd.ms-excel'])
const SMILES_HEADER_KEYS = new Set([
  'smiles',
  'canonicalsmiles',
  'isomericsmiles',
  'molecule',
  'mol',
  'structure',
  'ligandsmiles',
  'compoundsmiles'
])

const SMILES_TOKEN_PATTERN =
  /\[(?:[^\]]+)\]|Br|Cl|Si|Na|Li|Mg|Ca|Al|Fe|Zn|Cu|Mn|Hg|Ag|Au|Pt|Pd|Co|Ni|Sn|Se|As|Bi|Te|Xe|Kr|Rb|Cs|Sr|Ba|Be|Ne|Ar|Ti|Cr|Mo|Ru|Rh|Ir|Os|Re|Ga|Ge|In|Tl|Pb|Sb|Po|At|Rn|He|La|Ce|Pr|Nd|Pm|Sm|Eu|Gd|Tb|Dy|Ho|Er|Tm|Yb|Lu|Ac|Th|Pa|Np|Pu|Am|Cm|Bk|Cf|Es|Fm|Md|No|Lr|B|C|N|O|P|S|F|I|K|H|V|W|U|Y|c|n|o|p|s|b|\*|@@?|%\d{2}|\d|[+\-=#$\\/.:()]/g

const SMILES_ATOM_PATTERN =
  /\[(?:[^\]]+)\]|Br|Cl|Si|Na|Li|Mg|Ca|Al|Fe|Zn|Cu|Mn|Hg|Ag|Au|Pt|Pd|Co|Ni|Sn|Se|As|Bi|Te|Xe|Kr|Rb|Cs|Sr|Ba|Be|Ne|Ar|Ti|Cr|Mo|Ru|Rh|Ir|Os|Re|Ga|Ge|In|Tl|Pb|Sb|Po|At|Rn|He|La|Ce|Pr|Nd|Pm|Sm|Eu|Gd|Tb|Dy|Ho|Er|Tm|Yb|Lu|Ac|Th|Pa|Np|Pu|Am|Cm|Bk|Cf|Es|Fm|Md|No|Lr|B|C|N|O|P|S|F|I|K|H|V|W|U|Y|c|n|o|p|s|b/

function getFileName(file: CsvTaskFileReference): string {
  return file.original_name || file.filename || file.url || ''
}

function normalizeHeaderKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '')
}

function normalizeCsvText(text: string): string {
  if (text.includes('\n') || text.includes('\r')) {
    return text
  }

  return text.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n')
}

function toCsvMatrix(text: string): string[][] {
  const parser = Papa as PapaParseModule
  const result = parser.parse(normalizeCsvText(text), { skipEmptyLines: 'greedy' })

  return result.data
    .filter((row): row is unknown[] => Array.isArray(row))
    .map(row => row.map(cell => String(cell ?? '')))
}

function buildColumns(headerRow: string[], columnCount: number): CsvPreviewColumn[] {
  const usedKeys = new Set<string>()
  const columns: CsvPreviewColumn[] = []

  for (let index = 0; index < columnCount; index += 1) {
    const originalKey = (headerRow[index] || '').replace(/^\uFEFF/, '').trim()
    const fallbackKey = `column_${index + 1}`
    const baseKey = originalKey || fallbackKey
    let key = baseKey
    let duplicateIndex = 2

    while (usedKeys.has(key)) {
      key = `${baseKey}_${duplicateIndex}`
      duplicateIndex += 1
    }

    usedKeys.add(key)
    columns.push({
      key,
      title: originalKey || `Column ${index + 1}`,
      originalKey
    })
  }

  return columns
}

function looksLikeSmiles(rawValue: string): boolean {
  const value = rawValue.trim()

  if (!value || /\s/.test(value) || !SMILES_ATOM_PATTERN.test(value)) {
    return false
  }

  return value.replace(SMILES_TOKEN_PATTERN, '') === ''
}

export function detectCsvResultFile(
  file?: CsvTaskFileReference | null
): CsvTaskFileReference | null {
  if (!file) {
    return null
  }

  const lowerName = getFileName(file).toLowerCase()
  const lowerType = (file.content_type || '').toLowerCase()

  if (lowerName.endsWith('.csv') || CSV_CONTENT_TYPES.has(lowerType)) {
    return file
  }

  return null
}

export function detectSmilesColumn(
  columnKeys: string[],
  rows: CsvPreviewRow[]
): string | null {
  for (const columnKey of columnKeys) {
    if (SMILES_HEADER_KEYS.has(normalizeHeaderKey(columnKey))) {
      return columnKey
    }
  }

  let bestCandidate: { key: string; ratio: number; count: number } | null = null

  for (const columnKey of columnKeys) {
    const values = rows
      .map(row => String(row[columnKey] || '').trim())
      .filter(Boolean)
      .slice(0, 25)

    if (!values.length) {
      continue
    }

    const smilesCount = values.filter(looksLikeSmiles).length
    const ratio = smilesCount / values.length

    if (smilesCount === 0 || ratio < 0.8) {
      continue
    }

    if (
      !bestCandidate ||
      ratio > bestCandidate.ratio ||
      (ratio === bestCandidate.ratio && smilesCount > bestCandidate.count)
    ) {
      bestCandidate = {
        key: columnKey,
        ratio,
        count: smilesCount
      }
    }
  }

  return bestCandidate?.key || null
}

export function parseCsvPreview(text: string): CsvPreview {
  const matrix = toCsvMatrix(text)

  if (!matrix.length) {
    return {
      columns: [],
      rows: [],
      smilesColumnKey: null
    }
  }

  const headerRow = matrix[0] || []
  const dataRows = matrix.slice(1)
  const columnCount = Math.max(headerRow.length, ...dataRows.map(row => row.length), 0)
  const columns = buildColumns(headerRow, columnCount)
  const rows = dataRows.map((row, rowIndex) =>
    columns.reduce<CsvPreviewRow>((record, column, columnIndex) => {
      record[column.key] = row[columnIndex] || ''
      record.__rowKey = String(rowIndex)
      return record
    }, {})
  )

  return {
    columns,
    rows,
    smilesColumnKey: detectSmilesColumn(
      columns.map(column => column.key),
      rows
    )
  }
}
