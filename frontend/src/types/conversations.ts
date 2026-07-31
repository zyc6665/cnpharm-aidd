import type { TypedArtifact } from './artifacts'

export type ProjectRole = 'owner' | 'editor' | 'runner' | 'viewer'

export interface ProjectResearchContext {
  id: string
  name: string
  goal?: string | null
  status?: string
  membership: { role: ProjectRole }
}

export interface ProjectConversation {
  id: string
  project_id: string
  title: string
  status: string
  root_branch_id?: string | null
  created_at?: string
  updated_at?: string
}

export interface TextContentBlock {
  type: 'text'
  text: string
}

export interface ApprovalContentBlock {
  type: 'approval_ref'
  plan_id: string
  run_id?: string
  tool: string
  parameters: Record<string, unknown>
  resources: Record<string, unknown>
  estimated_duration_seconds?: number
  network_access: boolean
  status?: 'pending' | 'approved' | 'rejected'
}

export interface ReferenceContentBlock {
  type: 'citation' | 'artifact_ref'
  title?: string
  artifact_id?: string
  artifact?: TypedArtifact
  url?: string
  [key: string]: unknown
}

export type ConversationContentBlock =
  | TextContentBlock
  | ApprovalContentBlock
  | ReferenceContentBlock

export interface ConversationMessage {
  id: string
  conversation_id: string
  branch_id: string
  author_id?: string | null
  parent_message_id?: string | null
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: ConversationContentBlock[]
  plain_text: string
  sequence: number
  created_at?: string
}

export interface AgentEvent {
  id: string
  sequence: number
  event_type: string
  payload: Record<string, unknown>
  created_at?: string
}

export interface MessageBranchResult {
  branch: { id: string; parent_branch_id?: string; forked_from_message_id: string; title?: string }
  message: ConversationMessage
}

export interface PlanDecisionResult {
  id: string
  status: 'approved' | 'rejected'
  execution?: {
    execution_id: string
    state: string
    external_id?: string | null
  }
}

export interface ProjectAgentRunResult {
  id: string
  project_id: string
  conversation_id?: string | null
  message: string
  intent: string
  status: string
  input_type?: string | null
  requested_outputs: string[]
  plan: Record<string, unknown>
  plan_version?: {
    id: string
    status: 'pending' | 'approved' | 'rejected'
    content: Record<string, unknown>
  } | null
}
