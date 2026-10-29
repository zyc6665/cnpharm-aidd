import type { AssetArtifactType } from './enums.generated'

/**
 * 数据资产统一检索返回项（`GET /projects/{id}/assets`）。
 *
 * 类型集合来自后端单一真源的 codegen（`enums.generated.ts` 的 `AssetArtifactType`），
 * 前端不手抄。`source` 区分底层来源：`artifact` 走 Artifact 资产根，`dataset` 回落
 * 数据集领域表——两者语义不同，UI 需据此说明。
 */
export interface AssetItemMetadata {
  semanticType?: string | null
  standardType?: string | null
  standardVersion?: number | null
  filename?: string | null
  contentType?: string | null
  sizeBytes?: number | null
  datasetType?: string | null
  rowCount?: number | null
  fileCount?: number | null
  summary?: Record<string, unknown>
}

export interface AssetItem {
  id: string
  asset_type: AssetArtifactType
  name: string
  description: string | null
  source: 'artifact' | 'dataset'
  latest_version_id: string | null
  created_at: string | null
  updated_at: string | null
  metadata: AssetItemMetadata
}

export interface AssetListParams {
  type?: AssetArtifactType
  page?: number
  page_size?: number
}

export interface AssetListResponse {
  items: AssetItem[]
  total: number
  page: number
  page_size: number
  total_pages?: number
}
