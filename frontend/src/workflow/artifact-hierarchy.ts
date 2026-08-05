import { filterCompatibleArtifacts } from '../domain/tools/artifact-selection.ts'
import type { ArtifactFile, WorkbenchGroup } from '../types/models.d.ts'
import { sortArtifactsByCreatedAtDesc } from '../utils/artifact-sorting.ts'

export const UNGROUPED_ARTIFACT_GROUP_ID = 'ungrouped'
export const UNGROUPED_ARTIFACT_GROUP_SLUG = 'ungrouped'

export type WorkflowArtifactHierarchyScope = 'global' | 'current-group'

export interface WorkflowArtifactTaskNode {
  taskId: string
  taskName?: string
  latestCreatedAt: string
  artifacts: ArtifactFile[]
}

export interface WorkflowArtifactToolNode {
  toolId?: string
  toolSlug: string
  toolName: string
  tasks: WorkflowArtifactTaskNode[]
}

export interface WorkflowArtifactGroupNode {
  groupId: string
  groupName: string
  groupSlug: string
  isUngrouped?: boolean
  tools: WorkflowArtifactToolNode[]
}

export interface WorkflowArtifactHierarchyResult {
  groups: WorkflowArtifactGroupNode[]
}

export interface WorkflowArtifactSelectionPath {
  token?: number
  groupId?: string | null
  toolSlug?: string | null
  taskId?: string | null
  artifactId?: string | null
}

interface BuildWorkflowArtifactHierarchyInput {
  groups: WorkbenchGroup[]
  artifacts: ArtifactFile[]
  accept?: string
  scope: WorkflowArtifactHierarchyScope
  currentGroupId?: string | null
}

interface PrimaryGroupMeta {
  groupId: string
  groupName: string
  groupSlug: string
  groupOrder: number
  toolId?: string
  toolSlug: string
  toolName: string
  toolOrder: number
}

function resolveTaskName(artifacts: ArtifactFile[]): string | undefined {
  return artifacts.find((artifact) => artifact.task_name?.trim())?.task_name?.trim()
}

export function buildPrimaryGroupMap(groups: WorkbenchGroup[]): Map<string, PrimaryGroupMeta> {
  const primaryGroupMap = new Map<string, PrimaryGroupMeta>()

  groups.forEach((group, groupOrder) => {
    group.tools.forEach((tool, toolOrder) => {
      if (primaryGroupMap.has(tool.slug)) {
        return
      }

      primaryGroupMap.set(tool.slug, {
        groupId: group.id,
        groupName: group.name,
        groupSlug: group.slug,
        groupOrder,
        toolId: tool.id,
        toolSlug: tool.slug,
        toolName: tool.name,
        toolOrder
      })
    })
  })

  return primaryGroupMap
}

export function buildWorkflowArtifactHierarchy(
  input: BuildWorkflowArtifactHierarchyInput
): WorkflowArtifactHierarchyResult {
  const primaryGroupMap = buildPrimaryGroupMap(input.groups)
  const compatibleArtifacts = filterCompatibleArtifacts(input.artifacts, input.accept)
  const bucketMap = new Map<string, Map<string, Map<string, ArtifactFile[]>>>()

  for (const artifact of compatibleArtifacts) {
    const toolSlug = artifact.tool_slug?.trim()
    const taskId = artifact.task_id?.trim()

    if (!toolSlug || !taskId) {
      continue
    }

    const primaryGroup = primaryGroupMap.get(toolSlug)
    const groupId = primaryGroup?.groupId ?? UNGROUPED_ARTIFACT_GROUP_ID

    if (input.scope === 'current-group') {
      if (!input.currentGroupId || groupId !== input.currentGroupId) {
        continue
      }
    } else if (groupId === UNGROUPED_ARTIFACT_GROUP_ID && input.scope !== 'global') {
      continue
    }

    const toolMap = bucketMap.get(groupId) ?? new Map<string, Map<string, ArtifactFile[]>>()
    const taskMap = toolMap.get(toolSlug) ?? new Map<string, ArtifactFile[]>()
    const taskArtifacts = taskMap.get(taskId) ?? []

    taskArtifacts.push(artifact)
    taskMap.set(taskId, taskArtifacts)
    toolMap.set(toolSlug, taskMap)
    bucketMap.set(groupId, toolMap)
  }

  const groups = input.groups
    .filter((group) => {
      if (input.scope === 'current-group' && input.currentGroupId && group.id !== input.currentGroupId) {
        return false
      }

      return bucketMap.has(group.id)
    })
    .map<WorkflowArtifactGroupNode>((group) => {
      const toolMap = bucketMap.get(group.id) ?? new Map<string, Map<string, ArtifactFile[]>>()
      const tools = group.tools
        .filter((tool) => toolMap.has(tool.slug))
        .map<WorkflowArtifactToolNode>((tool) => {
          const taskMap = toolMap.get(tool.slug) ?? new Map<string, ArtifactFile[]>()
          const tasks = Array.from(taskMap.entries())
            .map<WorkflowArtifactTaskNode>(([taskId, taskArtifacts]) => {
              const artifacts = sortArtifactsByCreatedAtDesc(taskArtifacts)

              return {
                taskId,
                taskName: resolveTaskName(artifacts),
                latestCreatedAt: artifacts[0]?.created_at ?? '',
                artifacts
              }
            })
            .sort((left, right) => Date.parse(right.latestCreatedAt) - Date.parse(left.latestCreatedAt))

          return {
            toolId: tool.id,
            toolSlug: tool.slug,
            toolName: tool.name,
            tasks
          }
        })

      return {
        groupId: group.id,
        groupName: group.name,
        groupSlug: group.slug,
        tools
      }
    })

  if (input.scope === 'global' && bucketMap.has(UNGROUPED_ARTIFACT_GROUP_ID)) {
    const ungroupedToolMap = bucketMap.get(UNGROUPED_ARTIFACT_GROUP_ID) ?? new Map<string, Map<string, ArtifactFile[]>>()
    const ungroupedTools = Array.from(ungroupedToolMap.entries())
      .map<WorkflowArtifactToolNode>(([toolSlug, taskMap]) => {
        const flattenedArtifacts = Array.from(taskMap.values()).flat()
        const latestArtifact = sortArtifactsByCreatedAtDesc(flattenedArtifacts)[0]
        const tasks = Array.from(taskMap.entries())
          .map<WorkflowArtifactTaskNode>(([taskId, taskArtifacts]) => {
            const artifacts = sortArtifactsByCreatedAtDesc(taskArtifacts)

            return {
              taskId,
              taskName: resolveTaskName(artifacts),
              latestCreatedAt: artifacts[0]?.created_at ?? '',
              artifacts
            }
          })
          .sort((left, right) => Date.parse(right.latestCreatedAt) - Date.parse(left.latestCreatedAt))

        return {
          toolId: latestArtifact?.tool_id,
          toolSlug,
          toolName: latestArtifact?.tool_name ?? toolSlug,
          tasks
        }
      })
      .sort((left, right) => left.toolName.localeCompare(right.toolName, 'zh-Hans-CN'))

    groups.push({
      groupId: UNGROUPED_ARTIFACT_GROUP_ID,
      groupName: 'Ungrouped Tools',
      groupSlug: UNGROUPED_ARTIFACT_GROUP_SLUG,
      isUngrouped: true,
      tools: ungroupedTools
    })
  }

  return { groups }
}

export function groupArtifactsIntoHierarchy(
  input: BuildWorkflowArtifactHierarchyInput
): WorkflowArtifactGroupNode[] {
  return buildWorkflowArtifactHierarchy(input).groups
}
