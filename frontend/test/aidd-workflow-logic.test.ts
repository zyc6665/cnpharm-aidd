import { test } from 'vitest'
import assert from 'node:assert/strict'

import type {
  WorkflowArtifact,
  WorkflowArtifactSemanticType,
  WorkflowStepKey,
} from '../src/workflow/artifact-types.ts'
import { selectLatestValidArtifactBySemanticType } from '../src/workflow/artifact-resolver.ts'
import { mapTaskStatusToWorkflowStepStatus } from '../src/workflow/task-state.ts'

function createArtifact(input: {
  id: string
  semanticType: WorkflowArtifactSemanticType
  stepKey: WorkflowStepKey
  toolSlug: string
  createdAt: string
  name?: string
}): WorkflowArtifact {
  return {
    id: input.id,
    semanticType: input.semanticType,
    name: input.name ?? `${input.semanticType}-${input.id}`,
    stepKey: input.stepKey,
    toolSlug: input.toolSlug,
    createdAt: input.createdAt
  }
}

test('应从多个候选产物中选出最新且仍然有效的语义结果', async () => {
  const selectedArtifact = selectLatestValidArtifactBySemanticType({
    semanticType: 'generated_ligand',
    invalidArtifactIds: ['ligand-newest-invalid'],
    artifacts: [
      createArtifact({
        id: 'ligand-old',
        semanticType: 'generated_ligand',
        stepKey: 'moleculeGenerationOrVirtualScreening',
        toolSlug: 'gcdm-pocket-generation',
        createdAt: '2026-05-28T10:00:00Z'
      }),
      createArtifact({
        id: 'ligand-latest-valid',
        semanticType: 'generated_ligand',
        stepKey: 'moleculeGenerationOrVirtualScreening',
        toolSlug: 'targetdiff-service',
        createdAt: '2026-05-28T12:00:00Z'
      }),
      createArtifact({
        id: 'ligand-newest-invalid',
        semanticType: 'generated_ligand',
        stepKey: 'moleculeGenerationOrVirtualScreening',
        toolSlug: 'gcdm-pocket-generation',
        createdAt: '2026-05-28T13:00:00Z'
      }),
      createArtifact({
        id: 'pose-unrelated',
        semanticType: 'docking_pose',
        stepKey: 'molecularDockingAndAffinityPrediction',
        toolSlug: 'molecular-docking',
        createdAt: '2026-05-28T14:00:00Z'
      })
    ]
  })

  assert.equal(selectedArtifact?.id, 'ligand-latest-valid')
})

test('任务状态应映射为 workflow 的 running / completed / failed', async () => {
  assert.equal(mapTaskStatusToWorkflowStepStatus('pending'), 'running')
  assert.equal(mapTaskStatusToWorkflowStepStatus('running'), 'running')
  assert.equal(mapTaskStatusToWorkflowStepStatus('success'), 'completed')
  assert.equal(mapTaskStatusToWorkflowStepStatus('failure'), 'failed')
  assert.equal(mapTaskStatusToWorkflowStepStatus('canceled'), 'failed')
})
