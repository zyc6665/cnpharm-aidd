import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useArtifactsStore, useToolsStore, useWorkflowStore } from '@/stores'
import type { WorkflowReportRow } from '@/workflow/report'
import type { ToolContract, WorkflowDefinition } from '@/types/models'
import { type WorkflowArtifactSemanticType } from '@/workflow/artifact-types'
import { isWorkflowSemanticType, normalizeWorkflowSemanticType } from '@/workflow/semantic-types'
import {
  FREE_WORKFLOW_CANVAS_PRESET,
  WORKFLOW_CANVAS_PRESETS,
  getWorkflowCanvasPresetById
} from '@/workflow/canvas-presets'
import type { WorkflowCanvasNodeType } from '@/workflow/canvas-types'
import { resolveReadyToolNodeIds } from '@/workflow/canvas-runner'
import {
  extractWorkflowInputRequirementDetails,
  extractWorkflowInputRequirements
} from '@/workflow/workflow-definitions'
import {
  deriveArtifactSlotsFromToolContract,
  type ArtifactInputSlot,
  type ArtifactOutputSlot
} from '@/workflow/contract-bindings'
import { buildWorkflowAutoRepairPlan } from '@/workflow/auto-repair'
import { buildArtifactRoleLabels } from '@/workflow/artifact-role-labels'
import { resolveWorkflowCanvasNodeStatus } from '@/workflow/canvas-state'
import { resolveWorkflowLabel } from '@/workflow/i18n-utils'

type WorkflowStore = ReturnType<typeof useWorkflowStore>
type ToolsStore = ReturnType<typeof useToolsStore>
type ArtifactsStore = ReturnType<typeof useArtifactsStore>

type WorkflowToolSource = {
  id?: string
  slug: string
  name: string
  description?: string
  category_id?: string
  category?: string
  tags?: Array<{ id?: string; name: string; color?: string }>
  contract?: ToolContract | null
}

type AvailableWorkflowTool = WorkflowToolSource & {
  executorType?: string
  capability?: string
  stage?: string
  resourceProfile?: Record<string, unknown>
  inputSemanticTypes: WorkflowArtifactSemanticType[]
  outputSemanticTypes: WorkflowArtifactSemanticType[]
  inputArtifactSlots: ArtifactInputSlot[]
  outputArtifactSlots: ArtifactOutputSlot[]
}

