import type { Task } from '@/types/models'
import {
  WORKFLOW_ARTIFACT_SEMANTIC_TYPES,
  type WorkflowArtifactSemanticType
} from './semantic-types.ts'

export const WORKFLOW_STEP_KEYS = [
  'pocketExploration',
  'moleculeGenerationOrVirtualScreening',
  'molecularDockingAndAffinityPrediction',
  'propertyPrediction',
  'leadOptimization'
] as const

export type WorkflowStepKey = (typeof WORKFLOW_STEP_KEYS)[number]

export const WORKFLOW_STEP_STATUSES = [
  'idle',
  'ready',
  'running',
  'completed',
  'failed',
  'invalidated',
  'needs_tool_selection'
] as const

export type WorkflowStepStatus = (typeof WORKFLOW_STEP_STATUSES)[number]

export { WORKFLOW_ARTIFACT_SEMANTIC_TYPES, type WorkflowArtifactSemanticType }

export interface WorkflowArtifact {
  id: string
  semanticType: WorkflowArtifactSemanticType
  name: string
  stepKey: WorkflowStepKey
  toolSlug: string
  taskId?: Task['id']
  fileId?: string | number
  url?: string
  contentType?: string
  createdAt: string
  isDefault?: boolean
  metadata?: Record<string, unknown>
}

export type WorkflowTaskRef = Pick<
    Task,
    | 'id'
    | 'name'
    | 'tool_id'
    | 'tool_slug'
    | 'status'
    | 'progress'
    | 'progress_message'
    | 'error_message'
    | 'started_at'
    | 'finished_at'
    | 'created_at'
    | 'updated_at'
    | 'output_data'
    | 'output_files'
  >

export interface WorkflowStepRecord {
  status: WorkflowStepStatus
  toolSlug?: string
  task?: WorkflowTaskRef
  errorMessage?: string
  updatedAt?: string
}

export type WorkflowStepDraftMap = Partial<Record<WorkflowStepKey, Record<string, unknown>>>
export type WorkflowSelectedToolMap = Partial<Record<WorkflowStepKey, string>>
export type WorkflowStepStateMap = Partial<Record<WorkflowStepKey, WorkflowStepRecord>>
export type WorkflowTaskMap = Partial<Record<WorkflowStepKey, WorkflowTaskRef>>

export interface WorkflowSession {
  sessionId: string
  activeStepKey: WorkflowStepKey
  selectedToolByStep: WorkflowSelectedToolMap
  stepFormDrafts: WorkflowStepDraftMap
  taskByStep: WorkflowTaskMap
  stepStateByKey: WorkflowStepStateMap
  artifacts: WorkflowArtifact[]
  invalidArtifactIds: string[]
  lastUpdatedAt: string
  ownerUserId?: string
}
