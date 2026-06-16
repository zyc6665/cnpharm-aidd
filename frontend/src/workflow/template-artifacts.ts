import type { WorkflowArtifactSemanticType, WorkflowTaskRef } from './artifact-types.ts'
import type { WorkflowTemplate } from './template-types.ts'
import type { ArtifactFile } from '../types/models.d.ts'

export interface WorkflowNodeInputRequirement {
  semanticType: WorkflowArtifactSemanticType
  sourceNodeId: string
  edgeId: string
}

export interface WorkflowNodeArtifactRecommendation extends WorkflowNodeInputRequirement {
  artifact: ArtifactFile | null
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
