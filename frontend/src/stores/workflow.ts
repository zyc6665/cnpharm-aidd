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
  updateWorkflowTemplate,
} from '@/api/workflows'
import type {
  WorkflowDefinition,
  WorkflowRun,
  WorkflowRunCreateParams,
  WorkflowTemplate as SavedWorkflowTemplate,
  WorkflowTemplateCreateParams,
  WorkflowTemplateUpdateParams,
} from '@/types/models'
import { type WorkflowTaskRef } from '@/workflow/artifact-types'
import type {
  WorkflowCanvasEdge,
  WorkflowCanvasNode,
  WorkflowTemplate as CanvasWorkflowTemplate,
} from '@/workflow/template-types'
import {
  createInitialWorkflowSession,
  nowIsoString,
  type WorkflowCanvasPosition,
  type WorkflowWorkbenchSession,
  type WorkflowRunsPagination,
} from './workflow-session'
import { useWorkflowCanvasStore } from './workflow-canvas'
import { useWorkflowFormDraftStore } from './workflow-form-draft'
import { useWorkflowTaskBindingStore } from './workflow-task-binding'

interface AddToolNodeInput {
  toolSlug: string
  toolName?: string
  toolDescription?: string
  position?: WorkflowCanvasPosition
}

type WorkflowDefinitionLike = {
  template_id: string
  nodes: Array<{
    id: string
    kind?: 'input' | 'tool' | string
    type?: string
    semantic_type?: string
    tool_slug?: string
    semantic_inputs?: Record<string, string>
    position?: WorkflowCanvasPosition
  }>
  edges: Array<{
    id?: string
    source: string
    target: string
    artifactType?: string
    source_output?: string
    target_input?: string
  }>
  selected_tool_by_node?: Record<string, string>
  artifact_bindings_by_node?: Record<string, Record<string, string>>
}

