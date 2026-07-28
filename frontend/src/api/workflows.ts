import { del, get, post, put } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  PaginatedResponse,
  PaginationParams,
  WorkflowRun,
  WorkflowRunCreateParams,
  WorkflowTemplate,
  WorkflowTemplateCreateParams,
  WorkflowTemplateUpdateParams
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

export type WorkflowDefinitionUpdatePayload = Partial<WorkflowDefinitionPayload>

export const getWorkflowDefinitions = (
  params?: PaginationParams
): Promise<ApiResponse<PaginatedResponse<WorkflowDefinition>>> => {
  return get<PaginatedResponse<WorkflowDefinition>, PaginationParams>('/workflows', params)
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

export const getWorkflowTemplates = (): Promise<ApiResponse<PaginatedResponse<WorkflowTemplate>>> => {
  return get<PaginatedResponse<WorkflowTemplate>>('/workflows/templates')
}

export const getWorkflowRuns = (params?: {
  template_id?: string
  page?: number
  page_size?: number
}): Promise<ApiResponse<PaginatedResponse<WorkflowRun>>> => {
  return get<PaginatedResponse<WorkflowRun>>('/workflows/runs', params)
}

export const getWorkflowTemplate = (id: string): Promise<ApiResponse<WorkflowTemplate>> => {
  return get<WorkflowTemplate>(`/workflows/templates/${id}`)
}

export const createWorkflowTemplate = (
  data: WorkflowTemplateCreateParams
): Promise<ApiResponse<WorkflowTemplate>> => {
  return post<WorkflowTemplate>('/workflows/templates', data)
}

export const updateWorkflowTemplate = (
  id: string,
  data: WorkflowTemplateUpdateParams
): Promise<ApiResponse<WorkflowTemplate>> => {
  return put<WorkflowTemplate>(`/workflows/templates/${id}`, data)
}

export const duplicateWorkflowTemplate = (
  id: string,
  data: { name?: string } = {}
): Promise<ApiResponse<WorkflowTemplate>> => {
  return post<WorkflowTemplate>(`/workflows/templates/${id}/duplicate`, data)
}

export const deleteWorkflowTemplate = (id: string): Promise<ApiResponse<{ id: string }>> => {
  return del<{ id: string }>(`/workflows/templates/${id}`)
}

export const createWorkflowRun = (
  templateId: string,
  data: WorkflowRunCreateParams
): Promise<ApiResponse<WorkflowRun>> => {
  return post<WorkflowRun>(`/workflows/templates/${templateId}/runs`, data)
}

export const getWorkflowRun = (runId: string): Promise<ApiResponse<WorkflowRun>> => {
  return get<WorkflowRun>(`/workflows/runs/${runId}`)
}

export const syncWorkflowRun = (runId: string): Promise<ApiResponse<WorkflowRun>> => {
  return post<WorkflowRun>(`/workflows/runs/${runId}/sync`)
}
