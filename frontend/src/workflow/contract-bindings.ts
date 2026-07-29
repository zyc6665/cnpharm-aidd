import type { ToolContract, WorkbenchGroupTool } from '@/types/models'
import type { WorkflowArtifact, WorkflowArtifactSemanticType, WorkflowStepKey } from './artifact-types.ts'
import {
  WORKFLOW_ARTIFACT_SEMANTIC_TYPES
} from './semantic-types.ts'
import { normalizeWorkflowSemanticType } from './semantic-types.ts'

export interface WorkflowToolFieldBinding {
  readonly semanticType: WorkflowArtifactSemanticType
  readonly field: string
  readonly required?: boolean
  readonly acceptedExtensions?: readonly string[]
}

interface WorkflowToolOutputFileMatch {
  readonly filenameIncludesAny?: readonly string[]
  readonly extension?: string
  readonly contentType?: string
}

interface WorkflowToolFileOutputExtractor {
  readonly semanticType: WorkflowArtifactSemanticType
  readonly source: 'output_files'
  readonly match: WorkflowToolOutputFileMatch
}

interface WorkflowToolDataOutputExtractor {
  readonly semanticType: WorkflowArtifactSemanticType
  readonly source: 'output_data'
  readonly path: string
}

export type WorkflowToolOutputExtractor =
  | WorkflowToolFileOutputExtractor
  | WorkflowToolDataOutputExtractor

export interface WorkflowToolBindingConfig {
  readonly toolSlug: string
  readonly stepKey: WorkflowStepKey
  readonly acceptedInputTypes: readonly WorkflowArtifactSemanticType[]
  readonly fieldBindings: readonly WorkflowToolFieldBinding[]
  readonly outputExtractors: readonly WorkflowToolOutputExtractor[]
}

const STAGE_STEP_MAP: Readonly<Record<string, WorkflowStepKey>> = {
  pocket_exploration: 'pocketExploration',
  pocket_prediction: 'pocketExploration',
  molecule_generation: 'moleculeGenerationOrVirtualScreening',
  virtual_screening: 'moleculeGenerationOrVirtualScreening',
  docking_scoring: 'molecularDockingAndAffinityPrediction',
  docking: 'molecularDockingAndAffinityPrediction',
  affinity_prediction: 'molecularDockingAndAffinityPrediction',
  property_prediction: 'propertyPrediction',
  lead_optimization: 'leadOptimization'
}

export interface WorkflowPreflightInputReport {
  field: string
  semanticType: WorkflowArtifactSemanticType
  required: boolean
  artifact: WorkflowArtifact | null
  missing: boolean
  invalidFormat: boolean
  acceptedExtensions: readonly string[]
}

export interface WorkflowPreflightReport {
  ready: boolean
  inputs: WorkflowPreflightInputReport[]
  expectedOutputs: WorkflowArtifactSemanticType[]
}

function isWorkflowSemanticType(value: string): value is WorkflowArtifactSemanticType {
  return (WORKFLOW_ARTIFACT_SEMANTIC_TYPES as readonly string[]).includes(value)
}

function toWorkflowSemanticType(value: string): WorkflowArtifactSemanticType | null {
  const semanticType = normalizeWorkflowSemanticType(value)
  return isWorkflowSemanticType(semanticType) ? semanticType : null
}

function resolveStepKey(contract: ToolContract): WorkflowStepKey {
  const stage = contract.capability.stage ?? contract.capability.capability ?? ''
  return STAGE_STEP_MAP[stage] ?? 'moleculeGenerationOrVirtualScreening'
}

function isNewerArtifact(candidate: WorkflowArtifact, current: WorkflowArtifact): boolean {
  const candidateTimestamp = Date.parse(candidate.createdAt)
  const currentTimestamp = Date.parse(current.createdAt)

  if (!Number.isNaN(candidateTimestamp) && !Number.isNaN(currentTimestamp)) {
    return candidateTimestamp > currentTimestamp
  }

  return candidate.createdAt > current.createdAt
}

