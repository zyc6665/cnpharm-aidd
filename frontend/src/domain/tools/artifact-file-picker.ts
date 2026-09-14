import dayjs from 'dayjs'
import type { ArtifactFile } from '@/types/models'

export interface ArtifactPickerTaskNode {
  taskId: string
  latestCreatedAt: string
  artifacts: ArtifactFile[]
}

export interface ArtifactPickerToolNode {
  toolSlug: string
  toolName: string
  tasks: ArtifactPickerTaskNode[]
}

export interface ArtifactPickerGroupNode {
  groupId: string
  groupName?: string
  isUngrouped?: boolean
  tools: ArtifactPickerToolNode[]
}

export type ArtifactPickerStep = 'group' | 'tool' | 'task' | 'artifact'

export interface ArtifactPickerLabels {
  groupLabel: string
  toolLabel: string
  taskLabel: string
  outputLabel: string
  selectGroup: string
  selectTool: string
  selectTask: string
  selectOutput: string
  summarySelected: string
  summaryFocused: string
  summaryPending: string
  ungroupedGroup: string
  groupMeta: string
  toolMeta: string
  noArtifacts: string
  noCompatibleArtifacts: string
  artifactSelectedTag: string
  artifactFocusTag: string
}

export interface ArtifactPickerPathSegment {
  step: ArtifactPickerStep
  label: string
  value: string
  clickable: boolean
  complete: boolean
}

export interface ArtifactPickerStepSummary {
  label: string
  title: string
  count: number
}

export interface ArtifactPickerSelectionSummary {
  label: string
  title: string
  meta: string
}

export interface ArtifactPickerViewModel {
  selectedGroupNode: ArtifactPickerGroupNode | null
  selectedGroupTools: ArtifactPickerToolNode[]
  selectedToolNode: ArtifactPickerToolNode | null
  selectedToolTasks: ArtifactPickerTaskNode[]
  selectedTaskNode: ArtifactPickerTaskNode | null
  selectedTaskArtifacts: ArtifactFile[]
  compatibleArtifacts: ArtifactFile[]
  highlightedArtifact: ArtifactFile | null
  pathSegments: ArtifactPickerPathSegment[]
  currentStep: ArtifactPickerStepSummary
  summary: ArtifactPickerSelectionSummary
}

export interface BuildArtifactPickerViewModelInput {
  groupNodes: ArtifactPickerGroupNode[]
  activeStep: ArtifactPickerStep
  selectedGroupId?: string | null
  selectedToolSlug?: string | null
  selectedTaskId?: string | null
  focusedArtifactId?: string | null
  selectedArtifact?: ArtifactFile | null
  labels: ArtifactPickerLabels
}

export interface ArtifactPickerSelectionState {
  activeStep: ArtifactPickerStep
  selectedGroupId?: string
  selectedToolSlug?: string
  selectedTaskId?: string
  focusedArtifactId?: string
}

export interface ArtifactPickerExternalSelectionPath {
  token?: unknown
  groupId?: string | null
  toolSlug?: string | null
  taskId?: string | null
  artifactId?: string | null
}

export interface ResolveArtifactPickerSelectionStateInput {
  groupNodes: ArtifactPickerGroupNode[]
  currentState: ArtifactPickerSelectionState
  allowArtifacts: boolean
  selectedArtifact?: ArtifactFile | null
  preferredGroupId?: string | null
  preferredToolSlug?: string | null
  currentToolSlug?: string | null
}

export interface ApplyArtifactPickerExternalSelectionPathInput {
  groupNodes: ArtifactPickerGroupNode[]
  currentState: ArtifactPickerSelectionState
  allowArtifacts: boolean
  path?: ArtifactPickerExternalSelectionPath | null
}

export interface ArtifactPickerLocation {
  groupId: string
  toolSlug: string
  taskId: string
}

export function formatArtifactPickerArtifactMeta(artifact: ArtifactFile): string {
  return `${artifact.tool_name} · ${dayjs(artifact.created_at).format('YYYY-MM-DD HH:mm')}`
}

export function formatArtifactPickerTaskMeta(
  taskNode: Pick<ArtifactPickerTaskNode, 'latestCreatedAt'>,
  toolName?: string | null
): string {
  return `${toolName ?? '-'} · ${dayjs(taskNode.latestCreatedAt).format('YYYY-MM-DD HH:mm')}`
}

