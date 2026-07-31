import { del, get, patch, post } from './request'
import type { ApiResponse } from '@/types/api'
import type { AiddWorkflowDraft } from '@/types/models'
import type { PaginatedResponse } from '@/types/models'

export interface ResearchBoardSummary {
  id: string
  owner_id: string
  name: string
  description?: string | null
  version: number
  node_count: number
  created_at: string
  updated_at: string
}

export interface ResearchBoard {
  id: string
  owner_id: string
  name: string
  description?: string | null
  content: Record<string, unknown>
  version: number
  created_at: string
  updated_at: string
}

export const getResearchBoards = () => get<PaginatedResponse<ResearchBoardSummary>>('/research-boards', { page: 1, page_size: 100 })
export const getResearchBoard = (id: string) => get<ResearchBoard>(`/research-boards/${id}`)
export const createResearchBoard = (data: Pick<ResearchBoard, 'name' | 'content'> & { description?: string }) => post<ResearchBoard>('/research-boards', data)
export const updateResearchBoard = (id: string, data: Partial<Pick<ResearchBoard, 'name' | 'description' | 'content'>> & { version: number }) => patch<ResearchBoard>(`/research-boards/${id}`, data)
export const deleteResearchBoard = (id: string) => del<null>(`/research-boards/${id}`)
export const createBoardWorkflowDraft = (id: string): Promise<ApiResponse<AiddWorkflowDraft>> => post(`/research-boards/${id}/workflow-draft`)