export function useWorkflowCanvas(input: {
  workflowStore: WorkflowStore
  toolsStore: ToolsStore
  artifactsStore: ArtifactsStore
}) {
  const { workflowStore, toolsStore, artifactsStore } = input
  const { t, te } = useI18n()

  const sidebarToolSearchKeyword = ref('')
  const sidebarStageFilter = ref<string>()
  const sidebarInputFilter = ref<string>()
  const sidebarOutputFilter = ref<string>()
  const sidebarExecutorFilter = ref<string>()

  const activeCanvasPreset = computed(() => {
    return getWorkflowCanvasPresetById(workflowStore.canvasPresetId) ?? FREE_WORKFLOW_CANVAS_PRESET
  })

  const editableCanvasPreset = computed(() => ({
    ...activeCanvasPreset.value,
    nodes: workflowStore.hasCanvasOverride ? workflowStore.canvasNodes : activeCanvasPreset.value.nodes,
    edges: workflowStore.hasCanvasOverride ? workflowStore.canvasEdges : activeCanvasPreset.value.edges
  }))

  const activeNode = computed(() => {
    const requestedNode = editableCanvasPreset.value.nodes.find(
      node => node.id === workflowStore.activeNodeId
    )
    return requestedNode ?? editableCanvasPreset.value.nodes[0] ?? null
  })

  const selectedToolByActiveNode = computed(() => {
    if (!activeNode.value) {
      return null
    }

    return resolveSelectedToolSlug(activeNode.value.id)
  })

  const canvasPresetOptions = computed(() => {
    return WORKFLOW_CANVAS_PRESETS.map(preset => ({
      value: preset.id,
      label: formatKey(preset.nameKey)
    }))
  })

  function normalizeWorkflowTool(tool: WorkflowToolSource): AvailableWorkflowTool {
    const artifactSlots = deriveArtifactSlotsFromToolContract(tool.contract)
    return {
      id: tool.id,
      slug: tool.slug,
      name: tool.name,
      description: tool.description,
      category_id: tool.category_id,
      category: tool.category,
      tags: tool.tags ?? [],
      contract: tool.contract,
      executorType: tool.contract?.executor.type,
      capability: tool.contract?.capability.capability ?? undefined,
      stage: tool.contract?.capability.stage ?? tool.contract?.capability.capability ?? undefined,
      resourceProfile: tool.contract?.resource_profile,
      inputSemanticTypes: artifactSlots.inputs.length
        ? artifactSlots.inputs.map(slot => slot.type)
        : resolveWorkflowSemanticTypes(
            tool.contract?.capability.inputs.map(item => item.semantic_type) ?? []
          ),
      outputSemanticTypes: artifactSlots.outputs.length
        ? artifactSlots.outputs.map(slot => slot.type)
        : resolveWorkflowSemanticTypes(
            tool.contract?.capability.outputs.map(item => item.semantic_type) ?? []
          ),
      inputArtifactSlots: [...artifactSlots.inputs],
      outputArtifactSlots: [...artifactSlots.outputs]
    }
  }

  const availableWorkflowTools = computed(() => {
    const toolsBySlug = new Map<string, AvailableWorkflowTool>()

    for (const group of toolsStore.workbenchGroups) {
      for (const tool of group.tools) {
        toolsBySlug.set(tool.slug, normalizeWorkflowTool(tool))
      }
    }

    for (const tool of toolsStore.workflowToolOptions) {
      if (!toolsBySlug.has(tool.slug)) {
        toolsBySlug.set(tool.slug, normalizeWorkflowTool(tool))
      }
    }

    return Array.from(toolsBySlug.values())
  })

  const sidebarStageOptions = computed(() => {
    return Array.from(
      new Set(availableWorkflowTools.value.map(tool => tool.stage).filter(Boolean))
    ).map(stage => ({
      value: stage!,
      label: stage!
    }))
  })

  const sidebarInputOptions = computed(() => {
    return Array.from(
      new Set(availableWorkflowTools.value.flatMap(tool => tool.inputSemanticTypes).filter(Boolean))
    ).map(semanticType => ({
      value: semanticType,
      label: semanticType
    }))
  })

  const sidebarOutputOptions = computed(() => {
    return Array.from(
      new Set(
        availableWorkflowTools.value.flatMap(tool => tool.outputSemanticTypes).filter(Boolean)
      )
    ).map(semanticType => ({
      value: semanticType,
      label: semanticType
    }))
  })

  const sidebarExecutorOptions = computed(() => {
    return Array.from(
      new Set(availableWorkflowTools.value.map(tool => tool.executorType).filter(Boolean))
    ).map(executorType => ({
      value: executorType!,
      label: executorType!
    }))
  })

  const filteredSidebarToolOptions = computed(() => {
    const keyword = sidebarToolSearchKeyword.value.trim().toLowerCase()
    return availableWorkflowTools.value.filter(tool => {
      const matchesKeyword =
        !keyword ||
        [tool.name, tool.slug, tool.description]
          .filter(Boolean)
          .some(value => value!.toLowerCase().includes(keyword))
      const matchesStage = !sidebarStageFilter.value || tool.stage === sidebarStageFilter.value
      const matchesInput =
        !sidebarInputFilter.value ||
        tool.inputSemanticTypes.includes(sidebarInputFilter.value as WorkflowArtifactSemanticType)
      const matchesOutput =
        !sidebarOutputFilter.value ||
        tool.outputSemanticTypes.includes(sidebarOutputFilter.value as WorkflowArtifactSemanticType)
      const matchesExecutor =
        !sidebarExecutorFilter.value || tool.executorType === sidebarExecutorFilter.value

      return matchesKeyword && matchesStage && matchesInput && matchesOutput && matchesExecutor
    })
  })

  const currentWorkflowDefinition = computed<WorkflowDefinition>(() =>
    buildCurrentWorkflowDefinition()
  )

  const workflowInputRequirements = computed(() => {
    return extractWorkflowInputRequirements(currentWorkflowDefinition.value)
  })

  const workflowInputRequirementDetails = computed(() => {
    return extractWorkflowInputRequirementDetails(currentWorkflowDefinition.value)
  })

  const nodeStatuses = computed(() => {
    return editableCanvasPreset.value.nodes.reduce<
      Record<string, ReturnType<typeof resolveWorkflowCanvasNodeStatus>>
    >((statuses, node) => {
      statuses[node.id] = resolveWorkflowCanvasNodeStatus({
        node,
        selectedToolSlug: resolveSelectedToolSlug(node.id),
        hasRequiredInputs: hasRequiredInputs(node.id),
        task: workflowStore.taskByNode[node.id] ?? null
      })
      return statuses
    }, {})
  })

  const readyToolNodeIds = computed(() => {
    return resolveReadyToolNodeIds({
      template: editableCanvasPreset.value,
      nodeStatuses: nodeStatuses.value
    })
  })

  const readyNodeCount = computed(() => readyToolNodeIds.value.length)
  const blockedNodeCount = computed(() => {
    return editableCanvasPreset.value.nodes.filter(
      node =>
        node.type === 'tool' &&
        ['idle', 'needs_tool_selection'].includes(nodeStatuses.value[node.id] ?? 'idle')
    ).length
  })
  const runningNodeCount = computed(() => countNodesByStatus('running'))
  const completedNodeCount = computed(() => countNodesByStatus('completed'))
  const failedNodeCount = computed(() => countNodesByStatus('failed'))

  const workflowReportRows = computed<WorkflowReportRow[]>(() => {
    return editableCanvasPreset.value.nodes.map(node => {
      const task = workflowStore.taskByNode[node.id]
      const artifacts = task
        ? artifactsStore.items
            .filter(artifact => artifact.task_id === task.id)
            .map(artifact => ({
              id: artifact.id,
              filename: artifact.filename,
              url: artifact.download_url
            }))
        : []

      return {
        nodeId: node.id,
        nodeTitle: formatKey(node.titleKey),
        status: nodeStatuses.value[node.id] ?? 'idle',
        statusLabel: resolveNodeStatusReason(node.id),
        taskId: task?.id,
        taskStatus: task?.status,
        artifacts
      }
    })
  })

  const workflowRepairPlan = computed(() => buildWorkflowAutoRepairPlan({
    template: editableCanvasPreset.value,
    tools: availableWorkflowTools.value,
    artifactRoleLabels: buildArtifactRoleLabels(key => t(key)),
    labels: {
      reasonWithRoles: input => t('workflow.autoRepair.reasonWithRoles', {
        targetNodeTitle: formatKey(input.targetNodeTitle),
        inputSlotName: input.inputSlotName,
        requiredRoles: input.requiredRoleLabels.join(t('workflow.autoRepair.roleSeparator')),
        toolName: input.toolName,
      }),
      reasonWithoutRoles: input => t('workflow.autoRepair.reasonWithoutRoles', {
        targetNodeTitle: formatKey(input.targetNodeTitle),
        inputSlotName: input.inputSlotName,
        toolName: input.toolName,
      }),
    }
  }))

  const workflowRepairableCount = computed(() => workflowRepairPlan.value.repairableCount)

  const workflowRepairActions = computed(() => workflowRepairPlan.value.actions.map(action => ({
    ...action,
    targetNodeTitle: formatKey(action.targetNodeTitle)
  })))

  function handleCanvasPresetChange(canvasPresetId: unknown) {
    if (typeof canvasPresetId !== 'string') {
      return
    }

    workflowStore.setCanvasPreset(canvasPresetId)
  }

  function countNodesByStatus(status: ReturnType<typeof resolveWorkflowCanvasNodeStatus>) {
    return editableCanvasPreset.value.nodes.filter(node => nodeStatuses.value[node.id] === status)
      .length
  }

  function resolveNodeStatusReason(nodeId: string): string {
    const node = editableCanvasPreset.value.nodes.find(item => item.id === nodeId)
    const status = nodeStatuses.value[nodeId] ?? 'idle'
    if (!node) {
      return ''
    }

    if (status === 'ready') {
      return t('workflow.nodeState.ready')
    }
    if (status === 'running') {
      return t('workflow.nodeState.running')
    }
    if (status === 'completed') {
      return t('workflow.nodeState.completed')
    }
    if (status === 'failed') {
      return t('workflow.nodeState.failed')
    }
    if (status === 'needs_tool_selection') {
      return t('workflow.nodeState.missingTool')
    }
    if (status === 'invalidated') {
      return t('workflow.nodeState.invalidated')
    }
    if (node.type === 'tool' && node.requiredInputTypes?.length && !hasRequiredInputs(nodeId)) {
      return t('workflow.nodeState.waitingInput')
    }

    return node.type === 'input'
      ? t('workflow.nodeState.inputNode')
      : t('workflow.nodeState.pending')
  }

  function handleNodeToolSelect(nodeId: string, toolSlug: string) {
    workflowStore.selectNodeTool(nodeId, toolSlug)
  }

  function handleAddToolNode(
    input: string | { toolSlug: string; position?: { x: number; y: number } }
  ) {
    const toolSlug = typeof input === 'string' ? input : input.toolSlug
    const tool = resolveAvailableTool(toolSlug)
    return workflowStore.addToolNode({
      toolSlug,
      toolName: tool?.name ?? toolSlug,
      toolDescription: tool?.description,
      requiredInputTypes: tool?.inputSemanticTypes ?? [],
      producedOutputTypes: tool?.outputSemanticTypes ?? [],
      inputArtifactSlots: tool?.inputArtifactSlots ?? [],
      outputArtifactSlots: tool?.outputArtifactSlots ?? [],
      position:
        typeof input === 'string'
          ? {
              x: 320 + editableCanvasPreset.value.nodes.length * 36,
              y: 120 + editableCanvasPreset.value.nodes.length * 24
            }
          : input.position
    })
  }

  function handleApplyWorkflowAutoRepair(): number {
    const actions = workflowRepairPlan.value.actions
    let appliedCount = 0

    for (const action of actions) {
      const tool = resolveAvailableTool(action.toolSlug)
      if (!tool) {
        continue
      }
      const repairNode = handleAddToolNode({
        toolSlug: action.toolSlug,
        position: action.position
      })
      if (!repairNode) {
        continue
      }

      workflowStore.deleteCanvasEdge(action.sourceEdgeId)
      workflowStore.addCanvasEdge({
        source: action.sourceNodeId,
        target: repairNode.id,
        artifactType: action.artifactType
      })
      workflowStore.addCanvasEdge({
        source: repairNode.id,
        target: action.targetNodeId,
        artifactType: action.artifactType
      })
      appliedCount += 1
    }

    return appliedCount
  }

  function handleAddControlNode(type: Extract<WorkflowCanvasNodeType, 'condition' | 'map' | 'loop'>) {
    workflowStore.addControlNode({
      type,
      position: {
        x: 320 + editableCanvasPreset.value.nodes.length * 36,
        y: 120 + editableCanvasPreset.value.nodes.length * 24
      }
    })
  }

  function handleDeleteNode(nodeId: string) {
    workflowStore.deleteCanvasNode(nodeId)
  }

  function handleAddEdge(input: {
    source: string
    target: string
    artifactType?: WorkflowArtifactSemanticType
  }) {
    workflowStore.addCanvasEdge(input)
  }

  function handleDeleteEdge(edgeId: string) {
    workflowStore.deleteCanvasEdge(edgeId)
  }

  function hasRequiredInputs(nodeId: string): boolean {
    const node = editableCanvasPreset.value.nodes.find(item => item.id === nodeId)
    if (!node?.requiredInputTypes?.length) {
      return true
    }

    return node.requiredInputTypes.every(inputType => {
      const matchingEdges = editableCanvasPreset.value.edges.filter(
        edge => edge.target === nodeId && edge.artifactType === inputType
      )
      if (matchingEdges.length === 0) return true
      return matchingEdges.some(edge => {
        const upstreamNode = editableCanvasPreset.value.nodes.find(item => item.id === edge.source)
        if (upstreamNode?.type === 'input') return true
        return workflowStore.taskByNode[edge.source]?.status === 'success'
      })
    })
  }

  function resolveSelectedToolSlug(nodeId: string): string | null {
    const node = editableCanvasPreset.value.nodes.find(item => item.id === nodeId)
    if (!node) {
      return null
    }

    return (
      workflowStore.selectedToolByNode[nodeId] ??
      node.recommendedToolSlug ??
      ((node.toolSlugs?.length ?? 0) === 1 ? (node.toolSlugs?.[0] ?? null) : null)
    )
  }

  function resolveAvailableTool(toolSlug: string) {
    return availableWorkflowTools.value.find(tool => tool.slug === toolSlug) ?? null
  }

  function formatKey(key: string): string {
    return resolveWorkflowLabel(key, t, te, t('workflow.canvasNode.titleFallback'))
  }

  function resolveWorkflowSemanticTypes(values: string[]): WorkflowArtifactSemanticType[] {
    const seen = new Set<WorkflowArtifactSemanticType>()
    for (const value of values) {
      const normalized = normalizeWorkflowSemanticType(value)
      if (isWorkflowSemanticType(normalized)) {
        seen.add(normalized)
      }
    }
    return [...seen]
  }

  function buildCurrentWorkflowDefinition(): WorkflowDefinition {
    const nodes = editableCanvasPreset.value.nodes.map(node => buildWorkflowDefinitionNode(node))

    const edges = editableCanvasPreset.value.edges.map(edge => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      source_output: edge.artifactType,
      target_input: edge.artifactType,
      ...(edge.branch ? { branch: edge.branch } : {})
    }))

    return { nodes, edges }
  }

  function buildWorkflowDefinitionNode(node: (typeof editableCanvasPreset.value.nodes)[number]) {
    if (node.type === 'condition') {
      return {
        id: node.id,
        kind: 'condition',
        type: node.type,
        expression: node.expression,
        position: node.position
      }
    }

    if (node.type === 'map') {
      return {
        id: node.id,
        kind: 'map',
        type: node.type,
        over: node.over,
        max_parallelism: node.max_parallelism,
        position: node.position
      }
    }

    if (node.type === 'loop') {
      return {
        id: node.id,
        kind: 'loop',
        type: node.type,
        body: (node.body ?? []).map(loopNode => ({
          id: loopNode.id,
          kind: loopNode.type === 'input' ? 'input' : 'tool',
          type: loopNode.type,
          tool_slug: loopNode.recommendedToolSlug ?? loopNode.toolSlugs?.[0],
          semantic_type: loopNode.requiredInputTypes?.[0] ?? loopNode.recommendedToolSlug ?? loopNode.id,
          semantic_inputs: {},
          artifact_input_slots: loopNode.inputArtifactSlots ?? [],
          artifact_inputs: {},
          artifact_outputs: loopNode.outputArtifactSlots ?? [],
          params: {},
          position: loopNode.position
        })),
        max_iterations: node.max_iterations,
        convergence_condition: node.convergence_condition,
        position: node.position
      }
    }

    return {
      id: node.id,
      kind: node.type === 'input' ? 'input' : node.type === 'tool' ? 'tool' : node.type,
      type: node.type,
      semantic_type: node.requiredInputTypes?.[0] ?? node.recommendedToolSlug ?? node.id,
      tool_slug:
        node.type === 'tool'
          ? (resolveSelectedToolSlug(node.id) ?? node.recommendedToolSlug ?? undefined)
          : undefined,
      semantic_inputs: buildSemanticInputsForNode(node.id),
      artifact_input_slots: node.inputArtifactSlots ?? [],
      artifact_inputs: buildArtifactInputsForNode(node.id),
      artifact_outputs: node.outputArtifactSlots ?? [],
      params: workflowStore.nodeFormDrafts[node.id] ?? {},
      position: node.position
    }
  }

  function buildSemanticInputsForNode(nodeId: string) {
    const semanticInputs: Record<string, string> = {}
    const node = editableCanvasPreset.value.nodes.find(item => item.id === nodeId)
    if (!node) {
      return semanticInputs
    }

    const incomingEdges = editableCanvasPreset.value.edges.filter(edge => edge.target === nodeId)
    for (const edge of incomingEdges) {
      if (!edge.artifactType) {
        continue
      }
      const sourceNode = editableCanvasPreset.value.nodes.find(item => item.id === edge.source)
      if (!sourceNode) {
        continue
      }
      semanticInputs[edge.artifactType] =
        sourceNode.type === 'input'
          ? `workflow_input:${edge.artifactType}`
          : `node:${edge.source}:${edge.artifactType}`
    }

    for (const inputType of node.requiredInputTypes ?? []) {
      if (!semanticInputs[inputType]) {
        semanticInputs[inputType] = `workflow_input:${inputType}`
      }
    }

    return semanticInputs
  }

  function buildArtifactInputsForNode(nodeId: string) {
    const artifactInputs: Record<string, string> = {}
    const node = editableCanvasPreset.value.nodes.find(item => item.id === nodeId)
    if (!node?.inputArtifactSlots?.length) {
      return artifactInputs
    }

    const incomingEdges = editableCanvasPreset.value.edges.filter(edge => edge.target === nodeId)
    for (const slot of node.inputArtifactSlots) {
      const edge = incomingEdges.find(item => item.artifactType === slot.type)
      if (!edge?.artifactType) {
        artifactInputs[slot.name] = `workflow_input:${slot.type}`
        continue
      }

      const sourceNode = editableCanvasPreset.value.nodes.find(item => item.id === edge.source)
      if (!sourceNode || sourceNode.type === 'input') {
        artifactInputs[slot.name] = `workflow_input:${slot.type}`
        continue
      }

      const sourceSlot = sourceNode.outputArtifactSlots?.find(
        item => item.type === edge.artifactType
      )
      artifactInputs[slot.name] = `node:${edge.source}:${sourceSlot?.name ?? edge.artifactType}`
    }

    return artifactInputs
  }

  return {
    sidebarToolSearchKeyword,
    sidebarStageFilter,
    sidebarInputFilter,
    sidebarOutputFilter,
    sidebarExecutorFilter,
    activeCanvasPreset,
    editableCanvasPreset,
    activeNode,
    selectedToolByActiveNode,
    canvasPresetOptions,
    availableWorkflowTools,
    sidebarStageOptions,
    sidebarInputOptions,
    sidebarOutputOptions,
    sidebarExecutorOptions,
    filteredSidebarToolOptions,
    currentWorkflowDefinition,
    workflowInputRequirements,
    workflowInputRequirementDetails,
    nodeStatuses,
    readyToolNodeIds,
    readyNodeCount,
    blockedNodeCount,
    runningNodeCount,
    completedNodeCount,
    failedNodeCount,
    workflowReportRows,
    workflowRepairPlan,
    workflowRepairActions,
    workflowRepairableCount,
    handleCanvasPresetChange,
    resolveNodeStatusReason,
    handleNodeToolSelect,
    handleAddToolNode,
    handleApplyWorkflowAutoRepair,
    handleAddControlNode,
    handleDeleteNode,
    handleAddEdge,
    handleDeleteEdge,
    hasRequiredInputs,
    resolveSelectedToolSlug,
    resolveAvailableTool,
    formatKey,
    buildCurrentWorkflowDefinition
  }
}
