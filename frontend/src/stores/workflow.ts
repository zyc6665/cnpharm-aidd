import { computed } from 'vue'
import { defineStore, storeToRefs } from 'pinia'
import type { WorkflowDefinition } from '@/types/models'
import { type WorkflowArtifactSemanticType, type WorkflowTaskRef } from '@/workflow/artifact-types'
import type {
  WorkflowCanvasEdge,
  WorkflowCanvasNode,
  WorkflowTemplate as CanvasWorkflowTemplate
} from '@/workflow/template-types'
import { type ArtifactInputSlot, type ArtifactOutputSlot } from '@/workflow/contract-bindings'
import { type WorkflowCanvasPosition, type WorkflowWorkbenchSession } from './workflow-session'
import { useWorkflowCanvasStore } from './workflow-canvas'
import { useWorkflowFormDraftStore } from './workflow-form-draft'
import { useWorkflowTaskBindingStore } from './workflow-task-binding'
import { useWorkflowRunsStore } from './workflow-runs'
import { useWorkflowSessionStore } from './workflow-session-store'
import { useWorkflowTemplatesStore } from './workflow-templates'

interface AddToolNodeInput {
  toolSlug: string
  toolName?: string
  toolDescription?: string
  position?: WorkflowCanvasPosition
  requiredInputTypes?: WorkflowArtifactSemanticType[]
  producedOutputTypes?: WorkflowArtifactSemanticType[]
  inputArtifactSlots?: ArtifactInputSlot[]
  outputArtifactSlots?: ArtifactOutputSlot[]
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

export const useWorkflowStore = defineStore(
  'workflow',
  () => {
    // ── sub-stores ──
    const canvas = useWorkflowCanvasStore()
    const formDraft = useWorkflowFormDraftStore()
    const taskBinding = useWorkflowTaskBindingStore()
    const sessionStore = useWorkflowSessionStore()
    const templatesStore = useWorkflowTemplatesStore()
    const runsStore = useWorkflowRunsStore()

    const { sessionId, templateId, lastUpdatedAt, ownerUserId } = storeToRefs(sessionStore)
    const {
      workflowTemplates,
      activeWorkflowTemplate,
      activeWorkflowTemplateId,
      isLoadingWorkflowTemplates,
      isSavingWorkflowTemplate
    } = storeToRefs(templatesStore)
    const {
      workflowRuns,
      workflowRunsPagination,
      activeWorkflowRun,
      activeWorkflowRunId,
      isLoadingWorkflowRuns,
      isLoadingMoreWorkflowRuns,
      isLoadingWorkflowRun,
      isRunningWorkflowTemplate,
      isSyncingWorkflowRun,
      hasMoreWorkflowRuns
    } = storeToRefs(runsStore)
    const {
      activeNodeId,
      activeGroupId,
      nodePositionById,
      canvasNodes,
      canvasEdges,
      hasCanvasOverride
    } = storeToRefs(canvas)
    const { selectedToolByGroup, selectedToolByNode, toolFormDrafts, nodeFormDrafts } =
      storeToRefs(formDraft)
    const { taskByTool, taskByNode, artifactBindingsByNode } = storeToRefs(taskBinding)

    // ── session computed ──
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
      hasCanvasOverride: hasCanvasOverride.value,
      lastUpdatedAt: lastUpdatedAt.value,
      ownerUserId: ownerUserId.value
    }))

    function touchSession() {
      sessionStore.touch()
    }

    // ── lifecycle ──
    function normalizeSessionShape() {
      sessionStore.normalize()
      canvas.normalizeShape()
      formDraft.normalizeShape()
      taskBinding.normalizeShape()
    }

    function resetSession(nextOwnerUserId?: string) {
      sessionStore.reset(nextOwnerUserId)
      canvas.reset()
      formDraft.reset()
      taskBinding.reset()
    }

    function syncOwnerUserId(nextOwnerUserId?: string) {
      if (ownerUserId.value !== nextOwnerUserId) {
        resetSession(nextOwnerUserId)
        templatesStore.clearActiveWorkflowTemplate()
        runsStore.clear()
      }
    }

    function setTemplate(nextTemplateId: string) {
      if (!sessionStore.setTemplate(nextTemplateId)) return
      canvas.reset()
      formDraft.reset()
      taskBinding.reset()
    }

    // ── delegation: canvas ──
    const setActiveNode = (nodeId: string | null) => {
      canvas.setActiveNode(nodeId)
      touchSession()
    }
    const setActiveGroup = (groupId: string | null) => {
      canvas.setActiveGroup(groupId)
      touchSession()
    }
    const moveNode = (nodeId: string, pos: WorkflowCanvasPosition) => {
      canvas.moveNode(nodeId, pos)
      touchSession()
    }
    const setNodePositions = (p: Record<string, WorkflowCanvasPosition>) => {
      canvas.setNodePositions(p)
      touchSession()
    }
    const ensureCanvasFromTemplate = (t: CanvasWorkflowTemplate) => {
      canvas.ensureCanvasFromTemplate(t)
      touchSession()
    }
    const syncCanvasNodeSemanticTypes = () => canvas.syncNodeSemanticTypes()
    const exportWorkflowNodes = (n: WorkflowCanvasNode[]) => canvas.exportNodes(n)
    const exportWorkflowEdges = (e: WorkflowCanvasEdge[]) => canvas.exportEdges(e)
    const addCanvasEdge = (i: Parameters<typeof canvas.addEdge>[0]) => {
      const r = canvas.addEdge(i)
      touchSession()
      return r
    }
    const deleteCanvasEdge = (id: string) => {
      canvas.deleteEdge(id)
      touchSession()
    }

    function addToolNode(input: AddToolNodeInput): WorkflowCanvasNode {
      const nodeId = `tool-${input.toolSlug}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
      const node = canvas.addNode({
        id: nodeId,
        toolSlug: input.toolSlug,
        toolName: input.toolName,
        toolDescription: input.toolDescription,
        position: input.position,
        requiredInputTypes: input.requiredInputTypes,
        producedOutputTypes: input.producedOutputTypes,
        inputArtifactSlots: input.inputArtifactSlots,
        outputArtifactSlots: input.outputArtifactSlots
      })
      formDraft.selectNodeTool(nodeId, input.toolSlug)
      touchSession()
      return node
    }

    function deleteCanvasNode(nodeId: string) {
      // Check existence first (preserves old guard: input nodes cannot be deleted)
      const exists = canvasNodes.value.some(n => n.id === nodeId && n.type !== 'input')
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
      taskBinding.reset()
      taskBinding.artifactBindingsByNode = workflow.artifact_bindings_by_node ?? {}
      canvas.applyDefinition(workflow)
      touchSession()
    }

    // ── delegation: form draft ──
    const selectTool = (groupId: string, toolSlug: string) => {
      formDraft.selectTool(groupId, toolSlug)
      touchSession()
    }
    const selectNodeTool = (nodeId: string, toolSlug: string) => {
      formDraft.selectNodeTool(nodeId, toolSlug)
      touchSession()
    }
    const setToolFormDraft = (toolSlug: string, draft: Record<string, unknown>) => {
      formDraft.setToolFormDraft(toolSlug, draft)
      touchSession()
    }
    const setNodeFormDraft = (nodeId: string, draft: Record<string, unknown>) => {
      formDraft.setNodeFormDraft(nodeId, draft)
      touchSession()
    }
    const clearToolFormDraft = (toolSlug: string) => {
      formDraft.clearToolFormDraft(toolSlug)
      touchSession()
    }

    // ── delegation: task binding ──
    const recordTask = (toolSlug: string, task: WorkflowTaskRef) => {
      taskBinding.recordTask(toolSlug, task)
      touchSession()
    }
    const recordNodeTask = (nodeId: string, task: WorkflowTaskRef) => {
      taskBinding.recordNodeTask(nodeId, task)
      touchSession()
    }
    const setNodeArtifactBinding = (nodeId: string, field: string, artifactId: string) => {
      taskBinding.setNodeArtifactBinding(nodeId, field, artifactId)
      touchSession()
    }
    const clearTask = (toolSlug: string) => {
      taskBinding.clearTask(toolSlug)
      touchSession()
    }
    const clearNodeTask = (nodeId: string) => {
      taskBinding.clearNodeTask(nodeId)
      touchSession()
    }
    const clearNodeTasks = (nodeIds: string[]) => {
      taskBinding.clearNodeTasks(nodeIds)
      touchSession()
    }

    // ── templates and runs compatibility facade ──
    const loadWorkflowTemplates = templatesStore.loadWorkflowTemplates
    const loadWorkflowRuns = runsStore.loadWorkflowRuns
    const loadWorkflowTemplate = templatesStore.loadWorkflowTemplate

    async function saveWorkflowTemplate(
      ...args: Parameters<typeof templatesStore.saveWorkflowTemplate>
    ) {
      const template = await templatesStore.saveWorkflowTemplate(...args)
      touchSession()
      return template
    }

    async function updateSavedWorkflowTemplate(
      ...args: Parameters<typeof templatesStore.updateSavedWorkflowTemplate>
    ) {
      const template = await templatesStore.updateSavedWorkflowTemplate(...args)
      touchSession()
      return template
    }

    async function duplicateSavedWorkflowTemplate(
      ...args: Parameters<typeof templatesStore.duplicateSavedWorkflowTemplate>
    ) {
      const template = await templatesStore.duplicateSavedWorkflowTemplate(...args)
      touchSession()
      return template
    }

    async function removeWorkflowTemplate(
      ...args: Parameters<typeof templatesStore.removeWorkflowTemplate>
    ) {
      await templatesStore.removeWorkflowTemplate(...args)
      touchSession()
    }

    async function runWorkflowTemplate(...args: Parameters<typeof runsStore.runWorkflowTemplate>) {
      const run = await runsStore.runWorkflowTemplate(...args)
      touchSession()
      return run
    }

    async function loadWorkflowRun(...args: Parameters<typeof runsStore.loadWorkflowRun>) {
      const run = await runsStore.loadWorkflowRun(...args)
      touchSession()
      return run
    }

    async function syncActiveWorkflowRun(
      ...args: Parameters<typeof runsStore.syncActiveWorkflowRun>
    ) {
      const run = await runsStore.syncActiveWorkflowRun(...args)
      if (run) {
        touchSession()
      }
      return run
    }

    function setActiveWorkflowDefinition(
      definition: WorkflowDefinition,
      name = 'Untitled Workflow'
    ) {
      templatesStore.setActiveWorkflowDefinition(definition, ownerUserId.value, name)
      touchSession()
    }

    function clearActiveWorkflowRun() {
      runsStore.clearActiveWorkflowRun()
      touchSession()
    }

    function clearActiveWorkflowTemplate() {
      templatesStore.clearActiveWorkflowTemplate()
      touchSession()
    }

    function selectWorkflowRun(runId: string) {
      const selected = runsStore.selectWorkflowRun(runId)
      if (selected) {
        touchSession()
      }
      return selected
    }

    // ── public API ──
    return {
      // session
      sessionId,
      templateId,
      lastUpdatedAt,
      ownerUserId,
      // canvas (re-export sub-store refs for backward compat)
      activeNodeId,
      activeGroupId,
      nodePositionById,
      canvasNodes,
      canvasEdges,
      hasCanvasOverride,
      // form drafts (re-export sub-store refs)
      selectedToolByGroup,
      selectedToolByNode,
      toolFormDrafts,
      nodeFormDrafts,
      // task bindings (re-export sub-store refs)
      taskByTool,
      taskByNode,
      artifactBindingsByNode,
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
      setActiveWorkflowDefinition
    }
  },
  {
    persist: {
      pick: [
        'sessionId',
        'templateId',
        'lastUpdatedAt',
        'ownerUserId',
        'activeWorkflowTemplateId',
        'activeWorkflowRunId'
      ]
    }
  }
)
