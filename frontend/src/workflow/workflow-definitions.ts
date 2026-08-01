import type { ArtifactFile, WorkflowDefinition } from '../types/models'
import { sortArtifactsByCreatedAtDesc } from '../utils/artifact-sorting'

const WORKFLOW_INPUT_PREFIX = 'workflow_input:'

export interface WorkflowInputRequirement {
  readonly key: string
  readonly semanticType: string
  readonly slotName?: string
  readonly label: string
}

function normalizeSemanticType(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }

  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

function extractWorkflowInputSemanticType(source: unknown): string | null {
  if (typeof source !== 'string' || !source.startsWith(WORKFLOW_INPUT_PREFIX)) {
    return null
  }

  return normalizeSemanticType(source.slice(WORKFLOW_INPUT_PREFIX.length))
}

function upsertWorkflowInputRequirement(
  requirements: Map<string, WorkflowInputRequirement>,
  semanticType: string,
  slotName?: string
) {
  const existing = requirements.get(semanticType)
  if (existing?.slotName || (!slotName && existing)) {
    return
  }

  requirements.set(semanticType, {
    key: semanticType,
    semanticType,
    slotName,
    label: slotName ? `${slotName}: ${semanticType}` : semanticType
  })
}

export function extractWorkflowInputRequirements(definition: WorkflowDefinition): string[] {
  return extractWorkflowInputRequirementDetails(definition).map(requirement => requirement.key)
}

export function extractWorkflowInputRequirementDetails(
  definition: WorkflowDefinition
): WorkflowInputRequirement[] {
  const semanticTypes = new Set<string>()
  const requirements = new Map<string, WorkflowInputRequirement>()

  for (const node of definition.nodes ?? []) {
    const semanticInputs = node.semantic_inputs
    if (semanticInputs && typeof semanticInputs === 'object') {
      for (const source of Object.values(semanticInputs)) {
        const semanticType = extractWorkflowInputSemanticType(source)
        if (semanticType) {
          semanticTypes.add(semanticType)
          upsertWorkflowInputRequirement(requirements, semanticType)
        }
      }
    }

    const artifactInputs = node.artifact_inputs
    if (!artifactInputs || typeof artifactInputs !== 'object') {
      continue
    }

    for (const [slotName, source] of Object.entries(artifactInputs)) {
      const semanticType = extractWorkflowInputSemanticType(source)
      if (semanticType) {
        semanticTypes.add(semanticType)
        upsertWorkflowInputRequirement(requirements, semanticType, slotName)
      }
    }
  }

  return [...semanticTypes].map(
    semanticType =>
      requirements.get(semanticType) ?? {
        key: semanticType,
        semanticType,
        label: semanticType
      }
  )
}

export function buildWorkflowInputFileMap(
  requirements: string[],
  selections: Record<string, string | null | undefined>
): Record<string, string> {
  const inputFiles: Record<string, string> = {}

  for (const semanticType of requirements) {
    const fileId = selections[semanticType]
    if (typeof fileId === 'string' && fileId.trim()) {
      inputFiles[semanticType] = fileId
    }
  }

  return inputFiles
}

export function findLatestArtifactForSemanticType(
  artifacts: ArtifactFile[],
  semanticType: string
): ArtifactFile | null {
  const matchingArtifacts = artifacts.filter(artifact => artifact.semantic_type === semanticType)
  if (matchingArtifacts.length === 0) {
    return null
  }

  return sortArtifactsByCreatedAtDesc(matchingArtifacts)[0] ?? null
}
