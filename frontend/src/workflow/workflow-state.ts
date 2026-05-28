import {
  WORKFLOW_STEP_KEYS,
  type WorkflowArtifact,
  type WorkflowArtifactSemanticType,
  type WorkflowStepKey,
  type WorkflowStepStateMap,
  type WorkflowStepStatus
} from './artifact-types.ts'
import { AIDD_WORKFLOW_STEP_MAP } from './aidd-catalog.ts'
import { selectLatestValidArtifactBySemanticType } from './artifact-resolver.ts'
import { WORKFLOW_TOOL_BINDINGS, type WorkflowBoundToolSlug } from './tool-bindings.ts'

type WorkflowReadinessStatus = Extract<
  WorkflowStepStatus,
  'idle' | 'ready' | 'needs_tool_selection'
>

type WorkflowRestoreSelectionStatus = Extract<WorkflowStepStatus, 'idle' | 'needs_tool_selection'>

function getFallbackRequiredInputTypes(
  stepKey: WorkflowStepKey
): readonly WorkflowArtifactSemanticType[] {
  return AIDD_WORKFLOW_STEP_MAP[stepKey]?.requiredInputTypes ?? []
}

function getRequiredInputTypes(input: {
  stepKey: WorkflowStepKey
  selectedToolSlug?: WorkflowBoundToolSlug | null
}): readonly WorkflowArtifactSemanticType[] {
  if (input.selectedToolSlug != null) {
    const selectedBinding = WORKFLOW_TOOL_BINDINGS[input.selectedToolSlug]

    if (selectedBinding?.stepKey === input.stepKey) {
      return selectedBinding.acceptedInputTypes
    }
  }

  return getFallbackRequiredInputTypes(input.stepKey)
}

function hasAllRequiredArtifacts(input: {
  artifacts: WorkflowArtifact[]
  requiredInputTypes: readonly WorkflowArtifactSemanticType[]
  invalidArtifactIds?: Iterable<string>
}): boolean {
  return input.requiredInputTypes.every(
    (semanticType) =>
      selectLatestValidArtifactBySemanticType({
        artifacts: input.artifacts,
        semanticType,
        invalidArtifactIds: input.invalidArtifactIds
      }) !== null
  )
}

export function computeStepReadinessStatus(input: {
  stepKey: WorkflowStepKey
  artifacts: WorkflowArtifact[]
  selectedToolSlug?: WorkflowBoundToolSlug | null
  invalidArtifactIds?: Iterable<string>
}): WorkflowReadinessStatus {
  const requiredInputTypes = getRequiredInputTypes({
    stepKey: input.stepKey,
    selectedToolSlug: input.selectedToolSlug
  })

  if (
    !hasAllRequiredArtifacts({
      artifacts: input.artifacts,
      requiredInputTypes,
      invalidArtifactIds: input.invalidArtifactIds
    })
  ) {
    return 'idle'
  }

  const hasValidSelectedTool =
    input.selectedToolSlug != null && WORKFLOW_TOOL_BINDINGS[input.selectedToolSlug]?.stepKey === input.stepKey

  return hasValidSelectedTool ? 'ready' : 'needs_tool_selection'
}

export function invalidateCompletedDownstreamSteps(input: {
  fromStepKey: WorkflowStepKey
  stepStateByKey: WorkflowStepStateMap
}): WorkflowStepStateMap {
  const nextStepStateByKey: WorkflowStepStateMap = { ...input.stepStateByKey }
  const fromStepIndex = WORKFLOW_STEP_KEYS.indexOf(input.fromStepKey)

  if (fromStepIndex === -1) {
    return nextStepStateByKey
  }

  for (const stepKey of WORKFLOW_STEP_KEYS.slice(fromStepIndex + 1)) {
    const stepState = nextStepStateByKey[stepKey]

    if (stepState?.status === 'completed') {
      nextStepStateByKey[stepKey] = {
        ...stepState,
        status: 'invalidated'
      }
    }
  }

  return nextStepStateByKey
}

export function resolveToolSelectionStatusOnRestore(input: {
  persistedToolSlug?: WorkflowBoundToolSlug | null
  availableToolSlugs: readonly WorkflowBoundToolSlug[]
}): WorkflowRestoreSelectionStatus {
  if (
    input.persistedToolSlug != null &&
    !input.availableToolSlugs.includes(input.persistedToolSlug)
  ) {
    return 'needs_tool_selection'
  }

  return 'idle'
}
