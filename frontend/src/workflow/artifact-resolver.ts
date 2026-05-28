import type { WorkflowArtifact, WorkflowArtifactSemanticType, WorkflowStepKey, WorkflowTaskRef } from './artifact-types.ts'
import { WORKFLOW_TOOL_BINDINGS, type WorkflowBoundToolSlug, type WorkflowToolOutputExtractor } from './tool-bindings.ts'

function isNewerArtifact(candidate: WorkflowArtifact, current: WorkflowArtifact): boolean {
  const candidateTimestamp = Date.parse(candidate.createdAt)
  const currentTimestamp = Date.parse(current.createdAt)

  if (!Number.isNaN(candidateTimestamp) && !Number.isNaN(currentTimestamp)) {
    return candidateTimestamp > currentTimestamp
  }

  return candidate.createdAt > current.createdAt
}

export function selectLatestValidArtifactBySemanticType(input: {
  artifacts: WorkflowArtifact[]
  semanticType: WorkflowArtifactSemanticType
  invalidArtifactIds?: Iterable<string>
}): WorkflowArtifact | null {
  const invalidArtifactIds = new Set(input.invalidArtifactIds)
  let latestArtifact: WorkflowArtifact | null = null

  for (const artifact of input.artifacts) {
    if (artifact.semanticType !== input.semanticType) {
      continue
    }

    if (invalidArtifactIds.has(artifact.id)) {
      continue
    }

    if (latestArtifact === null || isNewerArtifact(artifact, latestArtifact)) {
      latestArtifact = artifact
    }
  }

  return latestArtifact
}

function matchesOutputFile(input: {
  extractor: Extract<WorkflowToolOutputExtractor, { source: 'output_files' }>
  file: NonNullable<WorkflowTaskRef['output_files']>[number]
}): boolean {
  const filename = input.file.original_name ?? input.file.filename ?? ''
  const contentType = input.file.content_type ?? ''
  const { match } = input.extractor

  if (match.filenameIncludes && !filename.includes(match.filenameIncludes)) {
    return false
  }

  if (match.contentType && contentType !== match.contentType) {
    return false
  }

  return true
}

function readOutputDataByPath(outputData: unknown, path: string): unknown {
  if (!outputData || typeof outputData !== 'object') {
    return undefined
  }

  return path.split('.').reduce<unknown>((currentValue, segment) => {
    if (!currentValue || typeof currentValue !== 'object') {
      return undefined
    }

    return (currentValue as Record<string, unknown>)[segment]
  }, outputData)
}

export function extractArtifactsFromTaskResult(input: {
  stepKey: WorkflowStepKey
  toolSlug: WorkflowBoundToolSlug
  task: WorkflowTaskRef
}): WorkflowArtifact[] {
  const binding = WORKFLOW_TOOL_BINDINGS[input.toolSlug]
  if (!binding) {
    return []
  }

  const createdAt = input.task.finished_at ?? input.task.updated_at ?? input.task.created_at
  const artifacts: WorkflowArtifact[] = []

  for (const extractor of binding.outputExtractors) {
    if (extractor.source === 'output_files') {
      const outputFiles = input.task.output_files ?? []

      for (const file of outputFiles) {
        if (!matchesOutputFile({ extractor, file })) {
          continue
        }

        artifacts.push({
          id: `${input.task.id}:${extractor.semanticType}:${String(file.id ?? file.filename ?? file.original_name ?? artifacts.length)}`,
          semanticType: extractor.semanticType,
          name: file.original_name ?? file.filename ?? `${extractor.semanticType}-${input.task.id}`,
          stepKey: input.stepKey,
          toolSlug: input.toolSlug,
          taskId: input.task.id,
          fileId: file.id,
          url: file.url,
          contentType: file.content_type,
          createdAt,
          metadata: {
            source: 'output_files'
          }
        })
      }

      continue
    }

    const extractedValue = readOutputDataByPath(input.task.output_data, extractor.path)
    if (extractedValue === undefined || extractedValue === null) {
      continue
    }

    artifacts.push({
      id: `${input.task.id}:${extractor.semanticType}:data`,
      semanticType: extractor.semanticType,
      name: `${extractor.semanticType}-${input.task.id}`,
      stepKey: input.stepKey,
      toolSlug: input.toolSlug,
      taskId: input.task.id,
      createdAt,
      metadata: {
        source: 'output_data',
        path: extractor.path,
        value: extractedValue
      }
    })
  }

  return artifacts
}

export function resolveWorkflowInputSourcesForTool(input: {
  toolSlug: WorkflowBoundToolSlug
  artifacts: WorkflowArtifact[]
  invalidArtifactIds?: Iterable<string>
}): Array<{
  field: string
  semanticType: WorkflowArtifactSemanticType
  artifact: WorkflowArtifact | null
}> {
  const binding = WORKFLOW_TOOL_BINDINGS[input.toolSlug]
  if (!binding) {
    return []
  }

  return binding.fieldBindings.map((fieldBinding) => ({
    field: fieldBinding.field,
    semanticType: fieldBinding.semanticType,
    artifact: selectLatestValidArtifactBySemanticType({
      artifacts: input.artifacts,
      semanticType: fieldBinding.semanticType,
      invalidArtifactIds: input.invalidArtifactIds
    })
  }))
}
