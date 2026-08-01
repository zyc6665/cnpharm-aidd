import type {
  WorkflowArtifact,
  WorkflowArtifactSemanticType,
  WorkflowStepKey,
  WorkflowTaskRef
} from './artifact-types.ts'
import { normalizeWorkflowSemanticType } from './semantic-types.ts'
import {
  type WorkflowToolBindingConfig,
  type WorkflowToolOutputExtractor
} from './contract-bindings.ts'

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

function selectArtifactForFieldBinding(input: {
  artifacts: WorkflowArtifact[]
  semanticType: WorkflowArtifactSemanticType
  invalidArtifactIds?: Iterable<string>
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

    if (isNewerArtifact(artifact, selectedArtifact)) {
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

interface StandardArtifactsSummary {
  artifact_version_ids_by_ref: Record<string, string>
  file_ids_by_artifact_ref: Record<string, string[]>
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function readStandardArtifacts(outputData: unknown): StandardArtifactsSummary | null {
  if (!isObject(outputData)) {
    return null
  }

  const candidate = isObject(outputData.standard_artifacts)
    ? outputData.standard_artifacts
    : isObject(outputData.result) && isObject(outputData.result.standard_artifacts)
      ? outputData.result.standard_artifacts
      : null

  if (!candidate) {
    return null
  }

  const rawVersionIds = candidate.artifact_version_ids_by_ref
  const rawFileIds = candidate.file_ids_by_artifact_ref
  if (!isObject(rawVersionIds) || !isObject(rawFileIds)) {
    return null
  }

  const artifactVersionIds: Record<string, string> = {}
  for (const [key, value] of Object.entries(rawVersionIds)) {
    if (typeof value === 'string' && value) {
      artifactVersionIds[key] = value
    }
  }

  const fileIds: Record<string, string[]> = {}
  for (const [key, value] of Object.entries(rawFileIds)) {
    if (Array.isArray(value)) {
      fileIds[key] = value.filter(
        (item): item is string => typeof item === 'string' && item.length > 0
      )
    }
  }

  return {
    artifact_version_ids_by_ref: artifactVersionIds,
    file_ids_by_artifact_ref: fileIds
  }
}

function resolveStandardArtifactKey(
  extractor: Extract<WorkflowToolOutputExtractor, { source: 'artifact' }>,
  standardArtifacts: StandardArtifactsSummary
): string | null {
  if (
    extractor.artifactName &&
    standardArtifacts.artifact_version_ids_by_ref[extractor.artifactName]
  ) {
    return extractor.artifactName
  }

  const keys = Object.keys(standardArtifacts.artifact_version_ids_by_ref)
  return keys.length === 1 ? keys[0] ?? null : null
}

function findOutputFileById(
  task: WorkflowTaskRef,
  fileId: string
): NonNullable<WorkflowTaskRef['output_files']>[number] | null {
  return (task.output_files ?? []).find((file) => String(file.id) === fileId) ?? null
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

    if (extractor.source === 'artifact') {
      const standardArtifacts = readStandardArtifacts(input.task.output_data)
      if (!standardArtifacts) {
        continue
      }

      const artifactKey = resolveStandardArtifactKey(extractor, standardArtifacts)
      if (!artifactKey) {
        continue
      }

      const artifactVersionId = standardArtifacts.artifact_version_ids_by_ref[artifactKey]
      const fileIds = standardArtifacts.file_ids_by_artifact_ref[artifactKey] ?? []
      const primaryFile = fileIds[0] ? findOutputFileById(input.task, fileIds[0]) : null

      artifacts.push({
        id: `${input.task.id}:${extractor.semanticType}:${artifactVersionId}`,
        semanticType: extractor.semanticType,
        name: primaryFile?.original_name ?? primaryFile?.filename ?? artifactKey,
        stepKey: input.stepKey,
        toolSlug: input.binding.toolSlug,
        taskId: input.task.id,
        fileId: primaryFile?.id ?? fileIds[0],
        url: primaryFile?.url,
        contentType: primaryFile?.content_type,
        createdAt,
        metadata: {
          source: 'standard_artifacts',
          artifactName: artifactKey,
          artifactVersionId,
          fileIds
        }
      })

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
      invalidArtifactIds: input.invalidArtifactIds
    })
  }))
}
