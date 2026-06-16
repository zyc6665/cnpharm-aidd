import { del, get, post, put } from './request'
import type { ApiResponse } from '@/types/api'
import type { PaginatedResponse, PaginationParams } from '@/types/models'

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
  user_id: string
  name: string
  description?: string | null
  template_id: string
  nodes: WorkflowDefinitionNode[]
  edges: WorkflowDefinitionEdge[]
  selected_tool_by_node: Record<string, string>
  artifact_bindings_by_node: Record<string, Record<string, string>>
  status: 'draft' | 'active' | 'archived'
  created_at: string
  updated_at: string
}

export interface WorkflowDefinitionPayload {
  name: string
  description?: string | null
  template_id: string
  nodes: WorkflowDefinitionNode[]
  edges: WorkflowDefinitionEdge[]
  selected_tool_by_node: Record<string, string>
  artifact_bindings_by_node: Record<string, Record<string, string>>
  status?: 'draft' | 'active' | 'archived'
}

export interface WorkflowDefinitionUpdatePayload extends Partial<WorkflowDefinitionPayload> {}

export const getWorkflowDefinitions = (
  params?: PaginationParams
): Promise<ApiResponse<PaginatedResponse<WorkflowDefinition>>> => {
  return get<PaginatedResponse<WorkflowDefinition>>('/workflows', params as Record<string, unknown>)
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