export function findArtifactPickerLocation(
  groupNodes: ArtifactPickerGroupNode[],
  artifactId: string
): ArtifactPickerLocation | null {
  for (const groupNode of groupNodes) {
    for (const toolNode of groupNode.tools) {
      for (const taskNode of toolNode.tasks) {
        if (taskNode.artifacts.some((artifact) => artifact.id === artifactId)) {
          return {
            groupId: groupNode.groupId,
            toolSlug: toolNode.toolSlug,
            taskId: taskNode.taskId,
          }
        }
      }
    }
  }

  return null
}

export function resolveArtifactPickerPreferredGroupId(
  groupNodes: ArtifactPickerGroupNode[],
  preferredGroupId?: string | null
): string | undefined {
  if (preferredGroupId && groupNodes.some((group) => group.groupId === preferredGroupId)) {
    return preferredGroupId
  }

  return groupNodes[0]?.groupId
}

export function resolveArtifactPickerPreferredToolSlug(
  groupNode: ArtifactPickerGroupNode | null,
  preferredToolSlug?: string | null,
  currentToolSlug?: string | null
): string | undefined {
  if (!groupNode) {
    return undefined
  }

  const nextToolSlug = preferredToolSlug ?? currentToolSlug
  if (nextToolSlug && groupNode.tools.some((tool) => tool.toolSlug === nextToolSlug)) {
    return nextToolSlug
  }

  return undefined
}

export function buildArtifactPickerViewModel(
  input: BuildArtifactPickerViewModelInput
): ArtifactPickerViewModel {
  const selectedGroupNode = input.groupNodes.find(
    (group) => group.groupId === input.selectedGroupId
  ) ?? null
  const selectedGroupTools = selectedGroupNode?.tools ?? []
  const selectedToolNode = selectedGroupTools.find(
    (tool) => tool.toolSlug === input.selectedToolSlug
  ) ?? null
  const selectedToolTasks = selectedToolNode?.tasks ?? []
  const selectedTaskNode = selectedToolTasks.find(
    (task) => task.taskId === input.selectedTaskId
  ) ?? null
  const selectedTaskArtifacts = selectedTaskNode?.artifacts ?? []
  const compatibleArtifacts = input.groupNodes.flatMap((group) =>
    group.tools.flatMap((tool) => tool.tasks.flatMap((task) => task.artifacts))
  )
  const highlightedArtifact = selectedTaskArtifacts.find(
    (artifact) => artifact.id === input.focusedArtifactId
  ) ?? null

  return {
    selectedGroupNode,
    selectedGroupTools,
    selectedToolNode,
    selectedToolTasks,
    selectedTaskNode,
    selectedTaskArtifacts,
    compatibleArtifacts,
    highlightedArtifact,
    pathSegments: buildPathSegments({
      ...input,
      selectedGroupNode,
      selectedToolNode,
      selectedTaskNode,
      highlightedArtifact,
    }),
    currentStep: buildCurrentStep({
      ...input,
      groupCount: input.groupNodes.length,
      toolCount: selectedGroupTools.length,
      taskCount: selectedToolTasks.length,
      artifactCount: selectedTaskArtifacts.length,
    }),
    summary: buildSelectionSummary({
      ...input,
      selectedGroupNode,
      selectedToolNode,
      selectedTaskNode,
      highlightedArtifact,
    }),
  }
}

export function resolveArtifactPickerSelectionState(
  input: ResolveArtifactPickerSelectionStateInput
): ArtifactPickerSelectionState {
  if (!input.allowArtifacts) {
    return { activeStep: 'group' }
  }

  if (input.selectedArtifact && artifactExists(input.groupNodes, input.selectedArtifact.id)) {
    const location = findArtifactPickerLocation(input.groupNodes, input.selectedArtifact.id)
    if (location) {
      return {
        activeStep: 'artifact',
        selectedGroupId: location.groupId,
        selectedToolSlug: location.toolSlug,
        selectedTaskId: location.taskId,
        focusedArtifactId: input.selectedArtifact.id,
      }
    }
  }

  const selectedGroupId = groupExists(input.groupNodes, input.currentState.selectedGroupId)
    ? input.currentState.selectedGroupId
    : resolveArtifactPickerPreferredGroupId(input.groupNodes, input.preferredGroupId)
  const selectedGroupNode = groupById(input.groupNodes, selectedGroupId)
  if (!selectedGroupNode) {
    return { activeStep: 'group' }
  }

  const selectedToolSlug = toolExists(selectedGroupNode, input.currentState.selectedToolSlug)
    ? input.currentState.selectedToolSlug
    : resolveArtifactPickerPreferredToolSlug(
      selectedGroupNode,
      input.preferredToolSlug,
      input.currentToolSlug,
    )
  const selectedToolNode = toolBySlug(selectedGroupNode, selectedToolSlug)
  if (!selectedToolNode) {
    return {
      activeStep: 'tool',
      selectedGroupId,
    }
  }

  const selectedTaskId = selectedToolNode.tasks.some(
    (task) => task.taskId === input.currentState.selectedTaskId,
  )
    ? input.currentState.selectedTaskId
    : undefined

  return withDeepestMissingStep({
    selectedGroupId,
    selectedToolSlug,
    selectedTaskId,
    focusedArtifactId: input.selectedArtifact
      ? input.currentState.focusedArtifactId
      : undefined,
    activeStep: input.currentState.activeStep,
  })
}