export const useWorkflowStore = defineStore('workflow', () => {
  // ── sub-stores ──
  const canvas = useWorkflowCanvasStore()
  const formDraft = useWorkflowFormDraftStore()
  const taskBinding = useWorkflowTaskBindingStore()

  // ── session metadata ──
  const initialSession = createInitialWorkflowSession()
  const sessionId = ref(initialSession.sessionId)
  const templateId = ref(initialSession.templateId)
  const lastUpdatedAt = ref(initialSession.lastUpdatedAt)
  const ownerUserId = ref<string | undefined>(initialSession.ownerUserId)

  // ── API state (non-persisted) ──
  const workflowTemplates = ref<SavedWorkflowTemplate[]>([])
  const workflowRuns = ref<WorkflowRun[]>([])
  const workflowRunsPagination = ref<WorkflowRunsPagination>({
    total: 0, page: 1, pageSize: 20, totalPages: 0,
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

  // ── session computed ──
  const session = computed<WorkflowWorkbenchSession>(() => ({
    sessionId: sessionId.value,
    templateId: templateId.value,
    activeNodeId: canvas.activeNodeId,
    activeGroupId: canvas.activeGroupId,
    selectedToolByGroup: formDraft.selectedToolByGroup,
    selectedToolByNode: formDraft.selectedToolByNode,
    toolFormDrafts: formDraft.toolFormDrafts,
    nodeFormDrafts: formDraft.nodeFormDrafts,
    taskByTool: taskBinding.taskByTool,
    taskByNode: taskBinding.taskByNode,
    artifactBindingsByNode: taskBinding.artifactBindingsByNode,
    nodePositionById: canvas.nodePositionById,
    canvasNodes: canvas.canvasNodes,
    canvasEdges: canvas.canvasEdges,
    lastUpdatedAt: lastUpdatedAt.value,
    ownerUserId: ownerUserId.value,
  }))

  const hasMoreWorkflowRuns = computed(() =>
    workflowRunsPagination.value.page < workflowRunsPagination.value.totalPages,
  )

  function touchSession() {
    lastUpdatedAt.value = nowIsoString()
  }

  // ── lifecycle ──
  function normalizeSessionShape() {
    if (typeof templateId.value !== 'string' || !templateId.value) {
      templateId.value = 'aidd-template'
    }
    canvas.normalizeShape()
    formDraft.normalizeShape()
    taskBinding.normalizeShape()
  }

  function resetSession(nextOwnerUserId?: string) {
    const next = createInitialWorkflowSession(nextOwnerUserId)
    sessionId.value = next.sessionId
    templateId.value = next.templateId
    lastUpdatedAt.value = next.lastUpdatedAt
    ownerUserId.value = next.ownerUserId
    canvas.reset()
    formDraft.reset()
    taskBinding.reset()
  }

  function syncOwnerUserId(nextOwnerUserId?: string) {
    if (ownerUserId.value !== nextOwnerUserId) {
      resetSession(nextOwnerUserId)
      workflowRuns.value = []
      workflowRunsPagination.value = { total: 0, page: 1, pageSize: 20, totalPages: 0 }
      activeWorkflowTemplate.value = null
      activeWorkflowTemplateId.value = null
      activeWorkflowRun.value = null
      activeWorkflowRunId.value = null
    }
  }

  function setTemplate(nextTemplateId: string) {
    if (templateId.value === nextTemplateId) return
    templateId.value = nextTemplateId
    canvas.reset()
    formDraft.reset()
    taskBinding.reset()
    touchSession()
  }

  // ── delegation: canvas ──
  const setActiveNode = (nodeId: string | null) => { canvas.setActiveNode(nodeId); touchSession() }
  const setActiveGroup = (groupId: string | null) => { canvas.setActiveGroup(groupId); touchSession() }
  const moveNode = (nodeId: string, pos: WorkflowCanvasPosition) => { canvas.moveNode(nodeId, pos); touchSession() }
  const setNodePositions = (p: Record<string, WorkflowCanvasPosition>) => { canvas.setNodePositions(p); touchSession() }
  const ensureCanvasFromTemplate = (t: CanvasWorkflowTemplate) => { canvas.ensureCanvasFromTemplate(t); touchSession() }
  const syncCanvasNodeSemanticTypes = () => canvas.syncNodeSemanticTypes()
  const exportWorkflowNodes = (n: WorkflowCanvasNode[]) => canvas.exportNodes(n)
  const exportWorkflowEdges = (e: WorkflowCanvasEdge[]) => canvas.exportEdges(e)
  const addCanvasEdge = (i: Parameters<typeof canvas.addEdge>[0]) => { const r = canvas.addEdge(i); touchSession(); return r }
  const deleteCanvasEdge = (id: string) => { canvas.deleteEdge(id); touchSession() }

  function addToolNode(input: AddToolNodeInput): WorkflowCanvasNode {
    const nodeId = `tool-${input.toolSlug}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    const node = canvas.addNode({
      id: nodeId,
      toolSlug: input.toolSlug,
      toolName: input.toolName,
      toolDescription: input.toolDescription,
      position: input.position,
    })
    formDraft.selectNodeTool(nodeId, input.toolSlug)
    touchSession()
    return node
  }

  function deleteCanvasNode(nodeId: string) {
    // Check existence first (preserves old guard: input nodes cannot be deleted)
    const exists = (canvas.canvasNodes as WorkflowCanvasNode[]).some(
      (n) => n.id === nodeId && n.type !== 'input',
    )
    if (!exists) return
    canvas.deleteNode(nodeId)
    formDraft.removeNodeSelection(nodeId)
    formDraft.clearNodeFormDraft(nodeId)
    taskBinding.clearNodeTask(nodeId)
    taskBinding.clearNodeArtifactBindings(nodeId)
    touchSession()
  }

  function applyWorkflowDefinition(workflow: WorkflowDefinitionLike) {
    templateId.value = workflow.template_id
    formDraft.selectedToolByNode = workflow.selected_tool_by_node ?? {}
    taskBinding.artifactBindingsByNode = workflow.artifact_bindings_by_node ?? {}
    taskBinding.reset() // clears tasks only
    canvas.applyDefinition(workflow)
    touchSession()
  }

  // ── delegation: form draft ──
  const selectTool = (groupId: string, toolSlug: string) => { formDraft.selectTool(groupId, toolSlug); touchSession() }
  const selectNodeTool = (nodeId: string, toolSlug: string) => { formDraft.selectNodeTool(nodeId, toolSlug); touchSession() }
  const setToolFormDraft = (toolSlug: string, draft: Record<string, unknown>) => { formDraft.setToolFormDraft(toolSlug, draft); touchSession() }
  const setNodeFormDraft = (nodeId: string, draft: Record<string, unknown>) => { formDraft.setNodeFormDraft(nodeId, draft); touchSession() }
  const clearToolFormDraft = (toolSlug: string) => { formDraft.clearToolFormDraft(toolSlug); touchSession() }

  // ── delegation: task binding ──
  const recordTask = (toolSlug: string, task: WorkflowTaskRef) => { taskBinding.recordTask(toolSlug, task); touchSession() }
  const recordNodeTask = (nodeId: string, task: WorkflowTaskRef) => { taskBinding.recordNodeTask(nodeId, task); touchSession() }
  const setNodeArtifactBinding = (nodeId: string, field: string, artifactId: string) => { taskBinding.setNodeArtifactBinding(nodeId, field, artifactId); touchSession() }
  const clearTask = (toolSlug: string) => { taskBinding.clearTask(toolSlug); touchSession() }
  const clearNodeTask = (nodeId: string) => { taskBinding.clearNodeTask(nodeId); touchSession() }
  const clearNodeTasks = (nodeIds: string[]) => { taskBinding.clearNodeTasks(nodeIds); touchSession() }

  // ── API operations ──
  function upsertWorkflowRun(run: WorkflowRun) {
    workflowRuns.value = [run, ...workflowRuns.value.filter((item) => item.id !== run.id)]
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

  async function loadWorkflowRuns(
    params?: { template_id?: string; page?: number; page_size?: number },
    options: { append?: boolean } = {},
  ) {
    if (options?.append) {
      isLoadingMoreWorkflowRuns.value = true
    } else {
      isLoadingWorkflowRuns.value = true
    }
    try {
      const response = await getWorkflowRuns(params)
      const next = response.data.items
      workflowRuns.value = options?.append
        ? [...workflowRuns.value, ...next.filter((item) => !workflowRuns.value.some((r) => r.id === item.id))]
        : next
      workflowRunsPagination.value = {
        total: response.data.total,
        page: response.data.page,
        pageSize: response.data.page_size,
        totalPages: response.data.total_pages,
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

  async function loadWorkflowTemplate(templateIdParam: string) {
    const response = await getWorkflowTemplate(templateIdParam)
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

  async function updateSavedWorkflowTemplate(templateIdParam: string, data: WorkflowTemplateUpdateParams) {
    isSavingWorkflowTemplate.value = true
    try {
      const response = await updateWorkflowTemplate(templateIdParam, data)
      activeWorkflowTemplate.value = response.data
      activeWorkflowTemplateId.value = response.data.id
      workflowTemplates.value = workflowTemplates.value.map((t) =>
        t.id === response.data.id ? response.data : t,
      )
      touchSession()
      return response.data
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function duplicateSavedWorkflowTemplate(templateIdParam: string, name?: string) {
    isSavingWorkflowTemplate.value = true
    try {
      const response = await duplicateWorkflowTemplate(templateIdParam, { name })
      activeWorkflowTemplate.value = response.data
      activeWorkflowTemplateId.value = response.data.id
      workflowTemplates.value = [response.data, ...workflowTemplates.value]
      touchSession()
      return response.data
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function removeWorkflowTemplate(templateIdParam: string) {
    isSavingWorkflowTemplate.value = true
    try {
      await deleteWorkflowTemplate(templateIdParam)
      workflowTemplates.value = workflowTemplates.value.filter((t) => t.id !== templateIdParam)
      if (activeWorkflowTemplateId.value === templateIdParam) {
        activeWorkflowTemplate.value = null
        activeWorkflowTemplateId.value = null
      }
      touchSession()
    } finally {
      isSavingWorkflowTemplate.value = false
    }
  }

  async function runWorkflowTemplate(templateIdParam: string, input: WorkflowRunCreateParams) {
    isRunningWorkflowTemplate.value = true
    try {
      const response = await createWorkflowRun(templateIdParam, input)
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
    if (!runId) return null
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
      updated_at: nowIsoString(),
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
    const run = workflowRuns.value.find((item) => item.id === runId)
    if (!run) return false
    activeWorkflowRun.value = run
    activeWorkflowRunId.value = run.id
    touchSession()
    return true
  }

  // ── public API ──
  return {
    // session
    sessionId,
    templateId,
    lastUpdatedAt,
    ownerUserId,
    // canvas (re-export sub-store refs for backward compat)
    activeNodeId: canvas.activeNodeId,
    activeGroupId: canvas.activeGroupId,
    nodePositionById: canvas.nodePositionById,
    canvasNodes: canvas.canvasNodes,
    canvasEdges: canvas.canvasEdges,
    // form drafts (re-export sub-store refs)
    selectedToolByGroup: formDraft.selectedToolByGroup,
    selectedToolByNode: formDraft.selectedToolByNode,
    toolFormDrafts: formDraft.toolFormDrafts,
    nodeFormDrafts: formDraft.nodeFormDrafts,
    // task bindings (re-export sub-store refs)
    taskByTool: taskBinding.taskByTool,
    taskByNode: taskBinding.taskByNode,
    artifactBindingsByNode: taskBinding.artifactBindingsByNode,
    // API state
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
    // computed
    session,
    hasMoreWorkflowRuns,
    // lifecyle
    resetSession,
    normalizeSessionShape,
    syncOwnerUserId,
    setTemplate,
    // canvas delegation
    setActiveNode,
    setActiveGroup,
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
    // form delegation
    selectTool,
    selectNodeTool,
    setToolFormDraft,
    setNodeFormDraft,
    clearToolFormDraft,
    // task delegation
    recordTask,
    recordNodeTask,
    setNodeArtifactBinding,
    clearTask,
    clearNodeTask,
    clearNodeTasks,
    // API
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
    setActiveWorkflowDefinition,
  }
}, {
  persist: {
    pick: [
      'sessionId',
      'templateId',
      'lastUpdatedAt',
      'ownerUserId',
      'activeWorkflowTemplateId',
      'activeWorkflowRunId',
    ],
  },
})
