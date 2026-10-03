import { computed, ref, watch, type ComputedRef } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { getTaskDetail } from '@/api/tasks'
import { getProjectArtifacts, uploadProjectArtifact } from '@/api/artifacts'
import { uploadFile } from '@/api/files'
import type { WorkflowDefinitionPayload } from '@/api/workflows'
import { deriveArtifactSlotsFromToolContract } from '@/workflow/contract-bindings'
import {
  buildWorkflowInputFileMap,
  findLatestArtifactForSemanticType
} from '@/workflow/workflow-definitions'
import { buildWorkflowRunListParams } from '@/workflow/project-context'
import { shouldAutoSyncWorkflowRun } from '@/workflow/workflow-runs'
import { resolveWorkflowControlNodeTitleKey } from '@/workflow/control-nodes'
import {
  validateWorkflowDefinition,
  validateWorkflowExecutionOrder
} from '@/workflow/canvas-runner'
import { type WorkflowArtifactSemanticType, type WorkflowTaskRef } from '@/workflow/artifact-types'
import { isWorkflowSemanticType, normalizeWorkflowSemanticType } from '@/workflow/semantic-types'
import type { TypedArtifact } from '@/types/artifacts'
import type {
  WorkflowCanvasEdge,
  WorkflowCanvasNode,
  WorkflowConditionExpression
} from '@/workflow/canvas-types'
import {
  useArtifactsStore,
  useUserStore,
  useWorkflowDefinitionsStore,
  useWorkflowStore
} from '@/stores'
import type { AiddWorkflowDraft, ToolContract, WorkflowDefinition, WorkflowDefinitionNode, WorkflowRun } from '@/types/models'

type UserStore = ReturnType<typeof useUserStore>
type ArtifactsStore = ReturnType<typeof useArtifactsStore>
type WorkflowStore = ReturnType<typeof useWorkflowStore>
type WorkflowDefinitionsStore = ReturnType<typeof useWorkflowDefinitionsStore>
type WorkflowToolContractLookup = Record<string, {
  name?: string
  description?: string
  contract?: ToolContract | null
} | undefined>

export interface WorkflowPersistenceLabels {
  untitledWorkflow: string
  duplicateName: (name: string) => string
  saved: string
  duplicated: string
  archived: string
  deleted: string
  draftSaved: string
  runCanceled: string
  nodeRetried: string
  loaded: string
  discardUnsavedTitle: string
  discardUnsavedContent: string
  discardUnsavedConfirm: string
  discardUnsavedCancel: string
  missingInputs: (inputs: string[]) => string
}

