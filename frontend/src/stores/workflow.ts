import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { TaskStatus } from '@/types/models'
import {
  type WorkflowArtifact,
  type WorkflowSelectedToolMap,
  type WorkflowSession,
  type WorkflowStepDraftMap,
  type WorkflowStepKey,
  type WorkflowStepRecord,
  type WorkflowStepStateMap,
  type WorkflowTaskMap,
  type WorkflowTaskRef
} from '@/workflow/artifact-types'
import { AIDD_WORKFLOW_STEP_ORDER } from '@/workflow/aidd-catalog'
import { buildWorkflowStepRecordFromTask, toWorkflowTaskRef } from '@/workflow/task-state'
import { extractArtifactsFromTaskResult } from '@/workflow/artifact-resolver'
import { invalidateCompletedDownstreamSteps, computeStepReadinessStatus } from '@/workflow/workflow-state'
import type { WorkflowBoundToolSlug } from '@/workflow/tool-bindings'

function getInitialActiveStepKey(): WorkflowStepKey {
  const initialStepKey = AIDD_WORKFLOW_STEP_ORDER[0]

  if (!initialStepKey) {
    throw new Error('AIDD workflow step order must define at least one step')
  }

  return initialStepKey
}

function nowIsoString(): string {
  return new Date().toISOString()
}

function createWorkflowSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  return `workflow-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function createInitialWorkflowSession(ownerUserId?: string): WorkflowSession {
  return {
    sessionId: createWorkflowSessionId(),
    activeStepKey: getInitialActiveStepKey(),
    selectedToolByStep: {},
    stepFormDrafts: {},
    taskByStep: {},
    stepStateByKey: {},
    artifacts: [],
    invalidArtifactIds: [],
    lastUpdatedAt: nowIsoString(),
    ownerUserId
  }
}

export const useWorkflowStore = defineStore('workflow', () => {
  const initialSession = createInitialWorkflowSession()

  const sessionId = ref(initialSession.sessionId)
  const activeStepKey = ref<WorkflowStepKey>(initialSession.activeStepKey)
  const selectedToolByStep = ref<WorkflowSelectedToolMap>(initialSession.selectedToolByStep)
  const stepFormDrafts = ref<WorkflowStepDraftMap>(initialSession.stepFormDrafts)
  const taskByStep = ref<WorkflowTaskMap>(initialSession.taskByStep)
  const stepStateByKey = ref<WorkflowStepStateMap>(initialSession.stepStateByKey)
  const artifacts = ref<WorkflowArtifact[]>(initialSession.artifacts)
  const invalidArtifactIds = ref<string[]>(initialSession.invalidArtifactIds)
  const lastUpdatedAt = ref(initialSession.lastUpdatedAt)
  const ownerUserId = ref<string | undefined>(initialSession.ownerUserId)

  const session = computed<WorkflowSession>(() => ({
    sessionId: sessionId.value,
    activeStepKey: activeStepKey.value,
    selectedToolByStep: selectedToolByStep.value,
    stepFormDrafts: stepFormDrafts.value,
    taskByStep: taskByStep.value,
    stepStateByKey: stepStateByKey.value,
    artifacts: artifacts.value,
    invalidArtifactIds: invalidArtifactIds.value,
    lastUpdatedAt: lastUpdatedAt.value,
    ownerUserId: ownerUserId.value
  }))

  function touchSession() {
    lastUpdatedAt.value = nowIsoString()
  }

  function setStepState(stepKey: WorkflowStepKey, nextState: Partial<WorkflowStepRecord>) {
    stepStateByKey.value = {
      ...stepStateByKey.value,
      [stepKey]: {
        ...stepStateByKey.value[stepKey],
        ...nextState,
        updatedAt: nowIsoString()
      }
    }
  }

  function refreshStepReadiness(stepKey: WorkflowStepKey) {
    const currentState = stepStateByKey.value[stepKey]

    if (
      currentState?.status === 'running' ||
      currentState?.status === 'completed' ||
      currentState?.status === 'failed' ||
      currentState?.status === 'invalidated'
    ) {
      return
    }

    const nextStatus = computeStepReadinessStatus({
      stepKey,
      artifacts: artifacts.value,
      selectedToolSlug: selectedToolByStep.value[stepKey] as WorkflowBoundToolSlug | undefined,
      invalidArtifactIds: invalidArtifactIds.value
    })

    setStepState(stepKey, {
      status: nextStatus,
      toolSlug: selectedToolByStep.value[stepKey]
    })
  }

  function refreshAllStepReadiness() {
    for (const stepKey of AIDD_WORKFLOW_STEP_ORDER) {
      refreshStepReadiness(stepKey)
    }
  }

  function resetSession(nextOwnerUserId?: string) {
    const nextSession = createInitialWorkflowSession(nextOwnerUserId)

    sessionId.value = nextSession.sessionId
    activeStepKey.value = nextSession.activeStepKey
    selectedToolByStep.value = nextSession.selectedToolByStep
    stepFormDrafts.value = nextSession.stepFormDrafts
    taskByStep.value = nextSession.taskByStep
    stepStateByKey.value = nextSession.stepStateByKey
    artifacts.value = nextSession.artifacts
    invalidArtifactIds.value = nextSession.invalidArtifactIds
    lastUpdatedAt.value = nextSession.lastUpdatedAt
    ownerUserId.value = nextSession.ownerUserId
  }

  function setOwnerUserId(userId?: string) {
    ownerUserId.value = userId
    touchSession()
  }

  function setActiveStep(stepKey: WorkflowStepKey) {
    activeStepKey.value = stepKey
    touchSession()
  }

  function selectTool(stepKey: WorkflowStepKey, toolSlug: WorkflowBoundToolSlug) {
    selectedToolByStep.value = {
      ...selectedToolByStep.value,
      [stepKey]: toolSlug
    }
    refreshStepReadiness(stepKey)
    touchSession()
  }

  function setStepFormDraft(stepKey: WorkflowStepKey, draft: Record<string, unknown>) {
    stepFormDrafts.value = {
      ...stepFormDrafts.value,
      [stepKey]: draft
    }
    touchSession()
  }

  function recordTask(stepKey: WorkflowStepKey, taskInput: WorkflowTaskRef) {
    const task = toWorkflowTaskRef(taskInput)

    taskByStep.value = {
      ...taskByStep.value,
      [stepKey]: task
    }

    if (task.tool_slug) {
      selectedToolByStep.value = {
        ...selectedToolByStep.value,
        [stepKey]: task.tool_slug
      }
    }

    setStepState(
      stepKey,
      buildWorkflowStepRecordFromTask({
        stepKey,
        task,
        previousStepRecord: stepStateByKey.value[stepKey]
      })
    )
    touchSession()
  }

  function registerArtifacts(nextArtifacts: WorkflowArtifact[]) {
    const artifactMap = new Map(artifacts.value.map((artifact) => [artifact.id, artifact]))

    for (const artifact of nextArtifacts) {
      artifactMap.set(artifact.id, artifact)
    }

    artifacts.value = Array.from(artifactMap.values())
    invalidArtifactIds.value = invalidArtifactIds.value.filter(
      (artifactId) => !nextArtifacts.some((artifact) => artifact.id === artifactId)
    )
    refreshAllStepReadiness()
    touchSession()
  }

  function registerTaskArtifacts(stepKey: WorkflowStepKey, toolSlug: WorkflowBoundToolSlug, taskInput: WorkflowTaskRef) {
    const task = toWorkflowTaskRef(taskInput)
    const nextArtifacts = extractArtifactsFromTaskResult({
      stepKey,
      toolSlug,
      task
    })

    if (nextArtifacts.length > 0) {
      registerArtifacts(nextArtifacts)
    }

    return nextArtifacts
  }

  function invalidateArtifacts(artifactIds: Iterable<string>) {
    const nextInvalidArtifactIds = new Set(invalidArtifactIds.value)

    for (const artifactId of artifactIds) {
      nextInvalidArtifactIds.add(artifactId)
    }

    invalidArtifactIds.value = Array.from(nextInvalidArtifactIds)
    refreshAllStepReadiness()
    touchSession()
  }

  function invalidateDownstreamFrom(stepKey: WorkflowStepKey) {
    stepStateByKey.value = invalidateCompletedDownstreamSteps({
      fromStepKey: stepKey,
      stepStateByKey: stepStateByKey.value
    })

    const currentIndex = AIDD_WORKFLOW_STEP_ORDER.indexOf(stepKey)
    const downstreamSteps = new Set(AIDD_WORKFLOW_STEP_ORDER.slice(currentIndex + 1))

    invalidateArtifacts(
      artifacts.value
        .filter((artifact) => downstreamSteps.has(artifact.stepKey))
        .map((artifact) => artifact.id)
    )
  }

  return {
    sessionId,
    activeStepKey,
    selectedToolByStep,
    stepFormDrafts,
    taskByStep,
    stepStateByKey,
    artifacts,
    invalidArtifactIds,
    lastUpdatedAt,
    ownerUserId,
    session,
    resetSession,
    setOwnerUserId,
    setActiveStep,
    selectTool,
    setStepFormDraft,
    recordTask,
    registerArtifacts,
    registerTaskArtifacts,
    invalidateArtifacts,
    invalidateDownstreamFrom,
    refreshStepReadiness,
    refreshAllStepReadiness
  }
}, {
  persist: {
    pick: [
      'sessionId',
      'activeStepKey',
      'selectedToolByStep',
      'stepFormDrafts',
      'taskByStep',
      'stepStateByKey',
      'artifacts',
      'invalidArtifactIds',
      'lastUpdatedAt',
      'ownerUserId'
    ]
  }
})
