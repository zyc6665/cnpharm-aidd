import type { WorkflowTaskRef } from '@/workflow/artifact-types'
import type {
  WorkflowCanvasEdge,
  WorkflowCanvasNode,
} from '@/workflow/template-types'

export interface WorkflowCanvasPosition {
  x: number
  y: number
}

export interface WorkflowWorkbenchSession {
  sessionId: string
  canvasPresetId: string
  activeNodeId: string | null
  activeGroupId: string | null
  selectedToolByGroup: Record<string, string>
  selectedToolByNode: Record<string, string>
  toolFormDrafts: Record<string, Record<string, unknown>>
  nodeFormDrafts: Record<string, Record<string, unknown>>
  taskByTool: Record<string, WorkflowTaskRef>
  taskByNode: Record<string, WorkflowTaskRef>
  artifactBindingsByNode: Record<string, Record<string, string>>
  nodePositionById: Record<string, WorkflowCanvasPosition>
  canvasNodes: WorkflowCanvasNode[]
  canvasEdges: WorkflowCanvasEdge[]
  hasCanvasOverride: boolean
  lastUpdatedAt: string
  ownerUserId?: string
}

export interface WorkflowRunsPagination {
  total: number
  page: number
  pageSize: number
  totalPages: number
}

function createWorkflowSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  return `workflow-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export function nowIsoString(): string {
  return new Date().toISOString()
}

export function createInitialWorkflowSession(ownerUserId?: string): WorkflowWorkbenchSession {
  return {
    sessionId: createWorkflowSessionId(),
    canvasPresetId: 'free-canvas',
    activeNodeId: null,
    activeGroupId: null,
    selectedToolByGroup: {},
    selectedToolByNode: {},
    toolFormDrafts: {},
    nodeFormDrafts: {},
    taskByTool: {},
    taskByNode: {},
    artifactBindingsByNode: {},
    nodePositionById: {},
    canvasNodes: [],
    canvasEdges: [],
    hasCanvasOverride: true,
    lastUpdatedAt: nowIsoString(),
    ownerUserId,
  }
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function normalizeRecord<T>(value: unknown): Record<string, T> {
  return isPlainRecord(value) ? (value as Record<string, T>) : {}
}
