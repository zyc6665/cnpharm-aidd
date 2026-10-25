/**
 * 靶点结构域（P-06~P-11）的类型定义。
 *
 * 字段名严格对齐后端 `backend/app/services/domain_targets.py` 的 `serialize_*`
 * 输出（snake_case），前端不在类型层做驼峰转换，避免与契约漂移。
 */

/** 结构/口袋的 3D 坐标（后端可能返回 null）。 */
export interface AxisVector {
  x: number | null
  y: number | null
  z: number | null
}

/** 模型或工具的 `{name, version}` 标识。 */
export interface ToolRef {
  name: string | null
  version: string | null
}

/** 口袋残基（`serialize_residue`）。 */
export interface PocketResidue {
  id: string
  pocket_id: string
  chain: string | null
  residue_seq: number | null
  residue_name: string | null
  is_key: boolean
  contribution: number | null
}

/** 口袋摘要（`serialize_pocket`）。 */
export interface PocketSummary {
  id: string
  structure_id: string
  rank: number | null
  score: number | null
  volume: number | null
  center: AxisVector | null
  box_size: AxisVector | null
  residue_count: number | null
  selected: boolean
  tool: ToolRef
  task_id: string | null
  created_at: string | null
  updated_at: string | null
  residues?: PocketResidue[]
}

/** 蛋白结构详情（`serialize_structure`）。 */
export interface ProteinStructureDetail {
  id: string
  protein_id: string
  source_type: string | null
  structure_urn: string | null
  structure_file_id: string | null
  prepared_urn: string | null
  prepared_file_id: string | null
  pdbqt_urn: string | null
  pdbqt_file_id: string | null
  sha256: string | null
  plddt_mean: number | null
  plddt_urn: string | null
  plddt_file_id: string | null
  model: ToolRef
  tool: ToolRef
  task_id: string | null
  created_at: string | null
  updated_at: string | null
  pockets?: PocketSummary[]
}

/** 蛋白详情（`serialize_protein`）。 */
export interface ProteinDetail {
  id: string
  target_id: string
  name: string
  sequence: string | null
  seq_length: number | null
  source: string | null
  current_version: number | null
  created_at: string | null
  updated_at: string | null
  structures?: ProteinStructureDetail[]
}

/** 靶点摘要/详情（`serialize_target`）。 */
export interface TargetSummary {
  id: string
  project_id: string
  created_by: string | null
  name: string
  target_type: string | null
  uniprot_id: string | null
  gene_name: string | null
  description: string | null
  created_at: string | null
  updated_at: string | null
  proteins?: ProteinDetail[]
}

/** 分页响应（后端 `paginated_response`）。 */
export interface PaginatedTargets {
  items: TargetSummary[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/** 结构文件下载信息（`GET /structures/{id}/pdb`）。 */
export interface StructureFileLink {
  role: string
  file_id: string
  urn: string | null
  download_url: string
}

export interface StructurePdbManifest {
  structure_id: string
  sha256: string | null
  files: StructureFileLink[]
}

/** 口袋残基列表响应（`GET /pockets/{id}/residues`）。 */
export interface PocketResidueList {
  pocket_id: string
  structure_id: string
  items: PocketResidue[]
}

/** 任务提交回执（`serialize_task_submission`，注意是 `task_id` 不是 `id`）。 */
export interface TaskSubmission {
  task_id: string
  status: string
  queue_position: number | null
  priority: string | null
}

/** 新建靶点入参（`TargetCreate`，后端 `extra='forbid'`）。 */
export interface TargetCreateInput {
  name: string
  target_type?: string
  uniprot_id?: string | null
  gene_name?: string | null
  description?: string | null
}

/** 更新靶点入参（`TargetUpdate`）。 */
export interface TargetUpdateInput {
  name?: string
  target_type?: string
  uniprot_id?: string | null
  gene_name?: string | null
  description?: string | null
}

/** 新增蛋白入参（`ProteinCreate`，sequence 与 file_id 二选一）。 */
export interface ProteinCreateInput {
  name: string
  sequence?: string
  file_id?: string
  source?: string
}

/** 结构预测入参（`StructurePredict`）。 */
export interface StructurePredictInput {
  model_ref?: { name: string; version?: string }
  params?: Record<string, string | number | boolean>
  scale?: string
  resource_profile?: string
  priority?: 'low' | 'normal' | 'high'
}

/** 结构导入入参（`StructureImport`）。 */
export interface StructureImportInput {
  file_id: string
  plddt_file_id?: string
  name?: string
  model_name?: string
  model_version?: string
  source_type?: string
}

/** 列表查询参数。 */
export interface TargetListParams {
  page?: number
  page_size?: number
  keyword?: string
  [key: string]: string | number | undefined
}
