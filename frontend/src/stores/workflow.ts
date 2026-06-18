import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  createWorkflowRun,
  createWorkflowTemplate,
  deleteWorkflowTemplate,
  duplicateWorkflowTemplate,
  getWorkflowRun,
  getWorkflowRuns,
  getWorkflowTemplate,
  getWorkflowTemplates,
  syncWorkflowRun,
  updateWorkflowTemplate
} from '@/api/workflows'
import type { WorkflowDefinition as LegacyWorkflowDefinition } from '@/api/workflows'
import type {
  WorkflowDefinition,
  WorkflowRun,
  WorkflowRunCreateParams,
  WorkflowTemplate as SavedWorkflowTemplate,
  WorkflowTemplateCreateParams,
  WorkflowTemplateUpdateParams
} from '@/types/models'
import type { WorkflowTaskRef } from '@/workflow/artifact-types'
import { toWorkflowTaskRef } from '@/workflow/task-state'
import type {
  WorkflowCanvasEdge,
  WorkflowCanvasNode,
  WorkflowTemplate as CanvasWorkflowTemplate
} from '@/workflow/template-types'

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
  canvasNodes: WorkflowCanvasNode[]
  canvasEdges: WorkflowCanvasEdge[]
  lastUpdatedAt: string
  ownerUserId?: string
}

interface AddToolNodeInput {
  toolSlug: string
  toolName?: string
  toolDescription?: string
  position?: WorkflowCanvasPosition
}

