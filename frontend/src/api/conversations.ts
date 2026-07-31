import { get, post, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  ConversationContentBlock,
  ConversationMessage,
  MessageBranchResult,
  PlanDecisionResult,
  ProjectConversation,
  ProjectResearchContext,
} from '@/types/conversations'

export const getProjectResearchContext = (
  projectId: string,
  options?: RequestOptions,
): Promise<ApiResponse<ProjectResearchContext>> => get(`/projects/${projectId}`, undefined, options)

export const getProjectConversations = (
  projectId: string,
  options?: RequestOptions,
): Promise<ApiResponse<{ items: ProjectConversation[] }>> =>
  get(`/projects/${projectId}/conversations`, undefined, options)

export const createProjectConversation = (
  projectId: string,
  title: string,
): Promise<ApiResponse<ProjectConversation>> => post(`/projects/${projectId}/conversations`, { title })

export const getConversationMessages = (
  conversationId: string,
  branchId?: string,
  options?: RequestOptions,
): Promise<ApiResponse<{ items: ConversationMessage[] }>> =>
  get(`/conversations/${conversationId}/messages`, branchId ? { branch_id: branchId } : undefined, options)

export const createConversationMessage = (
  conversationId: string,
  content: ConversationContentBlock[],
  branchId?: string,
): Promise<ApiResponse<ConversationMessage>> =>
  post(`/conversations/${conversationId}/messages`, { role: 'user', content, branch_id: branchId })

export const branchConversationMessage = (
  messageId: string,
  data: { content: ConversationContentBlock[]; title?: string },
): Promise<ApiResponse<MessageBranchResult>> => post(`/messages/${messageId}/branch`, data)

export const approvePlanVersion = (
  planId: string,
  comment?: string,
): Promise<ApiResponse<PlanDecisionResult>> => post(`/plan-versions/${planId}/approve`, { comment })

export const rejectPlanVersion = (
  planId: string,
  comment?: string,
): Promise<ApiResponse<PlanDecisionResult>> => post(`/plan-versions/${planId}/reject`, { comment })
