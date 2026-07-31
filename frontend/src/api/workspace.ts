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

export interface WorkspaceOverview {
  attention_task_count: number
  task_status_counts: Record<TaskStatus, number>
  tasks: WorkspaceTask[]
  boards: Array<{ id: string; name: string; node_count: number; updated_at: string }>
  workflows: Array<{ id: string; name: string; status: string; updated_at: string }>
  files: Array<{
    id: string
    filename: string
    content_type?: string
    size_bytes: number
    updated_at: string
  }>
  frequent_tools: WorkspaceTool[]
}

export const getWorkspaceOverview = () => get<WorkspaceOverview>('/workspace/overview')
