import type { WorkflowArtifactSemanticType, WorkflowTaskRef } from './artifact-types.ts'
import type { WorkflowTemplate } from './template-types.ts'
import type { ArtifactFile } from '../types/models.d.ts'
import { formatWorkflowKey } from './i18n-utils.ts'

export interface WorkflowNodeInputRequirement {
  semanticType: WorkflowArtifactSemanticType
  sourceNodeId: string
  edgeId: string
}

export interface WorkflowNodeArtifactRecommendation extends WorkflowNodeInputRequirement {
  artifact: ArtifactFile | null
}

export interface WorkflowEdgeSuggestion {
  sourceNodeId: string
  sourceNodeTitle: string
  targetNodeId: string
  semanticType: WorkflowArtifactSemanticType
}

export function resolveNodeInputRequirements(input: {
  template: WorkflowTemplate
  nodeId: string
}): WorkflowNodeInputRequirement[] {
  return input.template.edges
    .filter(edge => edge.target === input.nodeId && edge.artifactType)
    .map(edge => ({
      semanticType: edge.artifactType as WorkflowArtifactSemanticType,
      sourceNodeId: edge.source,
      edgeId: edge.id
    }))
}

export function recommendArtifactsForNode(input: {
  template: WorkflowTemplate
  nodeId: string
  artifacts: ArtifactFile[]
  taskByNode: Record<string, WorkflowTaskRef>
}): WorkflowNodeArtifactRecommendation[] {
  return resolveNodeInputRequirements(input).map(requirement => {
    const sourceTask = input.taskByNode[requirement.sourceNodeId]

    if (!sourceTask || sourceTask.status !== 'success') {
      return {
        ...requirement,
        artifact: null
      }
    }

    return {
      ...requirement,
      artifact: findLatestArtifactForTask(input.artifacts, sourceTask.id)
    }
  })
}

function findLatestArtifactForTask(artifacts: ArtifactFile[], taskId: string): ArtifactFile | null {
  return artifacts
    .filter(artifact => artifact.task_id === taskId)
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))[0] ?? null
}

export function suggestWorkflowEdgesForNode(input: {
  template: WorkflowTemplate
  nodeId: string
}): WorkflowEdgeSuggestion[] {
  const targetNode = input.template.nodes.find(node => node.id === input.nodeId)
  if (!targetNode?.requiredInputTypes?.length) {
    return []
  }

  const existingEdgeKeys = new Set(
    input.template.edges
      .filter(edge => edge.target === input.nodeId && edge.artifactType)
      .map(edge => `${edge.source}:${edge.artifactType}`)
  )

  return targetNode.requiredInputTypes.flatMap(semanticType => {
    return input.template.nodes
      .filter(node => node.id !== input.nodeId)
      .filter(node => node.producedOutputTypes?.includes(semanticType))
      .filter(node => !existingEdgeKeys.has(`${node.id}:${semanticType}`))
      .map(node => ({
        sourceNodeId: node.id,
        sourceNodeTitle: formatWorkflowKey(node.titleKey),
        targetNodeId: input.nodeId,
        semanticType
      }))
  })
}
