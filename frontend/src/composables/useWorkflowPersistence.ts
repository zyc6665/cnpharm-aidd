import { computed, ref, type ComputedRef } from 'vue'
import { message } from 'ant-design-vue'
import type { WorkflowDefinitionPayload } from '@/api/workflows'
import {
  buildWorkflowInputFileMap,
  findLatestArtifactForSemanticType,
} from '@/workflow/workflow-definitions'
import { shouldAutoSyncWorkflowRun } from '@/workflow/workflow-runs'
import {
  validateWorkflowDefinition,
  validateWorkflowExecutionOrder,
} from '@/workflow/template-runner'
import { useArtifactsStore, useUserStore, useWorkflowDefinitionsStore, useWorkflowStore } from '@/stores'
import type {
  ArtifactFile,
  WorkflowDefinition,
  WorkflowDefinitionNode,
  WorkflowRun,
  WorkflowTemplate,
} from '@/types/models'

type UserStore = ReturnType<typeof useUserStore>
type ArtifactsStore = ReturnType<typeof useArtifactsStore>
type WorkflowStore = ReturnType<typeof useWorkflowStore>
type WorkflowDefinitionsStore = ReturnType<typeof useWorkflowDefinitionsStore>

export function useWorkflowPersistence(input: {
  userStore: UserStore
  artifactsStore: ArtifactsStore
  workflowStore: WorkflowStore
  workflowDefinitionsStore: WorkflowDefinitionsStore
  editableTemplate: ComputedRef<{ id: string; nodes: any[]; edges: any[] }>
  workflowInputRequirements: ComputedRef<string[]>
  buildCurrentWorkflowDefinition: () => WorkflowDefinition
}) {
  const {
    userStore,
    artifactsStore,
    workflowStore,
    workflowDefinitionsStore,
    editableTemplate,
    workflowInputRequirements,
    buildCurrentWorkflowDefinition,
  } = input

  const workflowName = ref('AIDD workflow')
  const workflowTemplateName = ref('AIDD workflow')
  const selectedSavedWorkflowId = ref<string | undefined>()
  const workflowRunInputSelections = ref<Record<string, string | undefined>>({})
  const workflowRunAutoSyncTimer = ref<number | null>(null)

  const savedWorkflowOptions = computed(() => {
    return workflowDefinitionsStore.workflowDefinitions.map((workflow) => ({
      value: workflow.id,
      label: workflow.name,
    }))
  })

  const workflowTemplateOptions = computed(() => {
    return workflowStore.workflowTemplates.map((template) => ({
      value: template.id,
      label: template.name,
    }))
  })

  const selectedWorkflowInputFiles = computed(() => {
    return buildWorkflowInputFileMap(workflowInputRequirements.value, workflowRunInputSelections.value)
  })

  const artifactOptionsBySemanticType = computed(() => {
    return workflowInputRequirements.value.reduce<Record<string, Array<{ value: string; label: string }>>>(
      (accumulator, semanticType) => {
        accumulator[semanticType] = artifactsStore.items
          .filter((artifact) => artifact.semantic_type === semanticType)
          .map((artifact) => ({
            value: artifact.id,
            label: `${artifact.filename} · ${artifact.tool_name}`,
          }))
        return accumulator
      },
      {},
    )
  })

  async function handleSaveWorkflow() {
    const name = workflowName.value.trim() || 'AIDD workflow'
    const payload: WorkflowDefinitionPayload = {
      name,
      template_id: editableTemplate.value.id,
      nodes: workflowStore.exportWorkflowNodes(editableTemplate.value.nodes),
      edges: workflowStore.exportWorkflowEdges(editableTemplate.value.edges),
      selected_tool_by_node: workflowStore.selectedToolByNode,
      artifact_bindings_by_node: workflowStore.artifactBindingsByNode,
      status: 'draft',
    }

    try {
      const saved = await workflowDefinitionsStore.saveWorkflowDefinition(
        payload,
        selectedSavedWorkflowId.value ?? workflowDefinitionsStore.currentWorkflowDefinition?.id,
      )
      selectedSavedWorkflowId.value = saved.id
      workflowName.value = saved.name
      message.success('工作流已保存')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  function handleNewWorkflowTemplate() {
    workflowStore.clearActiveWorkflowTemplate()
    workflowTemplateName.value = ''
    selectedSavedWorkflowId.value = undefined
  }

  async function handleTemplateSelect(templateId: string | undefined) {
    if (!templateId) {
      workflowStore.clearActiveWorkflowTemplate()
      return
    }

    try {
      const template = await workflowStore.loadWorkflowTemplate(templateId)
      workflowTemplateName.value = template.name
      selectedSavedWorkflowId.value = template.id
      workflowStore.applyWorkflowDefinition(mapTemplateToDefinitionPayload(template))
    } catch {
      // 请求层会展示错误信息。
    }
  }

  async function handleSaveWorkflowTemplate() {
    const payload = {
      name: workflowTemplateName.value.trim() || 'AIDD workflow',
      description: workflowStore.activeWorkflowTemplate?.description ?? '',
      definition: buildCurrentWorkflowDefinition(),
      is_public: workflowStore.activeWorkflowTemplate?.is_public ?? false,
    }

    try {
      const template = workflowStore.activeWorkflowTemplateId
        ? await workflowStore.updateSavedWorkflowTemplate(workflowStore.activeWorkflowTemplateId, payload)
        : await workflowStore.saveWorkflowTemplate(payload)
      workflowTemplateName.value = template.name
      selectedSavedWorkflowId.value = template.id
      message.success('工作流模板已保存')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  async function handleDuplicateWorkflowTemplate() {
    const templateId = workflowStore.activeWorkflowTemplateId
    if (!templateId) {
      return
    }

    try {
      const duplicated = await workflowStore.duplicateSavedWorkflowTemplate(
        templateId,
        `${workflowTemplateName.value || 'AIDD workflow'} Copy`,
      )
      workflowTemplateName.value = duplicated.name
      selectedSavedWorkflowId.value = duplicated.id
      message.success('工作流模板已复制')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  async function handleDeleteWorkflowTemplate() {
    const templateId = workflowStore.activeWorkflowTemplateId
    if (!templateId) {
      return
    }

    try {
      await workflowStore.removeWorkflowTemplate(templateId)
      workflowTemplateName.value = 'AIDD workflow'
      selectedSavedWorkflowId.value = undefined
      message.success('工作流模板已删除')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  async function handleRunWorkflowTemplate() {
    const definition = buildCurrentWorkflowDefinition()
    const validationResult = validateWorkflowDefinition(definition)
    const executionValidationResult = validateWorkflowExecutionOrder(definition)
    if (!validationResult.valid || !executionValidationResult.valid) {
      message.warning(validationResult.message ?? executionValidationResult.message)
      return
    }

    const templateId = workflowStore.activeWorkflowTemplateId
    let activeTemplateId = templateId
    if (!activeTemplateId) {
      const template = await workflowStore.saveWorkflowTemplate({
        name: workflowTemplateName.value.trim() || 'AIDD workflow',
        definition,
        is_public: false,
      })
      activeTemplateId = template.id
      selectedSavedWorkflowId.value = template.id
    }

    const run = await workflowStore.runWorkflowTemplate(activeTemplateId!, {
      name: workflowTemplateName.value.trim() || 'AIDD workflow',
      input_files: selectedWorkflowInputFiles.value,
    })
    await workflowStore.loadWorkflowRuns({ template_id: activeTemplateId!, page: 1, page_size: 20 })
    await workflowStore.loadWorkflowRun(run.id)
  }

  async function handleRefreshWorkflowRuns() {
    const templateId = workflowStore.activeWorkflowTemplateId ?? undefined
    await workflowStore.loadWorkflowRuns({ template_id: templateId, page: 1, page_size: 20 })
  }

  async function handleLoadMoreWorkflowRuns() {
    const templateId = workflowStore.activeWorkflowTemplateId ?? undefined
    if (!workflowStore.hasMoreWorkflowRuns) {
      return
    }
    await workflowStore.loadWorkflowRuns(
      {
        template_id: templateId,
        page: workflowStore.workflowRunsPagination.page + 1,
        page_size: workflowStore.workflowRunsPagination.pageSize,
      },
      { append: true },
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
      [semanticType]: artifactId,
    }
  }

  async function scheduleWorkflowRunAutoSync() {
    clearWorkflowRunAutoSync()
    const run = workflowStore.activeWorkflowRun
    if (!shouldAutoSyncWorkflowRun(run, {
      isLoggedIn: userStore.isLoggedIn,
      isLoading: workflowStore.isLoadingWorkflowRun,
      isSyncing: workflowStore.isSyncingWorkflowRun,
    })) {
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

  async function restoreActiveWorkflowTemplate() {
    if (!userStore.authReady || !userStore.isLoggedIn || !workflowStore.activeWorkflowTemplateId) {
      return
    }
    await handleTemplateSelect(workflowStore.activeWorkflowTemplateId)
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
      const workflow = await workflowDefinitionsStore.loadWorkflowDefinition(selectedSavedWorkflowId.value)
      workflowStore.applyWorkflowDefinition(workflow)
      workflowName.value = workflow.name
      message.success('工作流已加载')
    } catch {
      // 请求层会展示错误信息。
    }
  }

  return {
    workflowName,
    workflowTemplateName,
    selectedSavedWorkflowId,
    workflowRunInputSelections,
    workflowRunAutoSyncTimer,
    savedWorkflowOptions,
    workflowTemplateOptions,
    selectedWorkflowInputFiles,
    artifactOptionsBySemanticType,
    handleSaveWorkflow,
    handleNewWorkflowTemplate,
    handleTemplateSelect,
    handleSaveWorkflowTemplate,
    handleDuplicateWorkflowTemplate,
    handleDeleteWorkflowTemplate,
    handleRunWorkflowTemplate,
    handleRefreshWorkflowRuns,
    handleLoadMoreWorkflowRuns,
    handleWorkflowRunSelect,
    handleSyncWorkflowRun,
    autofillWorkflowInputSelections,
    handleWorkflowInputSelect,
    scheduleWorkflowRunAutoSync,
    clearWorkflowRunAutoSync,
    restoreActiveWorkflowTemplate,
    restoreActiveWorkflowRun,
    handleLoadWorkflow,
  }
}

function mapTemplateToDefinitionPayload(template: WorkflowTemplate) {
  return {
    template_id: template.id,
    name: template.name,
    description: template.description ?? undefined,
    nodes: (template.definition.nodes ?? []).map((node) => mapTemplateNode(node)),
    edges: (template.definition.edges ?? []).map((edge, index) => ({
      id: resolveWorkflowEdgeId(edge.id, index),
      source: edge.source,
      target: edge.target,
      artifactType: edge.source_output ?? edge.target_input,
    })),
    selected_tool_by_node: {},
    artifact_bindings_by_node: {},
    status: 'draft' as const,
  }
}

function mapTemplateNode(node: WorkflowDefinitionNode) {
  return {
    id: node.id,
    type: node.kind === 'input' ? 'input' : 'tool',
    titleKey: node.tool_slug || node.semantic_type || node.id,
    descriptionKey: node.tool_slug || node.semantic_type || node.id,
    position: resolveWorkflowNodePosition(node),
    toolSlugs: node.tool_slug ? [node.tool_slug] : [],
    recommendedToolSlug: node.tool_slug ?? undefined,
    requiredInputTypes: Object.keys(node.semantic_inputs ?? {}),
    producedOutputTypes: [],
  }
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
      y: position.y,
    }
  }

  return { x: 0, y: 0 }
}

function resolveWorkflowEdgeId(edgeId: unknown, index: number): string {
  return typeof edgeId === 'string' && edgeId ? edgeId : `edge-${index}`
}