export function applyArtifactPickerExternalSelectionPath(
  input: ApplyArtifactPickerExternalSelectionPathInput
): ArtifactPickerSelectionState {
  if (!input.path || !input.allowArtifacts || input.groupNodes.length === 0) {
    return input.currentState
  }

  const nextState: ArtifactPickerSelectionState = { ...input.currentState }
  const artifactLocation = input.path.artifactId
    ? findArtifactPickerLocation(input.groupNodes, input.path.artifactId)
    : null
  const nextGroupId = input.path.groupId ?? artifactLocation?.groupId
  if (groupExists(input.groupNodes, nextGroupId)) {
    nextState.selectedGroupId = nextGroupId ?? undefined
  }

  const selectedGroupNode = groupById(input.groupNodes, nextState.selectedGroupId)
  const nextToolSlug = input.path.toolSlug ?? artifactLocation?.toolSlug
  if (selectedGroupNode && toolExists(selectedGroupNode, nextToolSlug)) {
    nextState.selectedToolSlug = nextToolSlug ?? undefined
  }

  const selectedToolNode = selectedGroupNode
    ? toolBySlug(selectedGroupNode, nextState.selectedToolSlug)
    : null
  const nextTaskId = input.path.taskId ?? artifactLocation?.taskId
  if (selectedToolNode && taskExists(selectedToolNode, nextTaskId)) {
    nextState.selectedTaskId = nextTaskId ?? undefined
  }

  const selectedTaskNode = selectedToolNode
    ? taskById(selectedToolNode, nextState.selectedTaskId)
    : null
  if (input.path.artifactId && selectedTaskNode?.artifacts.some(
    (artifact) => artifact.id === input.path?.artifactId
  )) {
    nextState.focusedArtifactId = input.path.artifactId
  }

  return withDeepestMissingStep(nextState)
}

function withDeepestMissingStep(
  state: ArtifactPickerSelectionState
): ArtifactPickerSelectionState {
  if (!state.selectedGroupId) {
    return { ...state, activeStep: 'group' }
  }
  if (!state.selectedToolSlug) {
    return { ...state, activeStep: 'tool' }
  }
  if (!state.selectedTaskId) {
    return { ...state, activeStep: 'task' }
  }
  return { ...state, activeStep: 'artifact' }
}

function groupExists(
  groupNodes: ArtifactPickerGroupNode[],
  groupId?: string | null
): boolean {
  return Boolean(groupId && groupNodes.some((group) => group.groupId === groupId))
}

function toolExists(
  groupNode: ArtifactPickerGroupNode,
  toolSlug?: string | null
): boolean {
  return Boolean(toolSlug && groupNode.tools.some((tool) => tool.toolSlug === toolSlug))
}

function taskExists(
  toolNode: ArtifactPickerToolNode,
  taskId?: string | null
): boolean {
  return Boolean(taskId && toolNode.tasks.some((task) => task.taskId === taskId))
}

function artifactExists(
  groupNodes: ArtifactPickerGroupNode[],
  artifactId: string
): boolean {
  return groupNodes.some((group) => group.tools.some((tool) =>
    tool.tasks.some((task) => task.artifacts.some((artifact) => artifact.id === artifactId))
  ))
}

function groupById(
  groupNodes: ArtifactPickerGroupNode[],
  groupId?: string | null
): ArtifactPickerGroupNode | null {
  return groupNodes.find((group) => group.groupId === groupId) ?? null
}

function toolBySlug(
  groupNode: ArtifactPickerGroupNode,
  toolSlug?: string | null
): ArtifactPickerToolNode | null {
  return groupNode.tools.find((tool) => tool.toolSlug === toolSlug) ?? null
}

