import { test } from 'vitest'
import assert from 'node:assert/strict'

import type {
  WorkflowArtifact,
  WorkflowArtifactSemanticType,
  WorkflowStepKey,
  WorkflowStepStatus,
  WorkflowTaskRef
} from '../src/workflow/artifact-types.ts'

type SelectLatestValidArtifactBySemanticType = (input: {
  artifacts: WorkflowArtifact[]
  semanticType: WorkflowArtifactSemanticType
  invalidArtifactIds?: Iterable<string>
}) => WorkflowArtifact | null

type MapTaskStatusToWorkflowStepStatus = (taskStatus: WorkflowTaskRef['status']) => Extract<
  WorkflowStepStatus,
  'running' | 'completed' | 'failed'
>

async function loadNamedFunction<T extends (...args: never[]) => unknown>(
  moduleRelativePath: string,
  exportName: string
): Promise<T> {
  try {
    const module = (await import(moduleRelativePath)) as Record<string, unknown>
    const exportedValue = module[exportName]

    assert.equal(
      typeof exportedValue,
      'function',
      `预期 ${moduleRelativePath} 导出函数 ${exportName}，但当前导出类型为 ${typeof exportedValue}`
    )

    return exportedValue as T
  } catch (error) {
    assert.fail(
      `预期 ${moduleRelativePath} 可加载且导出函数 ${exportName}，当前模块无法加载或导出缺失：${
        error instanceof Error ? error.message : String(error)
      }`
    )
  }
}

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
  const selectLatestValidArtifactBySemanticType =
    await loadNamedFunction<SelectLatestValidArtifactBySemanticType>(
      '../src/workflow/artifact-resolver.ts',
      'selectLatestValidArtifactBySemanticType'
    )

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
  const mapTaskStatusToWorkflowStepStatus =
    await loadNamedFunction<MapTaskStatusToWorkflowStepStatus>(
      '../src/workflow/task-state.ts',
      'mapTaskStatusToWorkflowStepStatus'
    )

  assert.equal(mapTaskStatusToWorkflowStepStatus('pending'), 'running')
  assert.equal(mapTaskStatusToWorkflowStepStatus('running'), 'running')
  assert.equal(mapTaskStatusToWorkflowStepStatus('success'), 'completed')
  assert.equal(mapTaskStatusToWorkflowStepStatus('failure'), 'failed')
  assert.equal(mapTaskStatusToWorkflowStepStatus('canceled'), 'failed')
})
