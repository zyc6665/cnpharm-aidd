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
  tools: ArtifactPickerToolNode[]
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
