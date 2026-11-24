import { message } from 'ant-design-vue'
import { saveBlobAsFile } from '@/utils/protected-file-access'

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
  void saveBlobAsFile(`\ufeff${csv}`, filename, 'text/csv;charset=utf-8').catch(cause => {
    message.error(cause instanceof Error ? cause.message : String(cause))
  })
}
