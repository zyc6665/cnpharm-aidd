import type { ArtifactFile } from '@/types/models'
import {
  formatArtifactPickerArtifactMeta,
  formatArtifactPickerTaskMeta,
  type ArtifactPickerGroupNode,
  type ArtifactPickerLabels,
  type ArtifactPickerStep,
  type ArtifactPickerTaskNode,
  type ArtifactPickerToolNode,
} from './artifact-file-picker'

export interface ArtifactPickerStepOptionModel {
  id: string
  title: string
  meta: string
  rightText?: string | number
  rightColor?: string
  selected?: boolean
  focused?: boolean
}

export interface BuildArtifactPickerStepOptionsInput {
  activeStep: ArtifactPickerStep
  groupNodes: ArtifactPickerGroupNode[]
  selectedGroupTools: ArtifactPickerToolNode[]
  selectedToolNode: ArtifactPickerToolNode | null
  selectedToolTasks: ArtifactPickerTaskNode[]
  selectedTaskArtifacts: ArtifactFile[]
  selectedGroupId?: string | null
  selectedToolSlug?: string | null
  selectedTaskId?: string | null
  selectedArtifact?: ArtifactFile | null
  focusedArtifactId?: string | null
  labels: ArtifactPickerLabels
  formatTaskArtifactCount: (count: number) => string
}

export function buildArtifactPickerStepOptions(
  input: BuildArtifactPickerStepOptionsInput
): ArtifactPickerStepOptionModel[] {
  if (input.activeStep === 'group') {
    return input.groupNodes.map((groupNode) => ({
      id: groupNode.groupId,
      title: groupNode.isUngrouped
        ? input.labels.ungroupedGroup
        : groupNode.groupName || '-',
      meta: input.labels.groupMeta,
      rightText: groupNode.tools.length,
      selected: input.selectedGroupId === groupNode.groupId,
    }))
  }

  if (input.activeStep === 'tool') {
    return input.selectedGroupTools.map((toolNode) => ({
      id: toolNode.toolSlug,
      title: toolNode.toolName,
      meta: input.labels.toolMeta,
      rightText: toolNode.tasks.length,
      selected: input.selectedToolSlug === toolNode.toolSlug,
    }))
  }

  if (input.activeStep === 'task') {
    return input.selectedToolTasks.map((taskNode) => ({
      id: taskNode.taskId,
      title: `#${taskNode.taskId}`,
      meta: formatArtifactPickerTaskMeta(
        taskNode,
        input.selectedToolNode?.toolName,
      ),
      rightText: input.formatTaskArtifactCount(taskNode.artifacts.length),
      selected: input.selectedTaskId === taskNode.taskId,
    }))
  }

  return input.selectedTaskArtifacts.map((artifact) => {
    const selected = input.selectedArtifact?.id === artifact.id
    const focused = input.focusedArtifactId === artifact.id && !selected
    return {
      id: artifact.id,
      title: artifact.filename,
      meta: formatArtifactPickerArtifactMeta(artifact),
      rightText: optionStatusText(selected, focused, input.labels),
      rightColor: optionStatusColor(selected, focused),
      selected,
      focused,
    }
  })
}

function optionStatusText(
  selected: boolean,
  focused: boolean,
  labels: ArtifactPickerLabels
): string | undefined {
  if (selected) {
    return labels.artifactSelectedTag
  }
  return focused ? labels.artifactFocusTag : undefined
}

function optionStatusColor(
  selected: boolean,
  focused: boolean
): string | undefined {
  if (selected) {
    return 'blue'
  }
  return focused ? 'gold' : undefined
}