const DEFAULT_WORKFLOW_PERSISTENCE_LABELS: WorkflowPersistenceLabels = {
  untitledWorkflow: 'Untitled Workflow',
  duplicateName: name => `${name} Copy`,
  saved: 'Workflow saved',
  duplicated: 'Workflow duplicated',
  archived: 'Workflow archived',
  deleted: 'Workflow deleted',
  draftSaved: 'Workflow draft saved',
  runCanceled: 'Workflow run canceled',
  nodeRetried: 'Workflow node retried',
  loaded: 'Workflow loaded',
  discardUnsavedTitle: 'Unsaved workflow changes',
  discardUnsavedContent: 'Discard the current workflow edits?',
  discardUnsavedConfirm: 'Discard changes',
  discardUnsavedCancel: 'Continue editing',
  missingInputs: inputs => `Select required inputs first: ${inputs.join(', ')}`,
}

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
  workflowToolsBySlug?: ComputedRef<WorkflowToolContractLookup>
  buildCurrentWorkflowDefinition: () => WorkflowDefinition
  labels?: ComputedRef<WorkflowPersistenceLabels>
}) {
  const {
    userStore,
    artifactsStore,
    workflowStore,
    workflowDefinitionsStore,
    editableCanvasPreset,
    projectId,
    workflowInputRequirements,
    workflowToolsBySlug,
    buildCurrentWorkflowDefinition
  } = input

  const persistenceLabels = computed(() => input.labels?.value ?? DEFAULT_WORKFLOW_PERSISTENCE_LABELS)
  const workflowName = ref(persistenceLabels.value.untitledWorkflow)
  const selectedSavedWorkflowId = ref<string | undefined>()
  const workflowRunInputSelections = ref<Record<string, string | undefined>>({})
  const projectWorkflowArtifacts = ref<TypedArtifact[]>([])
  const projectWorkflowArtifactsLoading = ref(false)
  const uploadingWorkflowInputKey = ref<string | null>(null)
  const workflowRunAutoSyncTimer = ref<number | null>(null)
  const cleanWorkflowSignature = ref('')
  const router = useRouter()

  function currentWorkflowSignature(): string {
    const definition = buildCurrentWorkflowDefinition()
    return JSON.stringify({
      name: workflowName.value,
      canvas_preset_id: editableCanvasPreset.value.id,
      nodes: definition.nodes,
      edges: definition.edges,
      selected_tool_by_node: workflowStore.selectedToolByNode,
      artifact_bindings_by_node: workflowStore.artifactBindingsByNode,
    })
  }

  const hasUnsavedWorkflowChanges = computed(
    () => currentWorkflowSignature() !== cleanWorkflowSignature.value
  )

  function markWorkflowClean() {
    cleanWorkflowSignature.value = currentWorkflowSignature()
  }

  async function confirmDiscardWorkflowChanges(): Promise<boolean> {
    if (!hasUnsavedWorkflowChanges.value) return true
    return await new Promise(resolve => {
      Modal.confirm({
        title: persistenceLabels.value.discardUnsavedTitle,
        content: persistenceLabels.value.discardUnsavedContent,
        okText: persistenceLabels.value.discardUnsavedConfirm,
        okType: 'danger',
        cancelText: persistenceLabels.value.discardUnsavedCancel,
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
  }

  const savedWorkflowOptions = computed(() => {
    return workflowDefinitionsStore.workflowDefinitions
      .filter(workflow => workflow.status !== 'archived')
      .map(workflow => ({
        value: workflow.id,
        label: workflow.name
      }))
  })

  if (!workflowStore.hasCanvasOverride) {
    markWorkflowClean()
  }

  const selectedWorkflowInputFiles = computed(() => {
    return buildWorkflowInputFileMap(
      workflowInputRequirements.value,
      workflowRunInputSelections.value
    )
  })

  const workflowInputOptionsLoading = computed(() =>
    projectId?.value ? projectWorkflowArtifactsLoading.value : artifactsStore.loading
  )
  const hasWorkflowInputOptions = computed(() =>
    Object.values(artifactOptionsBySemanticType.value).some(options => options.length > 0)
  )

  const artifactOptionsBySemanticType = computed(() => {
    return workflowInputRequirements.value.reduce<
      Record<string, Array<{ value: string; label: string }>>
    >((accumulator, semanticType) => {
      if (projectId?.value) {
        accumulator[semanticType] = projectWorkflowArtifacts.value
          .filter(artifact => isProjectArtifactUsableForInput(artifact, semanticType))
          .map(artifact => ({
            value: `artifact_version:${artifact.latest_version.id}`,
            label: `${artifact.name} · v${artifact.latest_version.version}`
          }))
      } else {
        accumulator[semanticType] = artifactsStore.items
          .filter(artifact => artifact.semantic_type === semanticType)
          .map(artifact => ({
            value: artifact.id,
            label: `${artifact.filename} · ${artifact.tool_name}`
          }))
      }
      return accumulator
    }, {})
  })

  let artifactRequestId = 0
  async function loadProjectWorkflowArtifacts() {
    const requestId = ++artifactRequestId
    const currentProjectId = projectId?.value
    if (!currentProjectId || !userStore.isLoggedIn) {
      projectWorkflowArtifacts.value = []
      projectWorkflowArtifactsLoading.value = false
      return
    }

    projectWorkflowArtifactsLoading.value = true
    try {
      const response = await getProjectArtifacts(currentProjectId)
      if (requestId === artifactRequestId) {
        projectWorkflowArtifacts.value = response.data.items
      }
    } catch {
      if (requestId === artifactRequestId) {
        projectWorkflowArtifacts.value = []
      }
    } finally {
      if (requestId === artifactRequestId) {
        projectWorkflowArtifactsLoading.value = false
      }
    }
  }

  watch(
    () => [projectId?.value, userStore.isLoggedIn] as const,
    () => void loadProjectWorkflowArtifacts(),
    { immediate: true }
  )

  async function handleSaveWorkflow() {
    const payload = buildWorkflowDefinitionPayload()

    try {
      const saved = await workflowDefinitionsStore.saveWorkflowDefinition(
        payload,
        selectedSavedWorkflowId.value ?? workflowDefinitionsStore.currentWorkflowDefinition?.id
      )
      selectedSavedWorkflowId.value = saved.id
      workflowName.value = saved.name
      markWorkflowClean()
      message.success(persistenceLabels.value.saved)
    } catch {
      // Request layer displays error details.
    }
  }

  function resetToNewWorkflow() {
    workflowStore.resetSession(userStore.user?.id)
    workflowStore.clearActiveWorkflowRun()
    workflowDefinitionsStore.clearCurrentWorkflowDefinition()
    selectedSavedWorkflowId.value = undefined
    workflowName.value = persistenceLabels.value.untitledWorkflow
    workflowRunInputSelections.value = {}
    markWorkflowClean()
  }

  async function handleNewWorkflow() {
    if (!await confirmDiscardWorkflowChanges()) return
    resetToNewWorkflow()
  }

  async function handleDuplicateWorkflow() {
    const selectedWorkflow = resolveSelectedWorkflowDefinition()
    if (!selectedWorkflowIdExists()) {
      return
    }

    const name = persistenceLabels.value.duplicateName(
      workflowName.value.trim() || selectedWorkflow?.name || persistenceLabels.value.untitledWorkflow
    )
    try {
      const saved = await workflowDefinitionsStore.saveWorkflowDefinition({
        ...buildWorkflowDefinitionPayload(name),
        status: 'draft'
      })
      selectedSavedWorkflowId.value = saved.id
      workflowName.value = saved.name
      markWorkflowClean()
      message.success(persistenceLabels.value.duplicated)
    } catch {
      // Request layer displays error details.
    }
  }

  async function handleArchiveWorkflow() {
    if (!selectedWorkflowIdExists() || !await confirmDiscardWorkflowChanges()) {
      return
    }

    try {
      await workflowDefinitionsStore.archiveWorkflowDefinition(selectedSavedWorkflowId.value!)
      resetToNewWorkflow()
      message.success(persistenceLabels.value.archived)
    } catch {
      // Request layer displays error details.
    }
  }

  async function handleDeleteWorkflow() {
    if (!selectedWorkflowIdExists() || !await confirmDiscardWorkflowChanges()) {
      return
    }

    try {
      await workflowDefinitionsStore.removeWorkflowDefinition(selectedSavedWorkflowId.value!)
      resetToNewWorkflow()
      message.success(persistenceLabels.value.deleted)
    } catch {
      // Request layer displays error details.
    }
  }

  async function applyWorkflowDraft(draft: AiddWorkflowDraft) {
    if (!await confirmDiscardWorkflowChanges()) return
    workflowDefinitionsStore.clearCurrentWorkflowDefinition()
    selectedSavedWorkflowId.value = undefined
    workflowName.value = draft.name
    workflowRunInputSelections.value = { ...draft.input_files }
    workflowStore.applyWorkflowDefinition(
      mapWorkflowDefinitionToCanvasPayload({
        canvasPresetId: 'aidd-workflow-draft',
        name: draft.name,
        description: draft.description,
        definition: draft.definition,
        toolsBySlug: workflowToolsBySlug?.value,
      })
    )
  }

  async function saveWorkflowDraft(draft: AiddWorkflowDraft, projectId: string) {
    if (!await confirmDiscardWorkflowChanges()) return
    const canvasPayload = mapWorkflowDefinitionToCanvasPayload({
      canvasPresetId: 'aidd-workflow-draft',
      name: draft.name,
      description: draft.description,
      definition: draft.definition,
      toolsBySlug: workflowToolsBySlug?.value,
    })

    const saved = await workflowDefinitionsStore.saveWorkflowDefinition({
      project_id: projectId,
      name: draft.name,
      description: draft.description ?? null,
      canvas_preset_id: canvasPayload.canvas_preset_id,
      nodes: canvasPayload.nodes as unknown as WorkflowDefinitionPayload['nodes'],
      edges: canvasPayload.edges,
      selected_tool_by_node: canvasPayload.selected_tool_by_node,
      artifact_bindings_by_node: canvasPayload.artifact_bindings_by_node,
      task_bindings_by_node: {},
      status: 'draft'
    })

    selectedSavedWorkflowId.value = saved.id
    workflowName.value = saved.name
    workflowRunInputSelections.value = { ...draft.input_files }
    workflowStore.applyWorkflowDefinition(
      mapWorkflowDefinitionToCanvasPayload({
        canvasPresetId: saved.canvas_preset_id,
        name: saved.name,
        description: saved.description,
        definition: saved as unknown as WorkflowDefinition,
        toolsBySlug: workflowToolsBySlug?.value,
      })
    )
    markWorkflowClean()
    message.success(persistenceLabels.value.draftSaved)
    return saved
  }

  async function handleRunWorkflowDefinition() {
    const missingInputs = workflowInputRequirements.value.filter(
      semanticType => !selectedWorkflowInputFiles.value[semanticType]
    )
    if (missingInputs.length) {
      message.warning(persistenceLabels.value.missingInputs(missingInputs))
      return
    }

    const definition = buildCurrentWorkflowDefinition()
    const validationResult = validateWorkflowDefinition(definition)
    const executionValidationResult = validateWorkflowExecutionOrder(definition)
    if (!validationResult.valid || !executionValidationResult.valid) {
      message.warning(validationResult.message ?? executionValidationResult.message)
      return
    }

    try {
      const saved = await workflowDefinitionsStore.saveWorkflowDefinition(
        buildWorkflowDefinitionPayload(workflowName.value.trim() || persistenceLabels.value.untitledWorkflow),
        selectedSavedWorkflowId.value ?? workflowDefinitionsStore.currentWorkflowDefinition?.id
      )
      selectedSavedWorkflowId.value = saved.id
      workflowName.value = saved.name
      markWorkflowClean()

      const run = await workflowStore.runWorkflowDefinition(saved.id, {
        name: saved.name,
        input_files: selectedWorkflowInputFiles.value
      })
      await workflowStore.loadWorkflowRuns(
        buildWorkflowRunListParams({
          projectId: projectId?.value,
          workflowDefinitionId: saved.id,
          page: 1,
          pageSize: 20
        })
      )
      await workflowStore.loadWorkflowRun(run.id)
    } catch {
      // 请求层已经展示具体错误。
    }
  }

  async function handleRefreshWorkflowRuns() {
    const workflowDefinitionId = selectedSavedWorkflowId.value ?? undefined
    await workflowStore.loadWorkflowRuns(
      buildWorkflowRunListParams({
        projectId: projectId?.value,
        workflowDefinitionId,
        page: 1,
        pageSize: 20
      })
    )
  }

  async function handleLoadMoreWorkflowRuns() {
    const workflowDefinitionId = selectedSavedWorkflowId.value ?? undefined
    if (!workflowStore.hasMoreWorkflowRuns) {
      return
    }
    await workflowStore.loadWorkflowRuns(
      buildWorkflowRunListParams({
        projectId: projectId?.value,
        workflowDefinitionId,
        page: workflowStore.workflowRunsPagination.page + 1,
        pageSize: workflowStore.workflowRunsPagination.pageSize
      }),
      { append: true }
    )
  }

  async function handleWorkflowRunSelect(runId: string) {
    const run = await workflowStore.loadWorkflowRun(runId)
    await restoreNodeTasksFromWorkflowRun(run)
    await scheduleWorkflowRunAutoSync()
  }

  async function handleSyncWorkflowRun() {
    try {
      const run = await workflowStore.syncActiveWorkflowRun()
      if (run) {
        await restoreNodeTasksFromWorkflowRun(run)
      }
    } catch {
      // 请求层已经展示具体错误。
    }
  }

  async function handleCancelWorkflowRun() {
    try {
      const run = await workflowStore.cancelActiveWorkflowRun()
      if (run) {
        await restoreNodeTasksFromWorkflowRun(run)
      }
      clearWorkflowRunAutoSync()
      message.success(persistenceLabels.value.runCanceled)
    } catch {
      // 请求层已经展示具体错误。
    }
  }

  async function handleRetryWorkflowRunNode(nodeId: string) {
    const runId = workflowStore.activeWorkflowRunId
    if (!runId) {
      return
    }
    try {
      const run = await workflowStore.retryWorkflowRunNode(runId, nodeId)
      if (run) {
        await restoreNodeTasksFromWorkflowRun(run)
      }
      await scheduleWorkflowRunAutoSync()
      message.success(persistenceLabels.value.nodeRetried)
    } catch {
      // 请求层已经展示具体错误。
    }
  }

  function handleWorkflowRunDetail(runId: string) {
    router.push({ name: 'WorkflowRunDetail', params: { runId } })
  }

  async function autofillWorkflowInputSelections() {
    const nextSelections: Record<string, string | undefined> = {}
    for (const semanticType of workflowInputRequirements.value) {
      if (projectId?.value) {
        const artifact = [...projectWorkflowArtifacts.value]
          .filter(item => isProjectArtifactUsableForInput(item, semanticType))
          .sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0]
        nextSelections[semanticType] = artifact
          ? `artifact_version:${artifact.latest_version.id}`
          : undefined
      } else {
        const artifact = findLatestArtifactForSemanticType(artifactsStore.items, semanticType)
        nextSelections[semanticType] = artifact?.id
      }
    }
    workflowRunInputSelections.value = nextSelections
  }

  function handleWorkflowInputSelect(semanticType: string, artifactId: string | undefined) {
    workflowRunInputSelections.value = {
      ...workflowRunInputSelections.value,
      [semanticType]: artifactId
    }
  }

  async function handleWorkflowInputUpload(semanticType: string, file: File) {
    uploadingWorkflowInputKey.value = semanticType
    try {
      if (projectId?.value) {
        const normalizedType = normalizeWorkflowSemanticType(semanticType)
        const standardMatch = /^([a-z][a-z0-9_]*)@(\d+)$/.exec(normalizedType)
        const baseSemanticType = semanticType.split('@')[0] ?? semanticType
        const artifact = await uploadProjectArtifact(projectId.value, {
          file,
          artifact_type: standardMatch?.[1] ?? 'file',
          semantic_type: baseSemanticType,
          ...(standardMatch
            ? { standard_type: standardMatch[1], standard_version: Number(standardMatch[2]) }
            : {}),
        })
        await loadProjectWorkflowArtifacts()
        handleWorkflowInputSelect(
          semanticType,
          `artifact_version:${artifact.data.latest_version.id}`
        )
      } else {
        const uploaded = await uploadFile(file)
        handleWorkflowInputSelect(semanticType, uploaded.data.id)
      }
    } catch {
      // The request layer displays upload errors.
    } finally {
      uploadingWorkflowInputKey.value = null
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
      if (workflowStore.isSyncingWorkflowRun || workflowStore.isLoadingWorkflowRun) {
        return
      }
      try {
        const run = await workflowStore.syncActiveWorkflowRun()
        if (!run) {
          return
        }
        await restoreNodeTasksFromWorkflowRun(run)
        if (['success', 'failure', 'canceled'].includes(run.status)) {
          await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
          clearWorkflowRunAutoSync()
        }
      } catch {
        clearWorkflowRunAutoSync()
      }
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
    const run = await workflowStore.loadWorkflowRun(workflowStore.activeWorkflowRunId)
    await restoreNodeTasksFromWorkflowRun(run)
  }

  async function handleLoadWorkflow() {
    if (!selectedSavedWorkflowId.value || !await confirmDiscardWorkflowChanges()) {
      return
    }

    try {
      const sessionTaskBindings = buildNodeTaskSnapshot(workflowStore.taskByNode)
      const workflow = await workflowDefinitionsStore.loadWorkflowDefinition(
        selectedSavedWorkflowId.value
      )
      workflowStore.applyWorkflowDefinition(
        mapWorkflowDefinitionToCanvasPayload({
          canvasPresetId: workflow.canvas_preset_id,
          name: workflow.name,
          description: workflow.description,
          definition: workflow as unknown as WorkflowDefinition,
          toolsBySlug: workflowToolsBySlug?.value,
        })
      )
      workflowName.value = workflow.name
      markWorkflowClean()
      const restoredFromDefinition = await restoreNodeTasksFromWorkflowDefinition(workflow)
      if (restoredFromDefinition === 0) {
        await restoreNodeTasksFromTaskBindings(sessionTaskBindings, workflow)
      }
      await tryRestoreLatestWorkflowRunForDefinition(workflow.id)
      message.success(persistenceLabels.value.loaded)
    } catch {
      // Request layer displays error details.
    }
  }

  async function tryRestoreLatestWorkflowRunForDefinition(workflowDefinitionId: string) {
    try {
      await restoreLatestWorkflowRunForDefinition(workflowDefinitionId)
    } catch {
      // The workflow definition is already loaded; run restore failures should not clear the canvas.
    }
  }

  async function restoreLatestWorkflowRunForDefinition(workflowDefinitionId: string) {
    workflowStore.clearActiveWorkflowRun()

    const runPage = await workflowStore.loadWorkflowRuns(
      buildWorkflowRunListParams({
        projectId: projectId?.value,
        workflowDefinitionId,
        page: 1,
        pageSize: 20
      })
    )
    const latestRun = Array.isArray(runPage?.items) ? runPage.items[0] : undefined
    if (!latestRun?.id) {
      return
    }

    const run = await workflowStore.loadWorkflowRun(latestRun.id)
    await restoreNodeTasksFromWorkflowRun(run)
    await scheduleWorkflowRunAutoSync()
  }

  async function restoreNodeTasksFromWorkflowRun(run: WorkflowRun) {
    workflowRunInputSelections.value = normalizeWorkflowInputSelections(run.input_files)

    const taskRequests = Object.entries(run.node_states ?? {})
      .map(([nodeId, state]) => ({ nodeId, taskId: state?.task_id }))
      .filter((entry): entry is { nodeId: string; taskId: string } => Boolean(entry.taskId))

    return await restoreNodeTasks(taskRequests)
  }

  async function restoreNodeTasksFromWorkflowDefinition(workflow: WorkflowDefinitionPayload | WorkflowDefinition) {
    return await restoreNodeTasksFromTaskBindings(workflow.task_bindings_by_node, workflow)
  }

  async function restoreNodeTasksFromTaskBindings(
    taskBindings: unknown,
    workflow: WorkflowDefinitionPayload | WorkflowDefinition,
  ) {
    const nodeIds = new Set((workflow.nodes ?? []).map(node => String(node.id)))
    const taskRequests = Object.entries(normalizeTaskBindings(taskBindings))
      .filter(([nodeId]) => nodeIds.has(nodeId))
      .map(([nodeId, taskId]) => ({ nodeId, taskId }))

    return await restoreNodeTasks(taskRequests)
  }

  async function restoreNodeTasks(taskRequests: Array<{ nodeId: string; taskId: string }>) {
    if (taskRequests.length === 0) {
      return 0
    }

    const uniqueTaskIds = Array.from(new Set(taskRequests.map((entry) => entry.taskId)))

    const taskResults = await Promise.allSettled(
      uniqueTaskIds.map(async (taskId) => {
        const response = await getTaskDetail(taskId, { silent: true })
        return { taskId, task: response.data }
      })
    )

    const taskById = new Map<string, WorkflowTaskRef>()

    for (const result of taskResults) {
      if (result.status === 'fulfilled') {
        taskById.set(result.value.taskId, result.value.task)
      }
    }

    let restoredCount = 0
    for (const { nodeId, taskId } of taskRequests) {
      const task = taskById.get(taskId)
      if (task) {
        workflowStore.recordNodeTask(nodeId, task)
        restoredCount += 1
      }
    }
    return restoredCount
  }

  function buildWorkflowDefinitionPayload(nameOverride?: string): WorkflowDefinitionPayload {
    const definition = buildCurrentWorkflowDefinition()
    return {
      ...(projectId?.value ? { project_id: projectId.value } : {}),
      name: nameOverride ?? (workflowName.value.trim() || persistenceLabels.value.untitledWorkflow),
      canvas_preset_id: editableCanvasPreset.value.id,
      nodes: definition.nodes,
      edges: definition.edges.map((edge, index) => ({
        id: resolveWorkflowEdgeId(edge.id, index),
        ...edge,
      })),
      selected_tool_by_node: workflowStore.selectedToolByNode,
      artifact_bindings_by_node: workflowStore.artifactBindingsByNode,
      task_bindings_by_node: buildNodeTaskSnapshot(workflowStore.taskByNode),
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
    hasUnsavedWorkflowChanges,
    confirmDiscardWorkflowChanges,
    selectedWorkflowInputFiles,
    artifactOptionsBySemanticType,
    workflowInputOptionsLoading,
    hasWorkflowInputOptions,
    uploadingWorkflowInputKey,
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
    handleCancelWorkflowRun,
    handleRetryWorkflowRunNode,
    handleWorkflowRunDetail,
    autofillWorkflowInputSelections,
    handleWorkflowInputSelect,
    handleWorkflowInputUpload,
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
  toolsBySlug?: WorkflowToolContractLookup
}) {
  const { canvasPresetId, name, description, definition, toolsBySlug } = input
  const nodes = definition.nodes ?? []
  const selectedToolByNode = normalizeSelectedToolByNode(definition.selected_tool_by_node)
  return {
    canvas_preset_id: canvasPresetId,
    name,
    description: description ?? undefined,
    nodes: nodes.map(node => mapCanvasDefinitionNode(
      node,
      toolsBySlug,
      resolveWorkflowNodeToolSlug(node, selectedToolByNode)
    )),
    edges: (definition.edges ?? []).map((edge, index) => ({
      id: resolveWorkflowEdgeId(edge.id, index),
      source: edge.source,
      target: edge.target,
      artifactType: edge.source_output ?? edge.target_input,
      branch: edge.branch === 'true' || edge.branch === 'false' ? edge.branch : undefined
    })),
    selected_tool_by_node: buildSelectedToolByNode(nodes, selectedToolByNode),
    artifact_bindings_by_node: normalizeArtifactBindings(definition.artifact_bindings_by_node),
    task_bindings_by_node: normalizeTaskBindings(definition.task_bindings_by_node),
    status: 'draft' as const
  }
}

function buildSelectedToolByNode(
  nodes: WorkflowDefinitionNode[],
  selectedToolByNode: Record<string, string>,
): Record<string, string> {
  const result: Record<string, string> = {}
  for (const node of nodes) {
    const toolSlug = resolveWorkflowNodeToolSlug(node, selectedToolByNode)
    if (toolSlug) {
      result[node.id] = toolSlug
    }
  }
  return result
}

function resolveWorkflowNodeToolSlug(
  node: WorkflowDefinitionNode,
  selectedToolByNode: Record<string, string>,
): string | undefined {
  return selectedToolByNode[node.id]
    ?? stringValue(node.tool_slug)
    ?? stringValue(node.recommendedToolSlug)
    ?? stringArrayValue(node.toolSlugs)[0]
}

function buildNodeTaskSnapshot(taskByNode: Record<string, WorkflowTaskRef | undefined>): Record<string, string> {
  const snapshot: Record<string, string> = {}
  for (const [nodeId, task] of Object.entries(taskByNode ?? {})) {
    if (typeof task?.id === 'string' && task.id.trim()) {
      snapshot[nodeId] = task.id
    }
  }
  return snapshot
}

function normalizeTaskBindings(value: unknown): Record<string, string> {
  if (!value || typeof value !== 'object') {
    return {}
  }

  const bindings: Record<string, string> = {}
  for (const [nodeId, rawTaskId] of Object.entries(value)) {
    if (typeof rawTaskId === 'string' && rawTaskId.trim()) {
      bindings[nodeId] = rawTaskId
    }
  }
  return bindings
}

function normalizeWorkflowInputSelections(value: unknown): Record<string, string> {
  if (!value || typeof value !== 'object') {
    return {}
  }

  const selections: Record<string, string> = {}
  for (const [semanticType, rawFileId] of Object.entries(value)) {
    if (typeof rawFileId === 'string' && rawFileId.trim()) {
      selections[semanticType] = rawFileId
    }
  }
  return selections
}

function normalizeArtifactBindings(value: unknown): Record<string, Record<string, string>> {
  if (!value || typeof value !== 'object') {
    return {}
  }

  const bindings: Record<string, Record<string, string>> = {}
  for (const [nodeId, rawSlots] of Object.entries(value)) {
    if (!rawSlots || typeof rawSlots !== 'object') {
      continue
    }
    const slotBindings: Record<string, string> = {}
    for (const [slotName, rawBinding] of Object.entries(rawSlots)) {
      if (typeof rawBinding === 'string' && rawBinding.trim()) {
        slotBindings[slotName] = rawBinding
      }
    }
    if (Object.keys(slotBindings).length > 0) {
      bindings[nodeId] = slotBindings
    }
  }
  return bindings
}

function normalizeSelectedToolByNode(value: unknown): Record<string, string> {
  if (!value || typeof value !== 'object') {
    return {}
  }

  const selected: Record<string, string> = {}
  for (const [nodeId, rawToolSlug] of Object.entries(value)) {
    if (typeof rawToolSlug === 'string' && rawToolSlug.trim()) {
      selected[nodeId] = rawToolSlug
    }
  }
  return selected
}

function deriveWorkflowNodeArtifactSlots(
  node: WorkflowDefinitionNode,
  toolsBySlug?: WorkflowToolContractLookup,
  selectedToolSlug?: string,
) {
  const savedInputs = Array.isArray(node.artifact_input_slots) ? node.artifact_input_slots : []
  const savedOutputs = Array.isArray(node.artifact_outputs) ? node.artifact_outputs : []
  const toolSlug = selectedToolSlug ?? stringValue(node.tool_slug)
  if (!toolSlug) {
    return { inputs: savedInputs, outputs: savedOutputs }
  }

  const contract = toolsBySlug?.[toolSlug]?.contract
  const contractSlots = deriveArtifactSlotsFromToolContract(contract)
  return {
    inputs: savedInputs.length > 0 ? savedInputs : [...contractSlots.inputs],
    outputs: savedOutputs.length > 0 ? savedOutputs : [...contractSlots.outputs],
  }
}

function mapCanvasDefinitionNode(
  node: WorkflowDefinitionNode,
  toolsBySlug?: WorkflowToolContractLookup,
  selectedToolSlug?: string,
): WorkflowCanvasNode {
  const nodeKind = String(node.kind ?? node.type ?? '')
  if (['condition', 'map', 'loop'].includes(nodeKind)) {
    return {
      id: node.id,
      type: nodeKind as WorkflowCanvasNode['type'],
      titleKey: stringValue(node.titleKey) ?? resolveWorkflowControlNodeTitleKey(nodeKind),
      descriptionKey: stringValue(node.descriptionKey),
      position: resolveWorkflowNodePosition(node),
      expression: conditionExpressionValue(node.expression),
      over: stringValue(node.over),
      max_parallelism: numberValue(node.max_parallelism),
      body: Array.isArray(node.body)
        ? node.body.map(item => mapCanvasDefinitionNode(item as WorkflowDefinitionNode, toolsBySlug))
        : undefined,
      max_iterations: numberValue(node.max_iterations),
      convergence_condition: conditionExpressionValue(node.convergence_condition),
    }
  }

  const toolSlug = selectedToolSlug ?? stringValue(node.tool_slug)
  const toolSlugs = toolSlug
    ? Array.from(new Set([toolSlug, ...stringArrayValue(node.toolSlugs)]))
    : stringArrayValue(node.toolSlugs)
  const tool = toolSlug ? toolsBySlug?.[toolSlug] : undefined
  const toolName = stringValue(tool?.name)
  const toolDescription = stringValue(tool?.description)
  const hydratedSlots = deriveWorkflowNodeArtifactSlots(node, toolsBySlug, toolSlug)
  const inputArtifactSlots = hydratedSlots.inputs
  const outputArtifactSlots = hydratedSlots.outputs
  const inputSlotTypes = resolveArtifactSlotTypes(inputArtifactSlots)
  const outputSlotTypes = resolveArtifactSlotTypes(outputArtifactSlots)

  return {
    id: node.id,
    type: node.kind === 'input' ? 'input' : 'tool',
    titleKey: toolName || toolSlug || node.semantic_type || node.id,
    descriptionKey: toolDescription || toolName || toolSlug || node.semantic_type || node.id,
    position: resolveWorkflowNodePosition(node),
    toolSlugs,
    recommendedToolSlug: toolSlug,
    requiredInputTypes:
      node.kind === 'input' && node.semantic_type
        ? [node.semantic_type as WorkflowArtifactSemanticType]
        : inputSlotTypes.length
          ? inputSlotTypes
          : Object.keys(node.semantic_inputs ?? {}) as WorkflowArtifactSemanticType[],
    producedOutputTypes: outputSlotTypes.length
      ? outputSlotTypes
      : Array.isArray(node.semantic_outputs)
        ? node.semantic_outputs as WorkflowArtifactSemanticType[]
        : [],
    inputArtifactSlots,
    outputArtifactSlots
  }
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined
}

function stringArrayValue(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
    : []
}

function numberValue(value: unknown): number | undefined {
  return typeof value === 'number' ? value : undefined
}

function conditionExpressionValue(value: unknown): WorkflowConditionExpression | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return undefined
  }
  const expression = value as Partial<WorkflowConditionExpression>
  return typeof expression.op === 'string' && 'left' in expression && 'right' in expression
    ? expression as WorkflowConditionExpression
    : undefined
}

function resolveArtifactSlotTypes(slots: unknown[]): WorkflowArtifactSemanticType[] {
  const types = new Set<WorkflowArtifactSemanticType>()

  for (const slot of slots) {
    if (!slot || typeof slot !== 'object' || !('type' in slot)) {
      continue
    }
    const type = (slot as { type?: unknown }).type
    if (typeof type === 'string') {
      const semanticType = normalizeWorkflowSemanticType(type)
      if (isWorkflowSemanticType(semanticType)) {
        types.add(semanticType)
      }
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

function isProjectArtifactUsableForInput(artifact: TypedArtifact, semanticType: string): boolean {
  const version = artifact.latest_version
  if (!version || version.status !== 'available') return false
  if (version.expires_at && new Date(version.expires_at).getTime() <= Date.now()) return false

  const expectedType = normalizeWorkflowSemanticType(semanticType)
  const artifactType = artifact.standard_type && artifact.standard_version
    ? `${artifact.standard_type}@${artifact.standard_version}`
    : normalizeWorkflowSemanticType(artifact.semantic_type)
  return artifactType === expectedType || normalizeWorkflowSemanticType(artifact.semantic_type) === expectedType
}
