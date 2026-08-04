import { computed, ref, type ComputedRef } from 'vue'
import { message } from 'ant-design-vue'
import type { WorkflowDefinitionPayload } from '@/api/workflows'
import {
  buildWorkflowInputFileMap,
  findLatestArtifactForSemanticType
} from '@/workflow/workflow-definitions'
import { shouldAutoSyncWorkflowRun } from '@/workflow/workflow-runs'
import {
  validateWorkflowDefinition,
  validateWorkflowExecutionOrder
} from '@/workflow/template-runner'
import {
  WORKFLOW_ARTIFACT_SEMANTIC_TYPES,
  type WorkflowArtifactSemanticType
} from '@/workflow/artifact-types'
import type { WorkflowCanvasEdge, WorkflowCanvasNode } from '@/workflow/template-types'
import {
  useArtifactsStore,
  useUserStore,
  useWorkflowDefinitionsStore,
  useWorkflowStore
} from '@/stores'
import type { AiddWorkflowDraft, WorkflowDefinition, WorkflowDefinitionNode } from '@/types/models'

type UserStore = ReturnType<typeof useUserStore>
type ArtifactsStore = ReturnType<typeof useArtifactsStore>
type WorkflowStore = ReturnType<typeof useWorkflowStore>
type WorkflowDefinitionsStore = ReturnType<typeof useWorkflowDefinitionsStore>

