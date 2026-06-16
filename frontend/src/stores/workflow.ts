import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { WorkflowDefinition } from '@/api/workflows'
import type { WorkflowTaskRef } from '@/workflow/artifact-types'
import { toWorkflowTaskRef } from '@/workflow/task-state'
import type { WorkflowCanvasNode } from '@/workflow/template-types'

export interface WorkflowCanvasPosition {
  x: number
  y: number
}

interface WorkflowWorkbenchSession {
  sessionId: string
  templateId: string
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
  lastUpdatedAt: string
  ownerUserId?: string
}

function nowIsoString(): string {
  return new Date().toISOString()
}

function createWorkflowSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  return `workflow-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function createInitialWorkflowSession(ownerUserId?: string): WorkflowWorkbenchSession {
  return {
    sessionId: createWorkflowSessionId(),
    templateId: 'aidd-template',
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
    lastUpdatedAt: nowIsoString(),
    ownerUserId
  }
}

export const useWorkflowStore = defineStore('workflow', () => {
  const initialSession = createInitialWorkflowSession()

  const sessionId = ref(initialSession.sessionId)
  const templateId = ref(initialSession.templateId)
  const activeNodeId = ref<string | null>(initialSession.activeNodeId)
  const activeGroupId = ref<string | null>(initialSession.activeGroupId)
  const selectedToolByGroup = ref<Record<string, string>>(initialSession.selectedToolByGroup)
  const selectedToolByNode = ref<Record<string, string>>(initialSession.selectedToolByNode)
  const toolFormDrafts = ref<Record<string, Record<string, unknown>>>(initialSession.toolFormDrafts)
  const nodeFormDrafts = ref<Record<string, Record<string, unknown>>>(initialSession.nodeFormDrafts)
  const taskByTool = ref<Record<string, WorkflowTaskRef>>(initialSession.taskByTool)
  const taskByNode = ref<Record<string, WorkflowTaskRef>>(initialSession.taskByNode)
  const artifactBindingsByNode = ref<Record<string, Record<string, string>>>(
    initialSession.artifactBindingsByNode
  )
  const nodePositionById = ref<Record<string, WorkflowCanvasPosition>>(initialSession.nodePositionById)
  const lastUpdatedAt = ref(initialSession.lastUpdatedAt)
  const ownerUserId = ref<string | undefined>(initialSession.ownerUserId)

  const session = computed<WorkflowWorkbenchSession>(() => ({
    sessionId: sessionId.value,
    templateId: templateId.value,
    activeNodeId: activeNodeId.value,
    activeGroupId: activeGroupId.value,
    selectedToolByGroup: selectedToolByGroup.value,
    selectedToolByNode: selectedToolByNode.value,
    toolFormDrafts: toolFormDrafts.value,
    nodeFormDrafts: nodeFormDrafts.value,
    taskByTool: taskByTool.value,
    taskByNode: taskByNode.value,
    artifactBindingsByNode: artifactBindingsByNode.value,
    nodePositionById: nodePositionById.value,
    lastUpdatedAt: lastUpdatedAt.value,
    ownerUserId: ownerUserId.value
  }))

  function touchSession() {
    lastUpdatedAt.value = nowIsoString()
  }

  function resetSession(nextOwnerUserId?: string) {
    const nextSession = createInitialWorkflowSession(nextOwnerUserId)

    sessionId.value = nextSession.sessionId
    templateId.value = nextSession.templateId
    activeNodeId.value = nextSession.activeNodeId
    activeGroupId.value = nextSession.activeGroupId
    selectedToolByGroup.value = nextSession.selectedToolByGroup
    selectedToolByNode.value = nextSession.selectedToolByNode
    toolFormDrafts.value = nextSession.toolFormDrafts
    nodeFormDrafts.value = nextSession.nodeFormDrafts
    taskByTool.value = nextSession.taskByTool
    taskByNode.value = nextSession.taskByNode
    artifactBindingsByNode.value = nextSession.artifactBindingsByNode
    nodePositionById.value = nextSession.nodePositionById
    lastUpdatedAt.value = nextSession.lastUpdatedAt
    ownerUserId.value = nextSession.ownerUserId
  }

  function syncOwnerUserId(nextOwnerUserId?: string) {
    if (ownerUserId.value !== nextOwnerUserId) {
      resetSession(nextOwnerUserId)
    }
  }

  function setTemplate(nextTemplateId: string) {
    if (templateId.value === nextTemplateId) {
      return
    }

    templateId.value = nextTemplateId
    activeNodeId.value = null
    selectedToolByNode.value = {}
    nodeFormDrafts.value = {}
    taskByNode.value = {}
    artifactBindingsByNode.value = {}
    nodePositionById.value = {}
    touchSession()
  }

  function setActiveNode(nodeId: string | null) {
    activeNodeId.value = nodeId
    touchSession()
  }

  function setActiveGroup(groupId: string | null) {
    activeGroupId.value = groupId
    touchSession()
  }

  function selectTool(groupId: string, toolSlug: string) {
    selectedToolByGroup.value = {
      ...selectedToolByGroup.value,
      [groupId]: toolSlug
    }
    touchSession()
  }

  function selectNodeTool(nodeId: string, toolSlug: string) {
    selectedToolByNode.value = {
      ...selectedToolByNode.value,
      [nodeId]: toolSlug
    }
    touchSession()
  }

  function setToolFormDraft(toolSlug: string, draft: Record<string, unknown>) {
    toolFormDrafts.value = {
      ...toolFormDrafts.value,
      [toolSlug]: draft
    }
    touchSession()
  }

  function setNodeFormDraft(nodeId: string, draft: Record<string, unknown>) {
    nodeFormDrafts.value = {
      ...nodeFormDrafts.value,
      [nodeId]: draft
    }
    touchSession()
  }

  function clearToolFormDraft(toolSlug: string) {
    if (!toolFormDrafts.value[toolSlug]) {
      return
    }

    const nextDrafts = { ...toolFormDrafts.value }
    delete nextDrafts[toolSlug]
    toolFormDrafts.value = nextDrafts
    touchSession()
  }

  function recordTask(toolSlug: string, taskInput: WorkflowTaskRef) {
    taskByTool.value = {
      ...taskByTool.value,
      [toolSlug]: toWorkflowTaskRef(taskInput)
    }
    touchSession()
  }

  function recordNodeTask(nodeId: string, taskInput: WorkflowTaskRef) {
    taskByNode.value = {
      ...taskByNode.value,
      [nodeId]: toWorkflowTaskRef(taskInput)
    }
    touchSession()
  }

  function setNodeArtifactBinding(nodeId: string, field: string, artifactId: string) {
    artifactBindingsByNode.value = {
      ...artifactBindingsByNode.value,
      [nodeId]: {
        ...(artifactBindingsByNode.value[nodeId] ?? {}),
        [field]: artifactId
      }
    }
    touchSession()
  }

  function moveNode(nodeId: string, position: WorkflowCanvasPosition) {
    nodePositionById.value = {
      ...nodePositionById.value,
      [nodeId]: {
        x: Math.max(0, Math.round(position.x)),
        y: Math.max(0, Math.round(position.y))
      }
    }
    touchSession()
  }

  function setNodePositions(positions: Record<string, WorkflowCanvasPosition>) {
    nodePositionById.value = Object.entries(positions).reduce<Record<string, WorkflowCanvasPosition>>(
      (nextPositions, [nodeId, position]) => {
        nextPositions[nodeId] = {
          x: Math.max(0, Math.round(position.x)),
          y: Math.max(0, Math.round(position.y))
        }
        return nextPositions
      },
      {}
    )
    touchSession()
  }

  function exportWorkflowNodes(nodes: WorkflowCanvasNode[]) {
    return nodes.map(node => ({
      ...node,
      position: nodePositionById.value[node.id] ?? node.position
    }))
  }

  function applyWorkflowDefinition(workflow: WorkflowDefinition) {
    templateId.value = workflow.template_id
    selectedToolByNode.value = workflow.selected_tool_by_node ?? {}
    artifactBindingsByNode.value = workflow.artifact_bindings_by_node ?? {}
    taskByNode.value = {}
    activeNodeId.value = workflow.nodes[0]?.id ?? null

    setNodePositions(
      workflow.nodes.reduce<Record<string, WorkflowCanvasPosition>>((positions, node) => {
        if (node.position) {
          positions[node.id] = node.position
        }
        return positions
      }, {})
    )
  }

  function clearTask(toolSlug: string) {
    if (!taskByTool.value[toolSlug]) {
      return
    }

    const nextTasks = { ...taskByTool.value }
    delete nextTasks[toolSlug]
    taskByTool.value = nextTasks
    touchSession()
  }

  return {
    sessionId,
    templateId,
    activeNodeId,
    activeGroupId,
    selectedToolByGroup,
    selectedToolByNode,
    toolFormDrafts,
    nodeFormDrafts,
    taskByTool,
    taskByNode,
    artifactBindingsByNode,
    nodePositionById,
    lastUpdatedAt,
    ownerUserId,
    session,
    resetSession,
    syncOwnerUserId,
    setTemplate,
    setActiveNode,
    setActiveGroup,
    selectTool,
    selectNodeTool,
    setToolFormDraft,
    setNodeFormDraft,
    clearToolFormDraft,
    recordTask,
    recordNodeTask,
    setNodeArtifactBinding,
    moveNode,
    setNodePositions,
    exportWorkflowNodes,
    applyWorkflowDefinition,
    clearTask
  }
}, {
  persist: {
    pick: [
      'sessionId',
      'templateId',
      'activeNodeId',
      'activeGroupId',
      'selectedToolByGroup',
      'selectedToolByNode',
      'toolFormDrafts',
      'nodeFormDrafts',
      'taskByTool',
      'taskByNode',
      'artifactBindingsByNode',
      'nodePositionById',
      'lastUpdatedAt',
      'ownerUserId'
    ]
  }
})