interface WorkflowRunsPagination {
  total: number
  page: number
  pageSize: number
  totalPages: number
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
    canvasNodes: [],
    canvasEdges: [],
    lastUpdatedAt: nowIsoString(),
    ownerUserId
  }
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function normalizeRecord<T>(value: unknown): Record<string, T> {
  return isPlainRecord(value) ? value as Record<string, T> : {}
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
  const canvasNodes = ref<WorkflowCanvasNode[]>(initialSession.canvasNodes)
  const canvasEdges = ref<WorkflowCanvasEdge[]>(initialSession.canvasEdges)
  const lastUpdatedAt = ref(initialSession.lastUpdatedAt)
  const ownerUserId = ref<string | undefined>(initialSession.ownerUserId)
  const workflowTemplates = ref<SavedWorkflowTemplate[]>([])
  const workflowRuns = ref<WorkflowRun[]>([])
  const workflowRunsPagination = ref<WorkflowRunsPagination>({
    total: 0,
    page: 1,
    pageSize: 20,
    totalPages: 0
  })
  const activeWorkflowTemplate = ref<SavedWorkflowTemplate | null>(null)
  const activeWorkflowRun = ref<WorkflowRun | null>(null)
  const activeWorkflowTemplateId = ref<string | null>(null)
  const activeWorkflowRunId = ref<string | null>(null)
  const isLoadingWorkflowTemplates = ref(false)
  const isLoadingWorkflowRuns = ref(false)
  const isLoadingMoreWorkflowRuns = ref(false)
  const isSavingWorkflowTemplate = ref(false)
  const isLoadingWorkflowRun = ref(false)
  const isRunningWorkflowTemplate = ref(false)
  const isSyncingWorkflowRun = ref(false)

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
    canvasNodes: canvasNodes.value,
    canvasEdges: canvasEdges.value,
    lastUpdatedAt: lastUpdatedAt.value,
    ownerUserId: ownerUserId.value
  }))

  function touchSession() {
    lastUpdatedAt.value = nowIsoString()
  }

  const hasMoreWorkflowRuns = computed(() =>
    workflowRunsPagination.value.page < workflowRunsPagination.value.totalPages
  )

  function normalizeSessionShape() {
    if (typeof templateId.value !== 'string' || !templateId.value) {
      templateId.value = 'aidd-template'
    }

    if (activeNodeId.value !== null && typeof activeNodeId.value !== 'string') {
      activeNodeId.value = null
    }

    if (activeGroupId.value !== null && typeof activeGroupId.value !== 'string') {
      activeGroupId.value = null
    }

    selectedToolByGroup.value = normalizeRecord<string>(selectedToolByGroup.value)
    selectedToolByNode.value = normalizeRecord<string>(selectedToolByNode.value)
    toolFormDrafts.value = normalizeRecord<Record<string, unknown>>(toolFormDrafts.value)
    nodeFormDrafts.value = normalizeRecord<Record<string, unknown>>(nodeFormDrafts.value)
    taskByTool.value = normalizeRecord<WorkflowTaskRef>(taskByTool.value)
    taskByNode.value = normalizeRecord<WorkflowTaskRef>(taskByNode.value)
    artifactBindingsByNode.value = normalizeRecord<Record<string, string>>(artifactBindingsByNode.value)
    nodePositionById.value = normalizeRecord<WorkflowCanvasPosition>(nodePositionById.value)
    canvasNodes.value = Array.isArray(canvasNodes.value) ? canvasNodes.value : []
    canvasEdges.value = Array.isArray(canvasEdges.value) ? canvasEdges.value : []
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
    canvasNodes.value = nextSession.canvasNodes
    canvasEdges.value = nextSession.canvasEdges
    lastUpdatedAt.value = nextSession.lastUpdatedAt
    ownerUserId.value = nextSession.ownerUserId
  }

  function syncOwnerUserId(nextOwnerUserId?: string) {
    if (ownerUserId.value !== nextOwnerUserId) {
      resetSession(nextOwnerUserId)
      workflowRuns.value = []
      workflowRunsPagination.value = {
        total: 0,
        page: 1,
        pageSize: 20,
        totalPages: 0
      }
      activeWorkflowTemplate.value = null
      activeWorkflowTemplateId.value = null
      activeWorkflowRun.value = null
      activeWorkflowRunId.value = null
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
    canvasNodes.value = []
    canvasEdges.value = []
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

  function ensureCanvasFromTemplate(template: CanvasWorkflowTemplate) {
    if (canvasNodes.value.length > 0) {
      return
    }

    canvasNodes.value = template.nodes.map(node => ({
      ...node,
      position: nodePositionById.value[node.id] ?? node.position
    }))
    canvasEdges.value = template.edges.map(edge => ({ ...edge }))
    syncCanvasNodeSemanticTypes()
    touchSession()
  }

  function syncCanvasNodeSemanticTypes() {
    type ArtifactType = NonNullable<WorkflowCanvasEdge['artifactType']>
    const requiredByNode = new Map<string, Set<ArtifactType>>()
    const producedByNode = new Map<string, Set<ArtifactType>>()

    for (const edge of canvasEdges.value) {
      if (!edge.artifactType) {
        continue
      }

      if (!requiredByNode.has(edge.target)) {
        requiredByNode.set(edge.target, new Set())
      }
      if (!producedByNode.has(edge.source)) {
        producedByNode.set(edge.source, new Set())
      }

      requiredByNode.get(edge.target)?.add(edge.artifactType)
      producedByNode.get(edge.source)?.add(edge.artifactType)
    }

    canvasNodes.value = canvasNodes.value.map(node => {
      const requiredInputTypes = Array.from(requiredByNode.get(node.id) ?? [])
      const producedOutputTypes = Array.from(new Set<ArtifactType>([
        ...((node.producedOutputTypes ?? []) as ArtifactType[]),
        ...Array.from(producedByNode.get(node.id) ?? [])
      ]))

      return {
        ...node,
        requiredInputTypes,
        producedOutputTypes
      }
    })
  }

  function addToolNode(input: AddToolNodeInput): WorkflowCanvasNode {
    const nodeId = `tool-${input.toolSlug}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    const position = input.position ?? {
      x: 320 + canvasNodes.value.length * 32,
      y: 120 + canvasNodes.value.length * 24
    }
    const node: WorkflowCanvasNode = {
      id: nodeId,
      type: 'tool',
      toolSlugs: [input.toolSlug],
      recommendedToolSlug: input.toolSlug,
      titleKey: input.toolName || input.toolSlug,
      descriptionKey: input.toolDescription,
      position,
      requiredInputTypes: [],
      producedOutputTypes: []
    }

    canvasNodes.value = [...canvasNodes.value, node]
    selectedToolByNode.value = {
      ...selectedToolByNode.value,
      [nodeId]: input.toolSlug
    }
    nodePositionById.value = {
      ...nodePositionById.value,
      [nodeId]: position
    }
    activeNodeId.value = nodeId
    touchSession()
    return node
  }

  function deleteCanvasNode(nodeId: string) {
    const node = canvasNodes.value.find(item => item.id === nodeId)
    if (!node || node.type === 'input') {
      return
    }

    canvasNodes.value = canvasNodes.value.filter(item => item.id !== nodeId)
    canvasEdges.value = canvasEdges.value.filter(edge => edge.source !== nodeId && edge.target !== nodeId)

    const nextPositions = { ...nodePositionById.value }
    const nextSelectedTools = { ...selectedToolByNode.value }
    const nextNodeDrafts = { ...nodeFormDrafts.value }
    const nextTasks = { ...taskByNode.value }
    const nextBindings = { ...artifactBindingsByNode.value }

    delete nextPositions[nodeId]
    delete nextSelectedTools[nodeId]
    delete nextNodeDrafts[nodeId]
    delete nextTasks[nodeId]
    delete nextBindings[nodeId]

    nodePositionById.value = nextPositions
    selectedToolByNode.value = nextSelectedTools
    nodeFormDrafts.value = nextNodeDrafts
    taskByNode.value = nextTasks
    artifactBindingsByNode.value = nextBindings

    if (activeNodeId.value === nodeId) {
      activeNodeId.value = canvasNodes.value[0]?.id ?? null
    }
    touchSession()
  }

  function addCanvasEdge(input: {
    source: string
    target: string
    artifactType?: WorkflowCanvasEdge['artifactType']
  }): WorkflowCanvasEdge | null {
    if (input.source === input.target) {
      return null
    }

    const hasSource = canvasNodes.value.some(node => node.id === input.source)
    const hasTarget = canvasNodes.value.some(node => node.id === input.target)
    if (!hasSource || !hasTarget) {
      return null
    }

    const existing = canvasEdges.value.find(edge => (
      edge.source === input.source &&
      edge.target === input.target &&
      edge.artifactType === input.artifactType
    ))
    if (existing) {
      return existing
    }

    const edge: WorkflowCanvasEdge = {
      id: `edge-${input.source}-${input.target}-${Date.now()}`,
      source: input.source,
      target: input.target,
      artifactType: input.artifactType
    }
    canvasEdges.value = [...canvasEdges.value, edge]
    syncCanvasNodeSemanticTypes()
    touchSession()
    return edge
  }

  function deleteCanvasEdge(edgeId: string) {
    if (!canvasEdges.value.some(edge => edge.id === edgeId)) {
      return
    }

    canvasEdges.value = canvasEdges.value.filter(edge => edge.id !== edgeId)
    syncCanvasNodeSemanticTypes()
    touchSession()
  }

  function exportWorkflowNodes(nodes: WorkflowCanvasNode[]) {
    const sourceNodes = canvasNodes.value.length ? canvasNodes.value : nodes
    return sourceNodes.map(node => ({
      ...node,
      position: nodePositionById.value[node.id] ?? node.position
    }))
  }

  function exportWorkflowEdges(edges: WorkflowCanvasEdge[]) {
    return canvasNodes.value.length ? canvasEdges.value : edges
  }

  function applyWorkflowDefinition(workflow: LegacyWorkflowDefinition) {
    templateId.value = workflow.template_id
    selectedToolByNode.value = workflow.selected_tool_by_node ?? {}
    artifactBindingsByNode.value = workflow.artifact_bindings_by_node ?? {}
    taskByNode.value = {}
    canvasNodes.value = workflow.nodes.map(node => node as WorkflowCanvasNode)
    canvasEdges.value = workflow.edges.map(edge => edge as WorkflowCanvasEdge)
    syncCanvasNodeSemanticTypes()
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

  function upsertWorkflowRun(run: WorkflowRun) {
    workflowRuns.value = [
      run,
      ...workflowRuns.value.filter(item => item.id !== run.id)
    ]
  }

  async function loadWorkflowTemplates() {
    isLoadingWorkflowTemplates.value = true
    try {
      const response = await getWorkflowTemplates()
      workflowTemplates.value = response.data.items
      return response.data
    } finally {
      isLoadingWorkflowTemplates.value = false
    }
  }

  async function loadWorkflowRuns(params?: {
    template_id?: string
    page?: number
    page_size?: number
  }, options: {
    append?: boolean
  } = {}) {
    if (options?.append) {
      isLoadingMoreWorkflowRuns.value = true
    } else {
      isLoadingWorkflowRuns.value = true
    }
    try {
      const response = await getWorkflowRuns(params)
      const nextItems = response.data.items
      workflowRuns.value = options?.append
        ? [
            ...workflowRuns.value,
            ...nextItems.filter(item => !workflowRuns.value.some(run => run.id === item.id))
          ]
        : nextItems
      workflowRunsPagination.value = {
        total: response.data.total,
        page: response.data.page,
        pageSize: response.data.page_size,
        totalPages: response.data.total_pages
      }
      return response.data
    } finally {
      if (options?.append) {
        isLoadingMoreWorkflowRuns.value = false
      } else {
        isLoadingWorkflowRuns.value = false
      }
    }
  }

  async function loadWorkflowTemplate(templateId: string) {
    const response = await getWorkflowTemplate(templateId)
    activeWorkflowTemplate.value = response.data
    activeWorkflowTemplateId.value = response.data.id
    return response.data
  }

  async function saveWorkflowTemplate(data: WorkflowTemplateCreateParams) {
    isSavingWorkflowTemplate.value = true
    try {
      const response = await createWorkflowTemplate(data)
      activeWorkflowTemplate.value = response.data
      activeWorkflowTemplateId.value = response.data.id
      workflowTemplates.value = [response.data, ...workflowTemplates.value]
      touchSession()
      return response.data
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function updateSavedWorkflowTemplate(
    templateId: string,
    data: WorkflowTemplateUpdateParams
  ) {
    isSavingWorkflowTemplate.value = true
    try {
      const response = await updateWorkflowTemplate(templateId, data)
      activeWorkflowTemplate.value = response.data
      activeWorkflowTemplateId.value = response.data.id
      workflowTemplates.value = workflowTemplates.value.map(template =>
        template.id === response.data.id ? response.data : template
      )
      touchSession()
      return response.data
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function duplicateSavedWorkflowTemplate(templateId: string, name?: string) {
    isSavingWorkflowTemplate.value = true
    try {
      const response = await duplicateWorkflowTemplate(templateId, { name })
      activeWorkflowTemplate.value = response.data
      activeWorkflowTemplateId.value = response.data.id
      workflowTemplates.value = [response.data, ...workflowTemplates.value]
      touchSession()
      return response.data
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function removeWorkflowTemplate(templateId: string) {
    isSavingWorkflowTemplate.value = true
    try {
      await deleteWorkflowTemplate(templateId)
      workflowTemplates.value = workflowTemplates.value.filter(template => template.id !== templateId)
      if (activeWorkflowTemplateId.value === templateId) {
        activeWorkflowTemplate.value = null
        activeWorkflowTemplateId.value = null
      }
      touchSession()
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function runWorkflowTemplate(
    templateId: string,
    input: WorkflowRunCreateParams
  ) {
    isRunningWorkflowTemplate.value = true
    try {
      const response = await createWorkflowRun(templateId, input)
      activeWorkflowRun.value = response.data
      activeWorkflowRunId.value = response.data.id
      upsertWorkflowRun(response.data)
      touchSession()
      return response.data
    } finally {
      isRunningWorkflowTemplate.value = false
    }
  }

  async function loadWorkflowRun(runId: string) {
    isLoadingWorkflowRun.value = true
    try {
      const response = await getWorkflowRun(runId)
      activeWorkflowRun.value = response.data
      activeWorkflowRunId.value = response.data.id
      upsertWorkflowRun(response.data)
      touchSession()
      return response.data
    } finally {
      isLoadingWorkflowRun.value = false
    }
  }

  async function syncActiveWorkflowRun(runId = activeWorkflowRunId.value) {
    if (!runId) {
      return null
    }

    isSyncingWorkflowRun.value = true
    try {
      const response = await syncWorkflowRun(runId)
      activeWorkflowRun.value = response.data
      activeWorkflowRunId.value = response.data.id
      upsertWorkflowRun(response.data)
      touchSession()
      return response.data
    } finally {
      isSyncingWorkflowRun.value = false
    }
  }

  function setActiveWorkflowDefinition(definition: WorkflowDefinition, name = 'Untitled Workflow') {
    activeWorkflowTemplate.value = {
      id: activeWorkflowTemplateId.value ?? '',
      owner_id: ownerUserId.value ?? '',
      name,
      status: 'draft',
      definition,
      is_public: false,
      version: 1,
      created_at: nowIsoString(),
      updated_at: nowIsoString()
    }
    touchSession()
  }

  function clearActiveWorkflowRun() {
    activeWorkflowRun.value = null
    activeWorkflowRunId.value = null
    touchSession()
  }

  function clearActiveWorkflowTemplate() {
    activeWorkflowTemplate.value = null
    activeWorkflowTemplateId.value = null
    touchSession()
  }

  function selectWorkflowRun(runId: string) {
    const run = workflowRuns.value.find(item => item.id === runId)
    if (!run) {
      return false
    }
    activeWorkflowRun.value = run
    activeWorkflowRunId.value = run.id
    touchSession()
    return true
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
    canvasNodes,
    canvasEdges,
    lastUpdatedAt,
    ownerUserId,
    workflowTemplates,
    workflowRuns,
    workflowRunsPagination,
    activeWorkflowTemplate,
    activeWorkflowRun,
    activeWorkflowTemplateId,
    activeWorkflowRunId,
    isLoadingWorkflowTemplates,
    isLoadingWorkflowRuns,
    isLoadingMoreWorkflowRuns,
    isSavingWorkflowTemplate,
    isLoadingWorkflowRun,
    isRunningWorkflowTemplate,
    isSyncingWorkflowRun,
    session,
    hasMoreWorkflowRuns,
    resetSession,
    normalizeSessionShape,
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
    ensureCanvasFromTemplate,
    syncCanvasNodeSemanticTypes,
    addToolNode,
    deleteCanvasNode,
    addCanvasEdge,
    deleteCanvasEdge,
    exportWorkflowNodes,
    exportWorkflowEdges,
    applyWorkflowDefinition,
    clearTask,
    loadWorkflowTemplates,
    loadWorkflowRuns,
    loadWorkflowTemplate,
    saveWorkflowTemplate,
    updateSavedWorkflowTemplate,
    duplicateSavedWorkflowTemplate,
    removeWorkflowTemplate,
    runWorkflowTemplate,
    loadWorkflowRun,
    syncActiveWorkflowRun,
    clearActiveWorkflowRun,
    clearActiveWorkflowTemplate,
    selectWorkflowRun,
    setActiveWorkflowDefinition
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
      'canvasNodes',
      'canvasEdges',
      'lastUpdatedAt',
      'ownerUserId',
      'activeWorkflowTemplateId',
      'activeWorkflowRunId'
    ]
  }
})