function taskById(
  toolNode: ArtifactPickerToolNode,
  taskId?: string | null
): ArtifactPickerTaskNode | null {
  return toolNode.tasks.find((task) => task.taskId === taskId) ?? null
}

function buildPathSegments(input: BuildArtifactPickerViewModelInput & {
  selectedGroupNode: ArtifactPickerGroupNode | null
  selectedToolNode: ArtifactPickerToolNode | null
  selectedTaskNode: ArtifactPickerTaskNode | null
  highlightedArtifact: ArtifactFile | null
}): ArtifactPickerPathSegment[] {
  const labels = input.labels
  return [
    {
      step: 'group',
      label: labels.groupLabel,
      value: input.selectedGroupNode
        ? groupDisplayName(input.selectedGroupNode, labels)
        : labels.selectGroup,
      clickable: input.groupNodes.length > 0,
      complete: Boolean(input.selectedGroupNode),
    },
    {
      step: 'tool',
      label: labels.toolLabel,
      value: input.selectedToolNode?.toolName ?? labels.selectTool,
      clickable: Boolean(input.selectedGroupNode),
      complete: Boolean(input.selectedToolNode),
    },
    {
      step: 'task',
      label: labels.taskLabel,
      value: input.selectedTaskNode ? `#${input.selectedTaskNode.taskId}` : labels.selectTask,
      clickable: Boolean(input.selectedToolNode),
      complete: Boolean(input.selectedTaskNode),
    },
    {
      step: 'artifact',
      label: labels.outputLabel,
      value: input.selectedArtifact?.filename
        ?? input.highlightedArtifact?.filename
        ?? labels.selectOutput,
      clickable: Boolean(input.selectedTaskNode),
      complete: Boolean(input.selectedArtifact ?? input.highlightedArtifact),
    },
  ]
}

function buildCurrentStep(input: BuildArtifactPickerViewModelInput & {
  groupCount: number
  toolCount: number
  taskCount: number
  artifactCount: number
}): ArtifactPickerStepSummary {
  const labels = input.labels
  if (input.activeStep === 'group') {
    return { label: labels.groupLabel, title: labels.selectGroup, count: input.groupCount }
  }
  if (input.activeStep === 'tool') {
    return { label: labels.toolLabel, title: labels.selectTool, count: input.toolCount }
  }
  if (input.activeStep === 'task') {
    return { label: labels.taskLabel, title: labels.selectTask, count: input.taskCount }
  }
  return { label: labels.outputLabel, title: labels.selectOutput, count: input.artifactCount }
}

function buildSelectionSummary(input: BuildArtifactPickerViewModelInput & {
  selectedGroupNode: ArtifactPickerGroupNode | null
  selectedToolNode: ArtifactPickerToolNode | null
  selectedTaskNode: ArtifactPickerTaskNode | null
  highlightedArtifact: ArtifactFile | null
}): ArtifactPickerSelectionSummary {
  const labels = input.labels
  const selectedArtifact = input.selectedArtifact ?? null
  if (selectedArtifact) {
    return {
      label: labels.summarySelected,
      title: selectedArtifact.filename,
      meta: formatArtifactPickerArtifactMeta(selectedArtifact),
    }
  }
  if (input.highlightedArtifact) {
    return {
      label: labels.summaryFocused,
      title: input.highlightedArtifact.filename,
      meta: formatArtifactPickerArtifactMeta(input.highlightedArtifact),
    }
  }
  if (input.selectedTaskNode) {
    return {
      label: labels.summaryPending,
      title: `#${input.selectedTaskNode.taskId}`,
      meta: formatArtifactPickerTaskMeta(
        input.selectedTaskNode,
        input.selectedToolNode?.toolName
      ),
    }
  }
  if (input.selectedToolNode) {
    return {
      label: labels.summaryPending,
      title: input.selectedToolNode.toolName,
      meta: labels.toolMeta,
    }
  }
  if (input.selectedGroupNode) {
    return {
      label: labels.summaryPending,
      title: groupDisplayName(input.selectedGroupNode, labels),
      meta: labels.groupMeta,
    }
  }
  return {
    label: labels.summaryPending,
    title: labels.noArtifacts,
    meta: labels.noCompatibleArtifacts,
  }
}

function groupDisplayName(
  groupNode: ArtifactPickerGroupNode,
  labels: ArtifactPickerLabels
): string {
  return groupNode.isUngrouped ? labels.ungroupedGroup : groupNode.groupName ?? groupNode.groupId
}
