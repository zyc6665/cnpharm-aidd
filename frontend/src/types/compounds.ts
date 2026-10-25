import type { TaskStatus } from './models'

/** 化合物分子性质（`compound.props`），键名与后端序列化保持一致。 */
export interface CompoundProperties {
  logP: number | null
  TPSA: number | null
  HBD: number | null
  HBA: number | null
  RotB: number | null
  QED: number | null
}

/** `serialize_compound` 的输出（docs/05 §4）。 */
export interface Compound {
  id: string
  name: string | null
  inchikey: string
  canonical_smiles: string
  mol_formula: string | null
  mol_weight: number | null
  props: CompoundProperties
  structure_urn: string | null
  created_at: string
  updated_at?: string
  created_by?: string | null
}

export type CandidateType = 'SMALL_MOLECULE' | 'PEPTIDE'

export type CandidateSource = 'IMPORT' | 'DESIGN' | 'SCREENING' | 'MANUAL'

/** 候选物在候选集里的位置（`serialize_set_item` 的 `location`）。 */
export type CandidateLocation = 'compound' | 'peptide'

/** `serialize_candidate` 的输出（docs/05 §5）。 */
export interface Candidate {
  id: string
  project_id: string
  candidate_type: CandidateType
  compound_id: string | null
  peptide_sequence: string | null
  name: string | null
  code: string | null
  source: CandidateSource
  design_score: number | null
  task_id: string | null
  attrs: Record<string, unknown>
  created_at: string
  updated_at: string
  compound: Compound | null
}

/**
 * 对比接口（`POST /candidates:compare`）把 7 项性质摊平到每条候选物顶层，
 * 其余字段与 `serialize_candidate` 相同。
 */
export interface CandidateComparison extends Omit<Candidate, 'compound'> {
  compound?: Compound | null
  mol_formula?: string | null
  mol_weight?: number | null
  logP?: number | null
  TPSA?: number | null
  HBD?: number | null
  HBA?: number | null
  RotB?: number | null
  QED?: number | null
}

/** 对比矩阵的输入：只要求能取到 7 项性质，页面可传 `Candidate` 或 `CandidateComparison`。 */
export interface ComparisonPropertySource {
  id: string
  name?: string | null
  candidate_type?: string
  code?: string | null
  compound?: Compound | null
  mol_formula?: string | null
  mol_weight?: number | null
  logP?: number | null
  TPSA?: number | null
  HBD?: number | null
  HBA?: number | null
  RotB?: number | null
  QED?: number | null
}

/** `serialize_candidate_set` 的输出。 */
export interface CandidateSet {
  id: string
  project_id: string
  name: string
  description: string | null
  item_count: number
  source_task_id: string | null
  version: number
  is_archived: boolean
  created_at: string
  updated_at: string
}

/** `serialize_set_item` 的输出。 */
export interface CandidateSetItem {
  id: string
  set_id: string
  candidate_id: string
  ordinal: number
  snapshot_score: number | null
  candidate: Candidate | null
  location: CandidateLocation
}

/** 化合物批量导入汇总（`data.summary`）。 */
export interface CompoundImportSummary {
  total: number
  success: number
  failed: number
  duplicate: number
  created_compounds?: number
}

export interface CompoundImportError {
  row: number
  message: string
}

export interface CompoundImportResult {
  summary: CompoundImportSummary
  errors: CompoundImportError[]
  file_id: string | null
}

export type DedupeStrategy = 'INCHIKEY_UPDATE' | 'INCHIKEY_SKIP' | 'INCHIKEY_ERROR'

export type ImportOnError = 'SKIP_AND_CONTINUE' | 'ABORT'

export interface CompoundCreateInput {
  smiles: string
  name?: string
}

export interface CompoundImportInput {
  file_id: string
  dataset_name?: string
  smiles_column?: string
  name_column?: string
  dedupe_strategy?: DedupeStrategy
  on_error?: ImportOnError
  set_name?: string
}

export interface CompoundSimilarityHit {
  compound: Compound
  similarity: number
}

export interface CompoundSearchResult {
  query: { smiles: string }
  fingerprint: { algorithm: string; bits: number }
  items: CompoundSimilarityHit[]
}

export interface CandidateCreateInput {
  candidate_type?: CandidateType
  smiles?: string
  peptide_sequence?: string
  name?: string
  code?: string
  source?: CandidateSource
  design_score?: number
  task_id?: string
  attrs?: Record<string, unknown>
}

export interface CandidateUpdateInput {
  name?: string
  code?: string
  design_score?: number
  attrs?: Record<string, unknown>
}

export interface CandidateCompareResult {
  items: CandidateComparison[]
  count: number
}

export interface CandidateSetCreateInput {
  name: string
  description?: string
  source_task_id?: string
}

