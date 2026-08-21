import type { ToolContract, WorkbenchGroupTool } from '@/types/models'
import type { WorkflowArtifact, WorkflowArtifactSemanticType, WorkflowStepKey } from './artifact-types.ts'
import { isWorkflowSemanticType, normalizeWorkflowSemanticType } from './semantic-types.ts'

export interface WorkflowToolFieldBinding {
  readonly semanticType: WorkflowArtifactSemanticType
  readonly field: string
  readonly required?: boolean
  readonly acceptedExtensions?: readonly string[]
}

export interface ArtifactInputSlot {
  readonly name: string
  readonly type: WorkflowArtifactSemanticType
  readonly required: boolean
  readonly rolePreferences?: readonly string[]
  readonly requiredRoles?: readonly string[]
  readonly readinessPolicy?: string | null
  readonly suggestedPreparationTool?: string | null
}

export interface ArtifactOutputSlot {
  readonly name: string
  readonly type: WorkflowArtifactSemanticType
  readonly cardinality: 'one' | 'many'
  readonly required: boolean
}

export interface ToolArtifactSlots {
  readonly inputs: readonly ArtifactInputSlot[]
  readonly outputs: readonly ArtifactOutputSlot[]
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

interface WorkflowToolArtifactOutputExtractor {
  readonly semanticType: WorkflowArtifactSemanticType
  readonly source: 'artifact'
  readonly artifactName?: string
  readonly match: {
    readonly type?: string
    readonly name?: string
  }
}

interface WorkflowToolDataOutputExtractor {
  readonly semanticType: WorkflowArtifactSemanticType
  readonly source: 'output_data'
  readonly path: string
}

export type WorkflowToolOutputExtractor =
  | WorkflowToolFileOutputExtractor
  | WorkflowToolArtifactOutputExtractor
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

function toWorkflowSemanticType(value: string): WorkflowArtifactSemanticType | null {
  const semanticType = normalizeWorkflowSemanticType(value)
  return isWorkflowSemanticType(semanticType) ? semanticType : null
}

function resolveStepKey(contract: ToolContract): WorkflowStepKey {
  const stage = contract.capability.stage ?? contract.capability.capability ?? ''
  return STAGE_STEP_MAP[stage] ?? 'moleculeGenerationOrVirtualScreening'
}

export function deriveArtifactSlotsFromToolContract(
  contract?: ToolContract | null
): ToolArtifactSlots {
  const artifactInputs = contract?.artifacts?.inputs ?? []
  const artifactOutputs = contract?.artifacts?.outputs ?? []

  return {
    inputs: artifactInputs
      .map((slot) => {
        const type = toWorkflowSemanticType(slot.type)
        if (!type || !slot.name) {
          return null
        }

        const inputSlot: ArtifactInputSlot = {
          name: slot.name,
          type,
          required: slot.required ?? true
        }
        const hasRoleAwareMetadata =
          'role_preferences' in slot ||
          'required_roles' in slot ||
          'readiness_policy' in slot ||
          'suggested_preparation_tool' in slot
        if (hasRoleAwareMetadata) {
          return {
            ...inputSlot,
            rolePreferences: toStringList(slot.role_preferences),
            requiredRoles: 'required_roles' in slot ? toStringList(slot.required_roles) : undefined,
            readinessPolicy: slot.readiness_policy ?? null,
            suggestedPreparationTool: slot.suggested_preparation_tool ?? null
          }
        }

        return inputSlot
      })
      .filter((slot): slot is ArtifactInputSlot => slot !== null),
    outputs: artifactOutputs
      .map((slot) => {
        const type = toWorkflowSemanticType(slot.type)
        if (!type || !slot.name) {
          return null
        }

        return {
          name: slot.name,
          type,
          cardinality: slot.cardinality ?? 'one',
          required: slot.required ?? true
        }
      })
      .filter((slot): slot is ArtifactOutputSlot => slot !== null)
  }
}

function toStringList(value: unknown): readonly string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.map(item => String(item)).filter(Boolean)
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

      if (output.source === 'artifact') {
        const artifactSlot = contract.artifacts?.outputs?.find(
          (slot) => slot.type === output.semantic_type
        )
        const artifactName = output.match?.name ?? artifactSlot?.name

        return {
          semanticType,
          source: 'artifact' as const,
          artifactName: artifactName ?? undefined,
          match: {
            type: output.match?.type ?? output.semantic_type,
            name: artifactName ?? undefined
          }
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