function selectLatestArtifact(input: {
  artifacts: readonly WorkflowArtifact[]
  semanticType: WorkflowArtifactSemanticType
  invalidArtifactIds?: Iterable<string>
}): WorkflowArtifact | null {
  const invalidArtifactIds = new Set(input.invalidArtifactIds)
  let latestArtifact: WorkflowArtifact | null = null

  for (const artifact of input.artifacts) {
    if (normalizeWorkflowSemanticType(artifact.semanticType) !== input.semanticType) {
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

function hasAcceptedExtension(
  artifact: WorkflowArtifact | null,
  acceptedExtensions: readonly string[]
): boolean {
  if (!artifact || acceptedExtensions.length === 0) {
    return true
  }

  const artifactName = artifact.name.toLowerCase()
  return acceptedExtensions.some((extension) => artifactName.endsWith(extension.toLowerCase()))
}

export function buildWorkflowToolBindingFromContract(
  contract?: ToolContract | null
): WorkflowToolBindingConfig | null {
  if (!contract || contract.validation.status !== 'valid' || contract.capability.enabled !== true) {
    return null
  }

  const fieldBindings = contract.capability.inputs
    .map((input) => {
      const semanticType = toWorkflowSemanticType(input.semantic_type)
      if (!semanticType) {
        return null
      }

      return {
        semanticType,
        field: input.field || semanticType,
        required: input.required ?? true,
        acceptedExtensions: input.accepted_extensions ?? []
      }
    })
    .filter((input): input is NonNullable<typeof input> => input !== null)

  const outputExtractors = contract.capability.outputs
    .map((output) => {
      const semanticType = toWorkflowSemanticType(output.semantic_type)
      if (!semanticType) {
        return null
      }

      if (output.source === 'output_data') {
        return {
          semanticType,
          source: 'output_data' as const,
          path: output.path || semanticType
        }
      }

      return {
        semanticType,
        source: 'output_files' as const,
        match: {
          extension: output.match?.extension ?? undefined,
          filenameIncludesAny: output.match?.filename_contains_any ?? undefined,
          contentType: output.match?.content_type ?? undefined
        }
      }
    })
    .filter((output): output is NonNullable<typeof output> => output !== null)

  if (fieldBindings.length === 0 && outputExtractors.length === 0) {
    return null
  }

  return {
    toolSlug: contract.slug,
    stepKey: resolveStepKey(contract),
    acceptedInputTypes: fieldBindings.map((input) => input.semanticType),
    fieldBindings,
    outputExtractors
  }
}

export function resolveWorkflowToolBinding(
  tool?: WorkbenchGroupTool | null
): WorkflowToolBindingConfig | null {
  return buildWorkflowToolBindingFromContract(tool?.contract)
}

export function buildWorkflowPreflightReport(input: {
  binding: WorkflowToolBindingConfig
  artifacts: readonly WorkflowArtifact[]
  invalidArtifactIds?: Iterable<string>
}): WorkflowPreflightReport {
  const inputs = input.binding.fieldBindings.map<WorkflowPreflightInputReport>((fieldBinding) => {
    const artifact = selectLatestArtifact({
      artifacts: input.artifacts,
      semanticType: fieldBinding.semanticType,
      invalidArtifactIds: input.invalidArtifactIds
    })
    const acceptedExtensions = fieldBinding.acceptedExtensions ?? []
    const invalidFormat = !hasAcceptedExtension(artifact, acceptedExtensions)

    return {
      field: fieldBinding.field,
      semanticType: fieldBinding.semanticType,
      required: fieldBinding.required ?? true,
      artifact,
      missing: (fieldBinding.required ?? true) && artifact === null,
      invalidFormat,
      acceptedExtensions
    }
  })

  return {
    ready: inputs.every((item) => !item.missing && !item.invalidFormat),
    inputs,
    expectedOutputs: Array.from(
      new Set(input.binding.outputExtractors.map((output) => output.semanticType))
    )
  }
}
