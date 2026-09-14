import type { ArtifactFile } from '@/types/models'
import {
  findArtifactPickerLocation,
  resolveArtifactPickerPreferredGroupId,
  resolveArtifactPickerPreferredToolSlug,
  type ArtifactPickerGroupNode,
  type ArtifactPickerStep,
  type ArtifactPickerTaskNode,
  type ArtifactPickerToolNode,
} from './artifact-file-picker'

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

export function resolveArtifactPickerSelectionState(
  input: ResolveArtifactPickerSelectionStateInput
): ArtifactPickerSelectionState {
  if (!input.allowArtifacts) {
    return { activeStep: 'group' }
  }

  if (input.selectedArtifact && artifactExists(input.groupNodes, input.selectedArtifact.id)) {
    const location = findArtifactPickerLocation(
      input.groupNodes,
      input.selectedArtifact.id,
    )
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

  const selectedGroupId = groupExists(
    input.groupNodes,
    input.currentState.selectedGroupId,
  )
    ? input.currentState.selectedGroupId
    : resolveArtifactPickerPreferredGroupId(
      input.groupNodes,
      input.preferredGroupId,
    )
  const selectedGroupNode = groupById(input.groupNodes, selectedGroupId)
  if (!selectedGroupNode) {
    return { activeStep: 'group' }
  }

  const selectedToolSlug = toolExists(
    selectedGroupNode,
    input.currentState.selectedToolSlug,
  )
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
