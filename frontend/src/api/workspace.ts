import { get } from './request'
import type { TaskStatus } from '@/types/models'

export interface WorkspaceTask {
  id: string
  name?: string
  status: TaskStatus
  progress: number
  error_message?: string
  tool_id: string
  tool_name?: string
  tool_slug?: string
  created_at: string
  updated_at: string
}

export interface WorkspaceTool {
  id: string
  name: string
  slug: string
  usage_count: number
}

export interface WorkspaceArtifactVersion {
  id: string
  version: number
  filename: string
  content_type?: string | null
  size_bytes: number
  sha256: string
  status: string
  expires_at?: string | null
  created_at: string
}

export interface WorkspaceArtifact {
  id: string
  project_id: string
  artifact_type: string
  semantic_type: string
  standard_type?: string | null
  standard_version?: number | null
  name: string
  description?: string | null
  latest_version: WorkspaceArtifactVersion
  created_at: string
  updated_at: string
}

export interface WorkspaceLegacyFile {
  id: string
  filename: string
  content_type?: string | null
  size_bytes: number
  updated_at: string
}

export interface WorkspaceOverview {
  attention_task_count: number
  task_status_counts: Record<TaskStatus, number>
  tasks: WorkspaceTask[]
  boards: Array<{ id: string; name: string; node_count: number; updated_at: string }>
  workflows: Array<{ id: string; name: string; status: string; updated_at: string }>
  artifacts?: WorkspaceArtifact[]
  files: WorkspaceLegacyFile[]
  frequent_tools: WorkspaceTool[]
}

export type WorkspaceAttentionTask = WorkspaceTask

export const getWorkspaceOverview = () =>
  get<WorkspaceOverview>('/workspace/overview', undefined, { silent: true, retry: 1 })
