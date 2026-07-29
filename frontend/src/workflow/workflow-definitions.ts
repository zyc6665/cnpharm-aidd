import type { ArtifactFile, WorkflowDefinition } from '../types/models'
import { sortArtifactsByCreatedAtDesc } from '../utils/artifact-sorting'

const WORKFLOW_INPUT_PREFIX = 'workflow_input:'

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

export function extractWorkflowInputRequirements(definition: WorkflowDefinition): string[] {
  const semanticTypes = new Set<string>()

  for (const node of definition.nodes ?? []) {
    if (!node.semantic_inputs || typeof node.semantic_inputs !== 'object') {
      continue
    }

    for (const source of Object.values(node.semantic_inputs)) {
      const semanticType = extractWorkflowInputSemanticType(source)
      if (semanticType) {
        semanticTypes.add(semanticType)
      }
    }
  }

  return [...semanticTypes]
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
  const matchingArtifacts = artifacts.filter((artifact) => artifact.semantic_type === semanticType)
  if (matchingArtifacts.length === 0) {
    return null
  }

  return sortArtifactsByCreatedAtDesc(matchingArtifacts)[0] ?? null
}
