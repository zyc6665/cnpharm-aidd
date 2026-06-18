import type {
  WorkflowArtifact,
  WorkflowArtifactSemanticType,
  WorkflowStepKey,
  WorkflowTaskRef
} from './artifact-types.ts'
import { normalizeWorkflowSemanticType } from './semantic-types.ts'
import {
  WORKFLOW_TOOL_BINDINGS,
  type WorkflowBoundToolSlug,
  type WorkflowToolBindingConfig,
  type WorkflowToolOutputExtractor
} from './tool-bindings.ts'

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
  const requestedSemanticType = normalizeWorkflowSemanticType(input.semanticType)
  let latestArtifact: WorkflowArtifact | null = null

  for (const artifact of input.artifacts) {
    if (normalizeWorkflowSemanticType(artifact.semanticType) !== requestedSemanticType) {
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

function getArtifactPreferenceRank(input: {
  artifact: WorkflowArtifact
  preferredArtifactNameIncludes?: readonly string[]
}): number {
  const preferences = input.preferredArtifactNameIncludes
  if (!preferences?.length) {
    return Number.POSITIVE_INFINITY
  }

  const artifactName = input.artifact.name.toLowerCase()
  const matchedIndex = preferences.findIndex((token) => artifactName.includes(token.toLowerCase()))
  return matchedIndex === -1 ? Number.POSITIVE_INFINITY : matchedIndex
}

function selectArtifactForFieldBinding(input: {
  artifacts: WorkflowArtifact[]
  semanticType: WorkflowArtifactSemanticType
  invalidArtifactIds?: Iterable<string>
  preferredArtifactNameIncludes?: readonly string[]
}): WorkflowArtifact | null {
  const invalidArtifactIds = new Set(input.invalidArtifactIds)
  const requestedSemanticType = normalizeWorkflowSemanticType(input.semanticType)
  let selectedArtifact: WorkflowArtifact | null = null

  for (const artifact of input.artifacts) {
    if (normalizeWorkflowSemanticType(artifact.semanticType) !== requestedSemanticType) {
      continue
    }

    if (invalidArtifactIds.has(artifact.id)) {
      continue
    }

    if (selectedArtifact === null) {
      selectedArtifact = artifact
      continue
    }

    const candidateRank = getArtifactPreferenceRank({
      artifact,
      preferredArtifactNameIncludes: input.preferredArtifactNameIncludes
    })
    const currentRank = getArtifactPreferenceRank({
      artifact: selectedArtifact,
      preferredArtifactNameIncludes: input.preferredArtifactNameIncludes
    })

    if (candidateRank < currentRank) {
      selectedArtifact = artifact
      continue
    }

    if (candidateRank === currentRank && isNewerArtifact(artifact, selectedArtifact)) {
      selectedArtifact = artifact
    }
  }

  return selectedArtifact
}

function matchesOutputFile(input: {
  extractor: Extract<WorkflowToolOutputExtractor, { source: 'output_files' }>
  file: NonNullable<WorkflowTaskRef['output_files']>[number]
}): boolean {
  const filename = input.file.original_name ?? input.file.filename ?? ''
  const contentType = input.file.content_type ?? ''
  const { match } = input.extractor

  if (match.extension && !filename.toLowerCase().endsWith(match.extension.toLowerCase())) {
    return false
  }

  if (match.filenameIncludes && !filename.includes(match.filenameIncludes)) {
    return false
  }

  if (
    match.filenameIncludesAny?.length &&
    !match.filenameIncludesAny.some((token) => filename.includes(token))
  ) {
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

  return extractArtifactsFromTaskResultWithBinding({
    stepKey: input.stepKey,
    binding,
    task: input.task
  })
}

export function extractArtifactsFromTaskResultWithBinding(input: {
  stepKey: WorkflowStepKey
  binding: WorkflowToolBindingConfig
  task: WorkflowTaskRef
}): WorkflowArtifact[] {
  const createdAt = input.task.finished_at ?? input.task.updated_at ?? input.task.created_at
  const artifacts: WorkflowArtifact[] = []

  for (const extractor of input.binding.outputExtractors) {
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
          toolSlug: input.binding.toolSlug,
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
      toolSlug: input.binding.toolSlug,
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

  return resolveWorkflowInputSourcesForBinding({
    binding,
    artifacts: input.artifacts,
    invalidArtifactIds: input.invalidArtifactIds
  })
}

export function resolveWorkflowInputSourcesForBinding(input: {
  binding: WorkflowToolBindingConfig
  artifacts: WorkflowArtifact[]
  invalidArtifactIds?: Iterable<string>
}): Array<{
  field: string
  semanticType: WorkflowArtifactSemanticType
  artifact: WorkflowArtifact | null
}> {
  return input.binding.fieldBindings.map((fieldBinding) => ({
    field: fieldBinding.field,
    semanticType: fieldBinding.semanticType,
    artifact: selectArtifactForFieldBinding({
      artifacts: input.artifacts,
      semanticType: fieldBinding.semanticType,
      invalidArtifactIds: input.invalidArtifactIds,
      preferredArtifactNameIncludes:
        'preferredArtifactNameIncludes' in fieldBinding
          ? fieldBinding.preferredArtifactNameIncludes
          : undefined
    })
  }))
}