export interface CandidateSetUpdateInput {
  name?: string
  description?: string
  version: number
  expected_version?: number
}

export interface CandidateSetItemsAddInput {
  candidate_ids: string[]
  snapshot_score?: number
}

export interface CandidateSetItemsAddResult {
  inserted: number
  skipped: number
  candidate_set: CandidateSet
}

export interface CandidateSetExportResult {
  candidate_set_id: string
  row_count: number
  file_id: string | null
  download_url: string | null
  content: string | null
  format: string
}

/** 化合物/候选物列表查询参数。 */
export interface CompoundListParams {
  page?: number
  page_size?: number
  keyword?: string
}

export interface CandidateListParams {
  page?: number
  page_size?: number
  candidate_type?: CandidateType
}

export interface CandidateSetListParams {
  page?: number
  page_size?: number
  include_archived?: boolean
}

/**
 * 结果列表项：后端 `_serialize_result` 的原样 snake_case 输出。
 * 与 `Task` 的差别在于主键叫 `task_id`、`finished_at` 可能是 `null`，
 * 因此这里单独声明而不改写 `types/models.d.ts` 里的 `Task`。
 */
export interface ProjectResultSummary {
  task_id: string
  name: string | null
  status: TaskStatus
  priority: string | null
  project_id: string
  tool_id: string | null
  tool_name: string | null
  tool_slug: string | null
  submitted_by: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  execution_time_sec: number | null
  error_message: string | null
  domain: string | null
}

/** 结果详情里的输入快照（`serialize_snapshot`，camelCase）。 */
export interface ResultInputSnapshot {
  inputRole: string | null
  ordinal: number
  entityType: string | null
  entityId: string | null
  urn: string | null
  sha256: string | null
  dataVersion: string | null
  fileId: string | null
  detail: Record<string, unknown> | null
  recordedAt: string | null
}

/** 结果详情里的产物项（`_artifact_outputs`）。 */
export interface ResultOutputArtifact {
  id: string
  artifact_type: string
  semantic_type: string | null
  standard_type: string | null
  standard_version: string | null
  name: string | null
  version_id: string | null
  version: number | null
  filename: string | null
  size_bytes: number | null
  sha256: string | null
}

export interface ProjectResultDetail extends ProjectResultSummary {
  inputs: ResultInputSnapshot[]
  outputs: ResultOutputArtifact[]
  output_data: Record<string, unknown> | null
}

export interface ProjectResultListParams {
  status?: TaskStatus
  page?: number
  page_size?: number
}

/** 追溯包（`services/traceability.py`，`traceability.v1`）。 */
export interface TraceabilityAuthor {
  userId: string | null
  displayName: string | null
  email: string | null
}

export interface TraceabilityTimeline {
  created: string | null
  started: string | null
  finished: string | null
  executionSeconds: number | null
  retryCount: number | null
}

export interface TraceabilityToolRef {
  id: string | null
  name: string | null
  slug: string | null
  version: string | null
  image: string | null
}

export interface TraceabilityEnvironment {
  image: string | null
  executorType: string | null
  tool: TraceabilityToolRef | null
  model: string | null
  resourceSnapshot: Record<string, unknown> | null
  contractVersion: string | null
}

export interface TraceabilityParams {
  requested: Record<string, unknown> | null
  inputBindings: Record<string, unknown> | null
}

export interface TraceabilityProcess {
  exitMessage: string | null
  progressMessage: string | null
  logAvailable: boolean | null
  logsEndpoint: string | null
}

export interface TraceabilityInput {
  inputRole?: string | null
  ordinal?: number
  entityType?: string | null
  entityId?: string | null
  urn?: string | null
  sha256?: string | null
  dataVersion?: string | null
  fileId?: string | null
  detail?: Record<string, unknown> | null
  recordedAt?: string | null
}

export interface TraceabilityOutput {
  kind: string | null
  artifactType: string | null
  semanticType: string | null
  standardType: string | null
  standardVersion: string | null
  urn: string | null
  sha256: string | null
  sizeBytes: number | null
  filename: string | null
}

export interface TraceabilityBizRef {
  projectId: string | null
  domain: string | null
}

export interface TraceabilityPackage {
  taskId: string
  taskName: string | null
  taskType: string | null
  status: string | null
  submittedBy: TraceabilityAuthor | null
  projectId: string | null
  timeline: TraceabilityTimeline | null
  inputs: TraceabilityInput[]
  environment: TraceabilityEnvironment | null
  params: TraceabilityParams | null
  process: TraceabilityProcess | null
  outputs: TraceabilityOutput[]
  bizRef: TraceabilityBizRef | null
  exportedAt: string | null
  packageVersion: string
}

export interface TraceabilityExportResult {
  task_id: string
  file_id: string | null
  filename: string | null
  sha256: string | null
  size_bytes: number | null
  download_url: string | null
}
