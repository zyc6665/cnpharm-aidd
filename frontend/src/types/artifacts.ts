export type ArtifactType =
  | 'protein_structure'
  | 'binding_pocket'
  | 'pocket_result'
  | 'ligand_structure'
  | 'molecule_table'
  | 'file'
  | 'run_report'

export interface ArtifactVersionFile {
  id: string
  role: string
  file_id: string
  is_primary: boolean
  sort_order: number
  filename?: string | null
  content_type?: string | null
  size_bytes?: number | null
  sha256?: string | null
  download_url: string
}

export interface ArtifactVersion {
  id: string
  version: number
  filename: string
  content_type?: string | null
  size_bytes: number
  sha256: string
  status: string
  manifest_json?: {
    metadata?: Record<string, unknown>
    [key: string]: unknown
  } | null
  expires_at?: string | null
  created_at: string
  files?: ArtifactVersionFile[]
}

export interface TypedArtifact {
  id: string
  project_id: string
  artifact_type: ArtifactType | (string & {})
  semantic_type: string
  standard_type?: string | null
  standard_version?: number | null
  name: string
  description?: string | null
  latest_version: ArtifactVersion
  versions?: ArtifactVersion[]
  deduplicated?: boolean
  created_at: string
  updated_at: string
  [key: string]: unknown
}

export interface ArtifactListResponse {
  items: TypedArtifact[]
}

export type ArtifactLineageGraphNodeKind =
  | 'artifact'
  | 'version'
  | 'task'
  | 'workflow_node'

export type ArtifactLineageGraphEdgeKind =
  | 'has_version'
  | 'derived_from'
  | 'produced_by'
  | 'runs_task'
  | (string & {})

export interface ArtifactLineageGraphNode {
  id: string
  kind: ArtifactLineageGraphNodeKind
  label: string
  artifact_id?: string | null
  version_id?: string | null
  task_id?: string | null
  workflow_run_id?: string | null
  workflow_definition_id?: string | null
  workflow_node_id?: string | null
  name?: string | null
  artifact_type?: string | null
  semantic_type?: string | null
  standard_type?: string | null
  standard_version?: number | null
  source_task_id?: string | null
  latest_version_id?: string | null
  version?: number | null
  filename?: string | null
  content_type?: string | null
  size_bytes?: number | null
  status?: string | null
  tool_id?: string | null
  tool_name?: string | null
  tool_slug?: string | null
  created_at?: string | null
  updated_at?: string | null
  [key: string]: unknown
}

export interface ArtifactLineageGraphEdge {
  id: string
  kind: ArtifactLineageGraphEdgeKind
  source: string
  target: string
  relation_type?: string | null
  lineage_id?: string | null
  project_id?: string | null
  created_at?: string | null
  [key: string]: unknown
}

export interface ArtifactLineageGraphSummary {
  artifacts: number
  versions: number
  tasks: number
  workflow_nodes: number
  lineage_edges: number
}

export interface ArtifactLineageGraph {
  project_id: string
  nodes: ArtifactLineageGraphNode[]
  edges: ArtifactLineageGraphEdge[]
  summary: ArtifactLineageGraphSummary
}

export interface ArtifactUploadInput {
  file: File
  artifact_type: ArtifactType | string
  semantic_type: string
  description?: string
  expires_at?: string
}
