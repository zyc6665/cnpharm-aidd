import { get, post, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  ConversationContentBlock,
  ConversationMessage,
  MessageBranchResult,
  PlanDecisionResult,
  ProjectAgentRun,
  ProjectAgentRunListParams,
  ProjectAgentRunListResult,
  ProjectAgentRunResult,
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
): Promise<ApiResponse<ProjectConversation>> =>
  post(`/projects/${projectId}/conversations`, { title })

export const getConversationMessages = (
  conversationId: string,
  branchId?: string,
  options?: RequestOptions,
): Promise<ApiResponse<{ items: ConversationMessage[] }>> =>
  get(
    `/conversations/${conversationId}/messages`,
    branchId ? { branch_id: branchId } : undefined,
    options,
  )

export const createConversationMessage = (
  conversationId: string,
  content: ConversationContentBlock[],
  branchId?: string,
): Promise<ApiResponse<ConversationMessage>> =>
  post(`/conversations/${conversationId}/messages`, {
    role: 'user',
    content,
    branch_id: branchId,
  })

export const startProjectAgentRun = (
  projectId: string,
  conversationId: string,
  data: { goal: string; protein_artifact_version_id?: string },
): Promise<ApiResponse<ProjectAgentRunResult>> =>
  post(`/projects/${projectId}/conversations/${conversationId}/agent-runs`, data)

export const getProjectAgentRuns = (
  projectId: string,
  params?: ProjectAgentRunListParams,
  options?: RequestOptions,
): Promise<ApiResponse<ProjectAgentRunListResult>> =>
  get(`/projects/${projectId}/agent-runs`, params, options)

export const getProjectAgentRun = (
  projectId: string,
  runId: string,
  options?: RequestOptions,
): Promise<ApiResponse<ProjectAgentRun>> =>
  get(`/projects/${projectId}/agent-runs/${runId}`, undefined, options)

export const cancelProjectAgentRun = (
  projectId: string,
  runId: string,
): Promise<ApiResponse<ProjectAgentRun>> =>
  post(`/projects/${projectId}/agent-runs/${runId}/cancel`)

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
