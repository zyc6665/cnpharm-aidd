import { parseCsvPreview, detectCsvResultFile, type CsvTaskFileReference } from './csv-result'

const MOLP_PC_CSV_HEADER = 'SMILES'

export function selectMolpPcCsvSourceFile(
  files: CsvTaskFileReference[]
): CsvTaskFileReference | null {
  const csvFiles = files
    .map(file => detectCsvResultFile(file))
    .filter((file): file is CsvTaskFileReference => Boolean(file))

  if (!csvFiles.length) {
    return null
  }

  const preferredOrder = [
    /qed[_-]?rank/i,
    /ranked/i,
    /metadata/i,
    /generated[_-]?molecules[_-]?smiles/i,
    /smiles/i
  ]

  for (const pattern of preferredOrder) {
    const matched = csvFiles.find(file =>
      pattern.test((file.original_name || file.filename || '').toLowerCase())
    )
    if (matched) {
      return matched
    }
  }

  return csvFiles[0] || null
}

export function canExportMolpPcCsv(files: CsvTaskFileReference[]): boolean {
  return Boolean(selectMolpPcCsvSourceFile(files)?.url)
}

function escapeCsvCell(value: string): string {
  if (/["\n\r,]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`
  }

  return value
}

export function buildMolpPcCsv(csvText: string): string | null {
  const preview = parseCsvPreview(csvText)
  if (!preview.smilesColumnKey) {
    return null
  }

  const smilesValues = preview.rows
    .map(row => String(row[preview.smilesColumnKey || ''] || '').trim())
    .filter(Boolean)

  if (!smilesValues.length) {
    return null
  }

  return [
    MOLP_PC_CSV_HEADER,
    ...smilesValues.map(escapeCsvCell)
  ].join('\n').concat('\n')
}
