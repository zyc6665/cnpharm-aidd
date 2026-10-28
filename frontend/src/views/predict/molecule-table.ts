import { getResult } from '@/api/results'
import { fetchProtectedFileText } from '@/utils/protected-file-access'
import { parseCsvPreview } from '@/domain/tasks/csv-result'
import type { CsvPreviewColumn, CsvPreviewRow } from '@/domain/tasks/csv-result'
import type { ProjectResultDetail, ResultOutputArtifact } from '@/types/compounds'

const MOLECULE_TABLE_STANDARD = 'molecule_table@1'

export interface MoleculeTableData {
  columns: CsvPreviewColumn[]
  rows: CsvPreviewRow[]
  mock: boolean
  detail: ProjectResultDetail
  artifact: ResultOutputArtifact | null
}

/** 在结果产物中定位 molecule_table（properties / ranked 都是 molecule_table@1）。 */
export function findMoleculeTableArtifact(
  detail: ProjectResultDetail
): ResultOutputArtifact | null {
  const found = detail.outputs.find(
    output =>
      output.standard_type === MOLECULE_TABLE_STANDARD ||
      output.artifact_type === 'molecule_table' ||
      (output.semantic_type ?? '').startsWith('molecule_table')
  )
  return found ?? null
}

/**
 * 读取 `GET /api/v1/results/{task_id}`，再下载 molecule_table 的 `table_file` 角色 CSV 并解析。
 * mock 标记来自同一结果的 `mock` 布尔（契约：GET /results 返回 mock）。
 */
export async function loadMoleculeTable(taskId: string): Promise<MoleculeTableData> {
  const response = await getResult(taskId)
  const detail: ProjectResultDetail & { mock?: boolean } = response.data
  const artifact = findMoleculeTableArtifact(detail)

  let columns: CsvPreviewColumn[] = []
  let rows: CsvPreviewRow[] = []

  if (artifact && artifact.version_id) {
    const url = `/api/v1/artifacts/${artifact.id}/versions/${artifact.version_id}/files/table_file/download`
    const text = await fetchProtectedFileText(url)
    const preview = parseCsvPreview(text)
    columns = preview.columns
    rows = preview.rows
  }

  return { columns, rows, mock: Boolean(detail.mock), detail, artifact }
}