export function useWorkflowPersistence(input: {
  userStore: UserStore
  artifactsStore: ArtifactsStore
  workflowStore: WorkflowStore
  workflowDefinitionsStore: WorkflowDefinitionsStore
  editableCanvasPreset: ComputedRef<{
    id: string
    nodes: WorkflowCanvasNode[]
    edges: WorkflowCanvasEdge[]
  }>
  projectId?: ComputedRef<string | undefined>
  workflowInputRequirements: ComputedRef<string[]>
  buildCurrentWorkflowDefinition: () => WorkflowDefinition
}) {
  const {
    userStore,
    artifactsStore,
    workflowStore,
    workflowDefinitionsStore,
    editableCanvasPreset,
    projectId,
    workflowInputRequirements,
    buildCurrentWorkflowDefinition
  } = input

  const workflowName = ref('未命名流程')
  const selectedSavedWorkflowId = ref<string | undefined>()
  const workflowRunInputSelections = ref<Record<string, string | undefined>>({})
  const workflowRunAutoSyncTimer = ref<number | null>(null)

  const savedWorkflowOptions = computed(() => {
    return workflowDefinitionsStore.workflowDefinitions
      .filter(workflow => workflow.status !== 'archived')
      .map(workflow => ({
        value: workflow.id,
        label: workflow.name
      }))
  })

  const selectedWorkflowInputFiles = computed(() => {
    return buildWorkflowInputFileMap(
      workflowInputRequirements.value,
      workflowRunInputSelections.value
    )
  })

  const artifactOptionsBySemanticType = computed(() => {
    return workflowInputRequirements.value.reduce<
      Record<string, Array<{ value: string; label: string }>>
    >((accumulator, semanticType) => {
      accumulator[semanticType] = artifactsStore.items
        .filter(artifact => artifact.semantic_type === semanticType)
        .map(artifact => ({
          value: artifact.id,
          label: `${artifact.filename} · ${artifact.tool_name}`
        }))
      return accumulator
    }, {})
  })

  async function handleSaveWorkflow() {
    const payload = buildWorkflowDefinitionPayload()

    try {
      const saved = await workflowDefinitionsStore.saveWorkflowDefinition(
        payload,
        selectedSavedWorkflowId.value ?? workflowDefinitionsStore.currentWorkflowDefinition?.id
      )
      selectedSavedWorkflowId.value = saved.id
      workflowName.value = saved.name
      message.success('流程已保存')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  function handleNewWorkflow() {
    workflowStore.resetSession(userStore.user?.id)
    workflowStore.clearActiveWorkflowRun()
    workflowDefinitionsStore.clearCurrentWorkflowDefinition()
    selectedSavedWorkflowId.value = undefined
    workflowName.value = '未命名流程'
    workflowRunInputSelections.value = {}
  }

  async function handleDuplicateWorkflow() {
    const selectedWorkflow = resolveSelectedWorkflowDefinition()
    if (!selectedWorkflowIdExists()) {
      return
    }

    const name = `${workflowName.value.trim() || selectedWorkflow?.name || '未命名流程'} 副本`
    try {
      const saved = await workflowDefinitionsStore.saveWorkflowDefinition({
        ...buildWorkflowDefinitionPayload(name),
        status: 'draft'
      })
      selectedSavedWorkflowId.value = saved.id
      workflowName.value = saved.name
      message.success('流程已复制')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  async function handleArchiveWorkflow() {
    if (!selectedWorkflowIdExists()) {
      return
    }

    try {
      await workflowDefinitionsStore.archiveWorkflowDefinition(selectedSavedWorkflowId.value!)
      handleNewWorkflow()
      message.success('流程已归档')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  async function handleDeleteWorkflow() {
    if (!selectedWorkflowIdExists()) {
      return
    }

    try {
      await workflowDefinitionsStore.removeWorkflowDefinition(selectedSavedWorkflowId.value!)
      handleNewWorkflow()
      message.success('流程已删除')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  function applyWorkflowDraft(draft: AiddWorkflowDraft) {
    workflowDefinitionsStore.clearCurrentWorkflowDefinition()
    selectedSavedWorkflowId.value = undefined
    workflowName.value = draft.name
    workflowRunInputSelections.value = { ...draft.input_files }
    workflowStore.applyWorkflowDefinition(
      mapWorkflowDefinitionToCanvasPayload({
        canvasPresetId: 'aidd-workflow-draft',
        name: draft.name,
        description: draft.description,
        definition: draft.definition
      })
    )
  }

  async function saveWorkflowDraft(draft: AiddWorkflowDraft, projectId: string) {
    const canvasPayload = mapWorkflowDefinitionToCanvasPayload({
      canvasPresetId: 'aidd-workflow-draft',
      name: draft.name,
      description: draft.description,
      definition: draft.definition
    })

    const saved = await workflowDefinitionsStore.saveWorkflowDefinition({
      project_id: projectId,
      name: draft.name,
      description: draft.description ?? null,
      canvas_preset_id: canvasPayload.canvas_preset_id,
      nodes: canvasPayload.nodes,
      edges: canvasPayload.edges,
      selected_tool_by_node: canvasPayload.selected_tool_by_node,
      artifact_bindings_by_node: canvasPayload.artifact_bindings_by_node,
      status: 'draft'
    })

    selectedSavedWorkflowId.value = saved.id
    workflowName.value = saved.name
    workflowRunInputSelections.value = { ...draft.input_files }
    workflowStore.applyWorkflowDefinition(saved)
    message.success('工作流草稿已保存')
    return saved
  }

  async function handleRunWorkflowDefinition() {
    const definition = buildCurrentWorkflowDefinition()
    const validationResult = validateWorkflowDefinition(definition)
    const executionValidationResult = validateWorkflowExecutionOrder(definition)
    if (!validationResult.valid || !executionValidationResult.valid) {
      message.warning(validationResult.message ?? executionValidationResult.message)
      return
    }

    const saved = await workflowDefinitionsStore.saveWorkflowDefinition(
      buildWorkflowDefinitionPayload(workflowName.value.trim() || '未命名流程'),
      selectedSavedWorkflowId.value ?? workflowDefinitionsStore.currentWorkflowDefinition?.id
    )
    selectedSavedWorkflowId.value = saved.id
    workflowName.value = saved.name

    const run = await workflowStore.runWorkflowDefinition(saved.id, {
      name: saved.name,
      input_files: selectedWorkflowInputFiles.value
    })
    await workflowStore.loadWorkflowRuns({
      ...(projectId?.value ? { project_id: projectId.value } : {}),
      workflow_definition_id: saved.id,
      page: 1,
      page_size: 20
    })
    await workflowStore.loadWorkflowRun(run.id)
  }

  async function handleRefreshWorkflowRuns() {
    const workflowDefinitionId = selectedSavedWorkflowId.value ?? undefined
    await workflowStore.loadWorkflowRuns({
      ...(projectId?.value ? { project_id: projectId.value } : {}),
      workflow_definition_id: workflowDefinitionId,
      page: 1,
      page_size: 20
    })
  }

  async function handleLoadMoreWorkflowRuns() {
    const workflowDefinitionId = selectedSavedWorkflowId.value ?? undefined
    if (!workflowStore.hasMoreWorkflowRuns) {
      return
    }
    await workflowStore.loadWorkflowRuns(
      {
        ...(projectId?.value ? { project_id: projectId.value } : {}),
        workflow_definition_id: workflowDefinitionId,
        page: workflowStore.workflowRunsPagination.page + 1,
        page_size: workflowStore.workflowRunsPagination.pageSize
      },
      { append: true }
    )
  }

  async function handleWorkflowRunSelect(runId: string) {
    await workflowStore.loadWorkflowRun(runId)
    await scheduleWorkflowRunAutoSync()
  }

  async function handleSyncWorkflowRun() {
    await workflowStore.syncActiveWorkflowRun()
  }

  async function autofillWorkflowInputSelections() {
    const nextSelections: Record<string, string | undefined> = {}
    for (const semanticType of workflowInputRequirements.value) {
      const artifact = findLatestArtifactForSemanticType(artifactsStore.items, semanticType)
      nextSelections[semanticType] = artifact?.id
    }
    workflowRunInputSelections.value = nextSelections
  }

  function handleWorkflowInputSelect(semanticType: string, artifactId: string | undefined) {
    workflowRunInputSelections.value = {
      ...workflowRunInputSelections.value,
      [semanticType]: artifactId
    }
  }

  async function scheduleWorkflowRunAutoSync() {
    clearWorkflowRunAutoSync()
    const run = workflowStore.activeWorkflowRun
    if (
      !shouldAutoSyncWorkflowRun(run, {
        isLoggedIn: userStore.isLoggedIn,
        isLoading: workflowStore.isLoadingWorkflowRun,
        isSyncing: workflowStore.isSyncingWorkflowRun
      })
    ) {
      return
    }

    workflowRunAutoSyncTimer.value = window.setInterval(async () => {
      await workflowStore.syncActiveWorkflowRun()
    }, 5000)
  }

  function clearWorkflowRunAutoSync() {
    if (workflowRunAutoSyncTimer.value !== null) {
      window.clearInterval(workflowRunAutoSyncTimer.value)
      workflowRunAutoSyncTimer.value = null
    }
  }

  async function restoreActiveWorkflowRun() {
    if (!userStore.authReady || !userStore.isLoggedIn || !workflowStore.activeWorkflowRunId) {
      return
    }
    await workflowStore.loadWorkflowRun(workflowStore.activeWorkflowRunId)
  }

  async function handleLoadWorkflow() {
    if (!selectedSavedWorkflowId.value) {
      return
    }

    try {
      const workflow = await workflowDefinitionsStore.loadWorkflowDefinition(
        selectedSavedWorkflowId.value
      )
      workflowStore.applyWorkflowDefinition(workflow)
      workflowName.value = workflow.name
      message.success('流程已加载')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  function buildWorkflowDefinitionPayload(nameOverride?: string): WorkflowDefinitionPayload {
    return {
      ...(projectId?.value ? { project_id: projectId.value } : {}),
      name: nameOverride ?? (workflowName.value.trim() || '未命名流程'),
      canvas_preset_id: editableCanvasPreset.value.id,
      nodes: workflowStore.exportWorkflowNodes(editableCanvasPreset.value.nodes),
      edges: workflowStore.exportWorkflowEdges(editableCanvasPreset.value.edges),
      selected_tool_by_node: workflowStore.selectedToolByNode,
      artifact_bindings_by_node: workflowStore.artifactBindingsByNode,
      status: 'draft'
    }
  }

  function selectedWorkflowIdExists(): boolean {
    return (
      typeof selectedSavedWorkflowId.value === 'string' && Boolean(selectedSavedWorkflowId.value)
    )
  }

  function resolveSelectedWorkflowDefinition() {
    return workflowDefinitionsStore.workflowDefinitions.find(
      workflow => workflow.id === selectedSavedWorkflowId.value
    )
  }

  return {
    workflowName,
    selectedSavedWorkflowId,
    workflowRunInputSelections,
    workflowRunAutoSyncTimer,
    savedWorkflowOptions,
    selectedWorkflowInputFiles,
    artifactOptionsBySemanticType,
    handleSaveWorkflow,
    handleNewWorkflow,
    handleDuplicateWorkflow,
    handleArchiveWorkflow,
    handleDeleteWorkflow,
    applyWorkflowDraft,
    saveWorkflowDraft,
    handleRunWorkflowDefinition,
    handleRefreshWorkflowRuns,
    handleLoadMoreWorkflowRuns,
    handleWorkflowRunSelect,
    handleSyncWorkflowRun,
    autofillWorkflowInputSelections,
    handleWorkflowInputSelect,
    scheduleWorkflowRunAutoSync,
    clearWorkflowRunAutoSync,
    restoreActiveWorkflowRun,
    handleLoadWorkflow
  }
}

export function mapWorkflowDefinitionToCanvasPayload(input: {
  canvasPresetId: string
  name: string
  description?: string | null
  definition: WorkflowDefinition
}) {
  const { canvasPresetId, name, description, definition } = input
  return {
    canvas_preset_id: canvasPresetId,
    name,
    description: description ?? undefined,
    nodes: (definition.nodes ?? []).map(node => mapCanvasDefinitionNode(node)),
    edges: (definition.edges ?? []).map((edge, index) => ({
      id: resolveWorkflowEdgeId(edge.id, index),
      source: edge.source,
      target: edge.target,
      artifactType: edge.source_output ?? edge.target_input
    })),
    selected_tool_by_node: Object.fromEntries(
      definition.nodes
        .filter(node => node.kind === 'tool' && node.tool_slug)
        .map(node => [node.id, node.tool_slug as string])
    ),
    artifact_bindings_by_node: {},
    status: 'draft' as const
  }
}

function mapCanvasDefinitionNode(node: WorkflowDefinitionNode) {
  const inputArtifactSlots = Array.isArray(node.artifact_input_slots)
    ? node.artifact_input_slots
    : []
  const outputArtifactSlots = Array.isArray(node.artifact_outputs) ? node.artifact_outputs : []
  const inputSlotTypes = resolveArtifactSlotTypes(inputArtifactSlots)
  const outputSlotTypes = resolveArtifactSlotTypes(outputArtifactSlots)

  return {
    id: node.id,
    type: node.kind === 'input' ? 'input' : 'tool',
    titleKey: node.tool_slug || node.semantic_type || node.id,
    descriptionKey: node.tool_slug || node.semantic_type || node.id,
    position: resolveWorkflowNodePosition(node),
    toolSlugs: node.tool_slug ? [node.tool_slug] : [],
    recommendedToolSlug: node.tool_slug ?? undefined,
    requiredInputTypes:
      node.kind === 'input' && node.semantic_type
        ? [node.semantic_type]
        : inputSlotTypes.length
          ? inputSlotTypes
          : Object.keys(node.semantic_inputs ?? {}),
    producedOutputTypes: outputSlotTypes.length
      ? outputSlotTypes
      : Array.isArray(node.semantic_outputs)
        ? node.semantic_outputs
        : [],
    inputArtifactSlots,
    outputArtifactSlots
  }
}

function resolveArtifactSlotTypes(slots: unknown[]): WorkflowArtifactSemanticType[] {
  const types = new Set<WorkflowArtifactSemanticType>()

  for (const slot of slots) {
    if (!slot || typeof slot !== 'object' || !('type' in slot)) {
      continue
    }
    const type = (slot as { type?: unknown }).type
    if (
      typeof type === 'string' &&
      WORKFLOW_ARTIFACT_SEMANTIC_TYPES.includes(type as WorkflowArtifactSemanticType)
    ) {
      types.add(type as WorkflowArtifactSemanticType)
    }
  }

  return [...types]
}

function resolveWorkflowNodePosition(node: WorkflowDefinitionNode) {
  const position = node.position
  if (
    position &&
    typeof position === 'object' &&
    'x' in position &&
    'y' in position &&
    typeof position.x === 'number' &&
    typeof position.y === 'number'
  ) {
    return {
      x: position.x,
      y: position.y
    }
  }

  return { x: 0, y: 0 }
}

function resolveWorkflowEdgeId(edgeId: unknown, index: number): string {
  return typeof edgeId === 'string' && edgeId ? edgeId : `edge-${index}`
}
