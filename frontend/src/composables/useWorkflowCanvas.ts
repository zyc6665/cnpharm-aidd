import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useArtifactsStore, useToolsStore, useWorkflowStore } from '@/stores'
import type { WorkflowReportRow } from '@/workflow/report'
import type {
  ToolContract,
  WorkflowDefinition,
} from '@/types/models'
import type { WorkflowArtifactSemanticType, WorkflowTaskRef } from '@/workflow/artifact-types'
import {
  AIDD_WORKFLOW_TEMPLATE,
  WORKFLOW_TEMPLATES,
  getWorkflowTemplateById,
} from '@/workflow/templates'
import { resolveReadyToolNodeIds } from '@/workflow/template-runner'
import { extractWorkflowInputRequirements } from '@/workflow/workflow-definitions'
import { resolveWorkflowCanvasNodeStatus } from '@/workflow/template-state'

type WorkflowStore = ReturnType<typeof useWorkflowStore>
type ToolsStore = ReturnType<typeof useToolsStore>
type ArtifactsStore = ReturnType<typeof useArtifactsStore>

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

  const activeTemplate = computed(() => {
    return getWorkflowTemplateById(workflowStore.templateId) ?? AIDD_WORKFLOW_TEMPLATE
  })

  const editableTemplate = computed(() => ({
    ...activeTemplate.value,
    nodes: workflowStore.canvasNodes.length ? workflowStore.canvasNodes : activeTemplate.value.nodes,
    edges: workflowStore.canvasNodes.length ? workflowStore.canvasEdges : activeTemplate.value.edges,
  }))

  const activeNode = computed(() => {
    const requestedNode = editableTemplate.value.nodes.find((node) => node.id === workflowStore.activeNodeId)
    return requestedNode ?? editableTemplate.value.nodes[0] ?? null
  })

  const selectedToolByActiveNode = computed(() => {
    if (!activeNode.value) {
      return null
    }

    return resolveSelectedToolSlug(activeNode.value.id)
  })

  const templateOptions = computed(() => {
    return WORKFLOW_TEMPLATES.map((template) => ({
      value: template.id,
      label: resolveLabel(template.nameKey),
    }))
  })

  const availableWorkflowTools = computed(() => {
    const toolsBySlug = new Map<
      string,
      {
        id?: string
        slug: string
        name: string
        description?: string
        contract?: ToolContract | null
        executorType?: string
        stage?: string
        inputSemanticTypes: string[]
        outputSemanticTypes: string[]
      }
    >()

    for (const group of toolsStore.workbenchGroups) {
      for (const tool of group.tools) {
        toolsBySlug.set(tool.slug, {
          id: tool.id,
          slug: tool.slug,
          name: tool.name,
          description: tool.description,
          contract: tool.contract,
          executorType: tool.contract?.executor.type,
          stage: tool.contract?.capability.stage ?? tool.contract?.capability.capability ?? undefined,
          inputSemanticTypes: tool.contract?.capability.inputs.map((item) => item.semantic_type) ?? [],
          outputSemanticTypes: tool.contract?.capability.outputs.map((item) => item.semantic_type) ?? [],
        })
      }
    }

    for (const tool of toolsStore.workflowToolOptions) {
      if (!toolsBySlug.has(tool.slug)) {
        toolsBySlug.set(tool.slug, {
          id: tool.id,
          slug: tool.slug,
          name: tool.name,
          description: tool.description,
          contract: tool.contract,
          executorType: tool.contract?.executor.type,
          stage: tool.contract?.capability.stage ?? tool.contract?.capability.capability ?? undefined,
          inputSemanticTypes: tool.contract?.capability.inputs.map((item) => item.semantic_type) ?? [],
          outputSemanticTypes: tool.contract?.capability.outputs.map((item) => item.semantic_type) ?? [],
        })
      }
    }

    return Array.from(toolsBySlug.values())
  })

  const sidebarStageOptions = computed(() => {
    return Array.from(new Set(availableWorkflowTools.value.map((tool) => tool.stage).filter(Boolean))).map((stage) => ({
      value: stage!,
      label: stage!,
    }))
  })

  const sidebarInputOptions = computed(() => {
    return Array.from(
      new Set(availableWorkflowTools.value.flatMap((tool) => tool.inputSemanticTypes).filter(Boolean)),
    ).map((semanticType) => ({
      value: semanticType,
      label: semanticType,
    }))
  })

  const sidebarOutputOptions = computed(() => {
    return Array.from(
      new Set(availableWorkflowTools.value.flatMap((tool) => tool.outputSemanticTypes).filter(Boolean)),
    ).map((semanticType) => ({
      value: semanticType,
      label: semanticType,
    }))
  })

  const sidebarExecutorOptions = computed(() => {
    return Array.from(
      new Set(availableWorkflowTools.value.map((tool) => tool.executorType).filter(Boolean)),
    ).map((executorType) => ({
      value: executorType!,
      label: executorType!,
    }))
  })

  const filteredSidebarToolOptions = computed(() => {
    const keyword = sidebarToolSearchKeyword.value.trim().toLowerCase()
    return availableWorkflowTools.value.filter((tool) => {
      const matchesKeyword = !keyword || [tool.name, tool.slug, tool.description]
        .filter(Boolean)
        .some((value) => value!.toLowerCase().includes(keyword))
      const matchesStage = !sidebarStageFilter.value || tool.stage === sidebarStageFilter.value
      const matchesInput = !sidebarInputFilter.value || tool.inputSemanticTypes.includes(sidebarInputFilter.value)
      const matchesOutput = !sidebarOutputFilter.value || tool.outputSemanticTypes.includes(sidebarOutputFilter.value)
      const matchesExecutor = !sidebarExecutorFilter.value || tool.executorType === sidebarExecutorFilter.value

      return matchesKeyword && matchesStage && matchesInput && matchesOutput && matchesExecutor
    })
  })

  const currentWorkflowDefinition = computed<WorkflowDefinition>(() => buildCurrentWorkflowDefinition())

  const workflowInputRequirements = computed(() => {
    return extractWorkflowInputRequirements(currentWorkflowDefinition.value)
  })

  const nodeStatuses = computed(() => {
    return editableTemplate.value.nodes.reduce<Record<string, ReturnType<typeof resolveWorkflowCanvasNodeStatus>>>(
      (statuses, node) => {
        statuses[node.id] = resolveWorkflowCanvasNodeStatus({
          node,
          selectedToolSlug: resolveSelectedToolSlug(node.id),
          hasRequiredInputs: hasRequiredInputs(node.id),
          task: workflowStore.taskByNode[node.id] ?? null,
        })
        return statuses
      },
      {},
    )
  })

  const readyToolNodeIds = computed(() => {
    return resolveReadyToolNodeIds({
      template: editableTemplate.value,
      nodeStatuses: nodeStatuses.value,
    })
  })

  const readyNodeCount = computed(() => readyToolNodeIds.value.length)
  const blockedNodeCount = computed(() => {
    return editableTemplate.value.nodes.filter((node) => (
      node.type === 'tool'
      && ['idle', 'needs_tool_selection'].includes(nodeStatuses.value[node.id] ?? 'idle')
    )).length
  })
  const runningNodeCount = computed(() => countNodesByStatus('running'))
  const completedNodeCount = computed(() => countNodesByStatus('completed'))
  const failedNodeCount = computed(() => countNodesByStatus('failed'))

  const workflowReportRows = computed<WorkflowReportRow[]>(() => {
    return editableTemplate.value.nodes.map((node) => {
      const task = workflowStore.taskByNode[node.id]
      const artifacts = task
        ? artifactsStore.items
          .filter((artifact) => artifact.task_id === task.id)
          .map((artifact) => ({
            id: artifact.id,
            filename: artifact.filename,
            url: artifact.download_url,
          }))
        : []

      return {
        nodeId: node.id,
        nodeTitle: resolveLabel(node.titleKey),
        status: nodeStatuses.value[node.id] ?? 'idle',
        statusLabel: resolveNodeStatusReason(node.id),
        taskId: task?.id,
        taskStatus: task?.status,
        artifacts,
      }
    })
  })

  function handleTemplateChange(templateId: unknown) {
    if (typeof templateId !== 'string') {
      return
    }

    workflowStore.setTemplate(templateId)
  }

  function countNodesByStatus(status: ReturnType<typeof resolveWorkflowCanvasNodeStatus>) {
    return editableTemplate.value.nodes.filter((node) => nodeStatuses.value[node.id] === status).length
  }

  function resolveNodeStatusReason(nodeId: string): string {
    const node = editableTemplate.value.nodes.find((item) => item.id === nodeId)
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

  function handleAddToolNode(toolSlug: string) {
    const tool = resolveAvailableTool(toolSlug)
    workflowStore.addToolNode({
      toolSlug,
      toolName: tool?.name ?? toolSlug,
      toolDescription: tool?.description,
      position: {
        x: 320 + editableTemplate.value.nodes.length * 36,
        y: 120 + editableTemplate.value.nodes.length * 24,
      },
    })
  }

  function handleDeleteNode(nodeId: string) {
    workflowStore.deleteCanvasNode(nodeId)
  }

  function handleAddEdge(input: {
    source: string
    target: string
    artifactType: WorkflowArtifactSemanticType
  }) {
    workflowStore.addCanvasEdge(input)
  }

  function handleDeleteEdge(edgeId: string) {
    workflowStore.deleteCanvasEdge(edgeId)
  }

  function hasRequiredInputs(nodeId: string): boolean {
    const node = editableTemplate.value.nodes.find((item) => item.id === nodeId)
    if (!node?.requiredInputTypes?.length) {
      return true
    }

    return node.requiredInputTypes.every((inputType) => {
      return editableTemplate.value.edges.some((edge) => {
        const upstreamTask = workflowStore.taskByNode[edge.source]
        return edge.target === nodeId && edge.artifactType === inputType && upstreamTask?.status === 'success'
      })
    })
  }

  function resolveSelectedToolSlug(nodeId: string): string | null {
    const node = editableTemplate.value.nodes.find((item) => item.id === nodeId)
    if (!node) {
      return null
    }

    return workflowStore.selectedToolByNode[nodeId]
      ?? node.recommendedToolSlug
      ?? ((node.toolSlugs?.length ?? 0) === 1 ? node.toolSlugs?.[0] ?? null : null)
  }

  function resolveToolForNode(nodeId: string) {
    const selectedToolSlug = resolveSelectedToolSlug(nodeId)
    if (!selectedToolSlug) {
      return null
    }

    const workbenchTool = toolsStore.workbenchGroups
      .flatMap((group) => group.tools)
      .find((tool) => tool.slug === selectedToolSlug) ?? null
    if (workbenchTool) {
      return workbenchTool
    }

    return toolsStore.workflowToolOptions.find((tool) => tool.slug === selectedToolSlug) ?? null
  }

  function resolveAvailableTool(toolSlug: string) {
    return availableWorkflowTools.value.find((tool) => tool.slug === toolSlug) ?? null
  }

  function resolveDownstreamNodeIds(nodeId: string): string[] {
    const visited = new Set<string>()
    const queue = [nodeId]

    while (queue.length > 0) {
      const currentNodeId = queue.shift()
      if (!currentNodeId || visited.has(currentNodeId)) {
        continue
      }

      visited.add(currentNodeId)

      for (const edge of editableTemplate.value.edges) {
        if (edge.source === currentNodeId && !visited.has(edge.target)) {
          queue.push(edge.target)
        }
      }
    }

    return Array.from(visited)
  }

  function formatKey(key: string): string {
    return resolveLabel(key)
  }

  function resolveLabel(key: string): string {
    if (te(key)) {
      return t(key)
    }

    const segments = key.split('.')
    const lastSegment = segments[segments.length - 1] ?? key
    return lastSegment
      .replace(/([A-Z])/g, ' $1')
      .replace(/[-_]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  }

  function buildCurrentWorkflowDefinition(): WorkflowDefinition {
    const nodes = editableTemplate.value.nodes.map((node) => ({
      id: node.id,
      kind: node.type === 'input' ? 'input' : 'tool',
      type: node.type,
      semantic_type: node.requiredInputTypes?.[0] ?? node.recommendedToolSlug ?? node.id,
      tool_slug: node.type === 'tool'
        ? resolveSelectedToolSlug(node.id) ?? node.recommendedToolSlug ?? undefined
        : undefined,
      semantic_inputs: buildSemanticInputsForNode(node.id),
      params: workflowStore.nodeFormDrafts[node.id] ?? {},
      position: node.position,
    }))

    const edges = editableTemplate.value.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      source_output: edge.artifactType,
      target_input: edge.artifactType,
    }))

    return { nodes, edges }
  }

  function buildSemanticInputsForNode(nodeId: string) {
    const semanticInputs: Record<string, string> = {}
    const node = editableTemplate.value.nodes.find((item) => item.id === nodeId)
    if (!node) {
      return semanticInputs
    }

    const incomingEdges = editableTemplate.value.edges.filter((edge) => edge.target === nodeId)
    for (const edge of incomingEdges) {
      if (!edge.artifactType) {
        continue
      }
      const sourceNode = editableTemplate.value.nodes.find((item) => item.id === edge.source)
      if (!sourceNode) {
        continue
      }
      semanticInputs[edge.artifactType] = sourceNode.type === 'input'
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

  return {
    sidebarToolSearchKeyword,
    sidebarStageFilter,
    sidebarInputFilter,
    sidebarOutputFilter,
    sidebarExecutorFilter,
    activeTemplate,
    editableTemplate,
    activeNode,
    selectedToolByActiveNode,
    templateOptions,
    availableWorkflowTools,
    sidebarStageOptions,
    sidebarInputOptions,
    sidebarOutputOptions,
    sidebarExecutorOptions,
    filteredSidebarToolOptions,
    currentWorkflowDefinition,
    workflowInputRequirements,
    nodeStatuses,
    readyToolNodeIds,
    readyNodeCount,
    blockedNodeCount,
    runningNodeCount,
    completedNodeCount,
    failedNodeCount,
    workflowReportRows,
    handleTemplateChange,
    resolveNodeStatusReason,
    handleNodeToolSelect,
    handleAddToolNode,
    handleDeleteNode,
    handleAddEdge,
    handleDeleteEdge,
    hasRequiredInputs,
    resolveSelectedToolSlug,
    resolveToolForNode,
    resolveAvailableTool,
    resolveDownstreamNodeIds,
    formatKey,
    buildCurrentWorkflowDefinition,
  }
}
