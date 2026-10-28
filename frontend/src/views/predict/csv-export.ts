/** 通用 CSV 导出：把 [{key,title}] 列与 Record 行拼成 CSV 并触发浏览器下载。 */
export interface CsvExportColumn {
  key: string
  title: string
}

function escapeCell(raw: string): string {
  if (/[",\n\r]/.test(raw)) {
    return `"${raw.replace(/"/g, '""')}"`
  }
  return raw
}

export function buildCsv(
  columns: CsvExportColumn[],
  rows: Array<Record<string, string>>
): string {
  const header = columns.map(column => escapeCell(column.title)).join(',')
  const body = rows.map(row =>
    columns.map(column => escapeCell(row[column.key] ?? '')).join(',')
  )
  return [header, ...body].join('\n')
}

export function downloadCsv(
  filename: string,
  columns: CsvExportColumn[],
  rows: Array<Record<string, string>>
): void {
  const csv = buildCsv(columns, rows)
  const blob = new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}
