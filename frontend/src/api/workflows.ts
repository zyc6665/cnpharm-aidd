import { del, get, LONG_RUNNING_TIMEOUT_MS, post, put, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  PaginatedResponse,
  PaginationParams,
  WorkflowRun,
  WorkflowRunCreateParams,
} from '@/types/models'

export interface WorkflowCanvasPosition {
  x: number
  y: number
}

export interface WorkflowDefinitionNode {
  id: string
  type?: string
  titleKey?: string
  descriptionKey?: string
  position?: WorkflowCanvasPosition
  toolSlugs?: string[]
  recommendedToolSlug?: string
  requiredInputTypes?: string[]
  producedOutputTypes?: string[]
}

export interface WorkflowDefinitionEdge {
  id: string
  source: string
  target: string
  artifactType?: string
  labelKey?: string
}

export interface WorkflowDefinition {
  id: string
  project_id?: string | null
  user_id: string
  name: string
  description?: string | null
  canvas_preset_id: string
  nodes: WorkflowDefinitionNode[]
  edges: WorkflowDefinitionEdge[]
  selected_tool_by_node: Record<string, string>
  artifact_bindings_by_node: Record<string, Record<string, string>>
  status: 'draft' | 'active' | 'archived'
  created_at: string
  updated_at: string
}

export interface WorkflowDefinitionPayload {
  project_id?: string | null
  name: string
  description?: string | null
  canvas_preset_id: string
  nodes: WorkflowDefinitionNode[]
  edges: WorkflowDefinitionEdge[]
  selected_tool_by_node: Record<string, string>
  artifact_bindings_by_node: Record<string, Record<string, string>>
  status?: 'draft' | 'active' | 'archived'
}

export type WorkflowDefinitionUpdatePayload = Partial<WorkflowDefinitionPayload>

export interface WorkflowDefinitionListParams extends PaginationParams {
  project_id?: string
}

export interface WorkflowRunListParams extends PaginationParams {
  workflow_definition_id?: string
  project_id?: string
}

export const getWorkflowDefinitions = (
  params?: WorkflowDefinitionListParams
): Promise<ApiResponse<PaginatedResponse<WorkflowDefinition>>> => {
  return get<PaginatedResponse<WorkflowDefinition>, WorkflowDefinitionListParams>(
    '/workflows',
    params
  )
}

export const getWorkflowDefinition = (id: string): Promise<ApiResponse<WorkflowDefinition>> => {
  return get<WorkflowDefinition>(`/workflows/${id}`)
}

export const createWorkflowDefinition = (
  data: WorkflowDefinitionPayload
): Promise<ApiResponse<WorkflowDefinition>> => {
  return post<WorkflowDefinition>('/workflows', data)
}

export const updateWorkflowDefinition = (
  id: string,
  data: WorkflowDefinitionUpdatePayload
): Promise<ApiResponse<WorkflowDefinition>> => {
  return put<WorkflowDefinition>(`/workflows/${id}`, data)
}

export const deleteWorkflowDefinition = (id: string): Promise<ApiResponse<null>> => {
  return del<null>(`/workflows/${id}`)
}

export const getWorkflowRuns = (
  params?: WorkflowRunListParams,
  options?: RequestOptions
): Promise<ApiResponse<PaginatedResponse<WorkflowRun>>> => {
  return get<PaginatedResponse<WorkflowRun>, WorkflowRunListParams>(
    '/workflows/runs',
    params,
    options
  )
}

export const createWorkflowRun = (
  workflowDefinitionId: string,
  data: WorkflowRunCreateParams,
  options?: RequestOptions
): Promise<ApiResponse<WorkflowRun>> => {
  return post<WorkflowRun>(`/workflows/${workflowDefinitionId}/runs`, data, {
    ...options,
    timeout: options?.timeout ?? LONG_RUNNING_TIMEOUT_MS
  })
}

export const getWorkflowRun = (runId: string, options?: RequestOptions): Promise<ApiResponse<WorkflowRun>> => {
  return get<WorkflowRun>(`/workflows/runs/${runId}`, undefined, options)
}

export const syncWorkflowRun = (runId: string, options?: RequestOptions): Promise<ApiResponse<WorkflowRun>> => {
  return post<WorkflowRun>(`/workflows/runs/${runId}/sync`, undefined, {
    ...options,
    timeout: options?.timeout ?? LONG_RUNNING_TIMEOUT_MS
  })
}

export const cancelWorkflowRun = (
  runId: string,
  options?: RequestOptions
): Promise<ApiResponse<WorkflowRun>> => {
  return post<WorkflowRun>(`/workflows/runs/${runId}/cancel`, undefined, options)
}

export const retryWorkflowRunNode = (
  runId: string,
  nodeId: string,
  options?: RequestOptions
): Promise<ApiResponse<WorkflowRun>> => {
  return post<WorkflowRun>(`/workflows/runs/${runId}/nodes/${nodeId}/retry`, undefined, {
    ...options,
    timeout: options?.timeout ?? LONG_RUNNING_TIMEOUT_MS
  })
}
