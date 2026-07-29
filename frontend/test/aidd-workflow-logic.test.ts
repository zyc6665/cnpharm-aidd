import { test } from 'vitest'
import assert from 'node:assert/strict'

import type { ToolOptionSummary } from '../src/types/models.d.ts'
import type {
  WorkflowArtifact,
  WorkflowArtifactSemanticType,
  WorkflowStepKey,
  WorkflowStepRecord,
  WorkflowStepStateMap,
  WorkflowStepStatus,
  WorkflowTaskRef
} from '../src/workflow/artifact-types.ts'
import type { WorkflowBoundToolSlug } from '../src/workflow/tool-bindings.ts'

type WorkflowReadinessStatus = Extract<
  WorkflowStepStatus,
  'idle' | 'ready' | 'needs_tool_selection'
>

type WorkflowRestoreSelectionStatus = Extract<WorkflowStepStatus, 'idle' | 'needs_tool_selection'>

type SelectLatestValidArtifactBySemanticType = (input: {
  artifacts: WorkflowArtifact[]
  semanticType: WorkflowArtifactSemanticType
  invalidArtifactIds?: Iterable<string>
}) => WorkflowArtifact | null

type ComputeStepReadinessStatus = (input: {
  stepKey: WorkflowStepKey
  artifacts: WorkflowArtifact[]
  selectedToolSlug?: WorkflowBoundToolSlug | null
  invalidArtifactIds?: Iterable<string>
}) => WorkflowReadinessStatus

type InvalidateCompletedDownstreamSteps = (input: {
  fromStepKey: WorkflowStepKey
  stepStateByKey: WorkflowStepStateMap
}) => WorkflowStepStateMap

type ResolveToolSelectionStatusOnRestore = (input: {
  persistedToolSlug?: WorkflowBoundToolSlug | null
  availableToolSlugs: readonly WorkflowBoundToolSlug[]
}) => WorkflowRestoreSelectionStatus

type WorkflowStepToolOption = {
  slug: WorkflowBoundToolSlug
  availability: 'available' | 'missing'
  isRecommended: boolean
  tool?: ToolOptionSummary
}

type WorkflowStepToolViewModel = {
  stepKey: WorkflowStepKey
  tools: WorkflowStepToolOption[]
  availableToolSlugs: WorkflowBoundToolSlug[]
  missingToolSlugs: WorkflowBoundToolSlug[]
  defaultSelectedToolSlug: WorkflowBoundToolSlug | null
}

type BuildWorkflowStepToolViewModel = (input: {
  stepKey: WorkflowStepKey
  tools: ToolOptionSummary[]
}) => WorkflowStepToolViewModel

type MapTaskStatusToWorkflowStepStatus = (taskStatus: WorkflowTaskRef['status']) => Extract<
  WorkflowStepStatus,
  'running' | 'completed' | 'failed'
>

type BuildWorkflowStepRecordFromTask = (input: {
  stepKey: WorkflowStepKey
  task: WorkflowTaskRef
  previousStepRecord?: WorkflowStepRecord
}) => WorkflowStepRecord

type ExtractArtifactsFromTaskResult = (input: {
  stepKey: WorkflowStepKey
  toolSlug: WorkflowBoundToolSlug
  task: WorkflowTaskRef
}) => WorkflowArtifact[]

type ResolveWorkflowInputSourcesForTool = (input: {
  toolSlug: WorkflowBoundToolSlug
  artifacts: WorkflowArtifact[]
  invalidArtifactIds?: Iterable<string>
}) => Array<{
  field: string
  semanticType: WorkflowArtifactSemanticType
  artifact: WorkflowArtifact | null
}>

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

function createToolOption(input: {
  id: string
  slug: WorkflowBoundToolSlug | 'unrelated-tool'
  name: string
  status?: ToolOptionSummary['status']
  is_public?: boolean
}): ToolOptionSummary {
  return {
    id: input.id,
    slug: input.slug,
    name: input.name,
    status: input.status ?? 'published',
    is_public: input.is_public ?? true
  }
}

function createWorkflowTaskRef(input: {
  id: string
  status: WorkflowTaskRef['status']
  toolId?: string
  toolSlug?: string
  progress?: number
  errorMessage?: string
  outputData?: unknown
  outputFiles?: WorkflowTaskRef['output_files']
  finishedAt?: string
}): WorkflowTaskRef {
  return {
    id: input.id,
    tool_id: input.toolId ?? 'tool-1',
    tool_slug: input.toolSlug,
    status: input.status,
    progress: input.progress ?? 0,
    error_message: input.errorMessage,
    output_data: input.outputData,
    output_files: input.outputFiles,
    finished_at: input.finishedAt,
    created_at: '2026-05-28T10:00:00Z'
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

test('上一步成功产出必需输入且已选工具时，下一步可执行状态应变为 ready', async () => {
  const computeStepReadinessStatus = await loadNamedFunction<ComputeStepReadinessStatus>(
    '../src/workflow/workflow-state.ts',
    'computeStepReadinessStatus'
  )

  const status = computeStepReadinessStatus({
    stepKey: 'moleculeGenerationOrVirtualScreening',
    selectedToolSlug: 'gcdm-pocket-generation',
    artifacts: [
      createArtifact({
        id: 'pocket-1',
        semanticType: 'pocket_structure',
        stepKey: 'pocketExploration',
        toolSlug: 'pocket-explorer',
        createdAt: '2026-05-28T09:00:00Z'
      })
    ]
  })

  assert.equal(status, 'ready')
})

test('当必需输入产物已失效时，步骤状态应保持 idle', async () => {
  const computeStepReadinessStatus = await loadNamedFunction<ComputeStepReadinessStatus>(
    '../src/workflow/workflow-state.ts',
    'computeStepReadinessStatus'
  )

  const status = computeStepReadinessStatus({
    stepKey: 'moleculeGenerationOrVirtualScreening',
    selectedToolSlug: 'gcdm-pocket-generation',
    invalidArtifactIds: ['pocket-1'],
    artifacts: [
      createArtifact({
        id: 'pocket-1',
        semanticType: 'pocket_structure',
        stepKey: 'pocketExploration',
        toolSlug: 'pocket-explorer',
        createdAt: '2026-05-28T09:00:00Z'
      })
    ]
  })

  assert.equal(status, 'idle')
})

test('上游步骤重跑后，只应将已完成的下游步骤标记为 invalidated', async () => {
  const invalidateCompletedDownstreamSteps =
    await loadNamedFunction<InvalidateCompletedDownstreamSteps>(
    '../src/workflow/workflow-state.ts',
      'invalidateCompletedDownstreamSteps'
    )

  const nextState = invalidateCompletedDownstreamSteps({
    fromStepKey: 'moleculeGenerationOrVirtualScreening',
    stepStateByKey: {
      pocketExploration: {
        status: 'completed',
        toolSlug: 'pocket-explorer'
      },
      moleculeGenerationOrVirtualScreening: {
        status: 'completed',
        toolSlug: 'gcdm-pocket-generation'
      },
      molecularDockingAndAffinityPrediction: {
        status: 'completed',
        toolSlug: 'molecular-docking'
      },
      propertyPrediction: {
        status: 'ready',
        toolSlug: 'molp-pc-property-prediction'
      },
      leadOptimization: {
        status: 'failed',
        toolSlug: 'lead-optimizer',
        errorMessage: 'optimizer crashed'
      }
    }
  })

  assert.equal(nextState.pocketExploration?.status, 'completed')
  assert.equal(nextState.moleculeGenerationOrVirtualScreening?.status, 'completed')
  assert.equal(nextState.molecularDockingAndAffinityPrediction?.status, 'invalidated')
  assert.equal(nextState.propertyPrediction?.status, 'ready')
  assert.equal(nextState.leadOptimization?.status, 'failed')
  assert.equal(nextState.leadOptimization?.errorMessage, 'optimizer crashed')
})

test('恢复步骤时若原工具已不可用，工具选择状态应进入 needs_tool_selection', async () => {
  const resolveToolSelectionStatusOnRestore =
    await loadNamedFunction<ResolveToolSelectionStatusOnRestore>(
    '../src/workflow/workflow-state.ts',
      'resolveToolSelectionStatusOnRestore'
    )

  const restoredStatus = resolveToolSelectionStatusOnRestore({
    persistedToolSlug: 'targetdiff-service',
    availableToolSlugs: ['gcdm-pocket-generation']
  })

  assert.equal(restoredStatus, 'needs_tool_selection')
})

test('步骤工具视图模型只应保留配置命中的工具并标记缺失项', async () => {
  const buildWorkflowStepToolViewModel = await loadNamedFunction<BuildWorkflowStepToolViewModel>(
    '../src/workflow/step-tools.ts',
    'buildWorkflowStepToolViewModel'
  )

  const viewModel = buildWorkflowStepToolViewModel({
    stepKey: 'moleculeGenerationOrVirtualScreening',
    tools: [
      createToolOption({
        id: 'tool-1',
        slug: 'gcdm-pocket-generation',
        name: 'GCDM Pocket Generation'
      }),
      createToolOption({
        id: 'tool-2',
        slug: 'unrelated-tool',
        name: 'Unrelated Tool'
      })
    ]
  })

  assert.deepEqual(
    viewModel.tools.map((tool) => tool.slug),
    ['gcdm-pocket-generation', 'targetdiff-service']
  )
  assert.deepEqual(viewModel.availableToolSlugs, ['gcdm-pocket-generation'])
  assert.deepEqual(viewModel.missingToolSlugs, ['targetdiff-service'])
  assert.equal(viewModel.tools[1]?.availability, 'missing')
})

test('推荐工具可用时应作为默认选中项，否则回退到首个可用工具', async () => {
  const buildWorkflowStepToolViewModel = await loadNamedFunction<BuildWorkflowStepToolViewModel>(
    '../src/workflow/step-tools.ts',
    'buildWorkflowStepToolViewModel'
  )

  const recommendedViewModel = buildWorkflowStepToolViewModel({
    stepKey: 'moleculeGenerationOrVirtualScreening',
    tools: [
      createToolOption({
        id: 'tool-1',
        slug: 'targetdiff-service',
        name: 'TargetDiff'
      }),
      createToolOption({
        id: 'tool-2',
        slug: 'gcdm-pocket-generation',
        name: 'GCDM Pocket Generation'
      })
    ]
  })

  assert.equal(recommendedViewModel.defaultSelectedToolSlug, 'gcdm-pocket-generation')

  const fallbackViewModel = buildWorkflowStepToolViewModel({
    stepKey: 'moleculeGenerationOrVirtualScreening',
    tools: [
      createToolOption({
        id: 'tool-2',
        slug: 'targetdiff-service',
        name: 'TargetDiff'
      })
    ]
  })

  assert.equal(fallbackViewModel.defaultSelectedToolSlug, 'targetdiff-service')
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

test('提交任务、任务成功和任务失败时应得到对应的步骤记录状态', async () => {
  const buildWorkflowStepRecordFromTask =
    await loadNamedFunction<BuildWorkflowStepRecordFromTask>(
      '../src/workflow/task-state.ts',
      'buildWorkflowStepRecordFromTask'
    )

  const runningStepRecord = buildWorkflowStepRecordFromTask({
    stepKey: 'propertyPrediction',
    task: createWorkflowTaskRef({
      id: 'task-running',
      status: 'pending',
      toolSlug: 'molp-pc-property-prediction',
      progress: 10
    })
  })

  assert.equal(runningStepRecord.status, 'running')
  assert.equal(runningStepRecord.toolSlug, 'molp-pc-property-prediction')

  const completedStepRecord = buildWorkflowStepRecordFromTask({
    stepKey: 'propertyPrediction',
    previousStepRecord: runningStepRecord,
    task: createWorkflowTaskRef({
      id: 'task-success',
      status: 'success',
      toolSlug: 'molp-pc-property-prediction',
      progress: 100
    })
  })

  assert.equal(completedStepRecord.status, 'completed')

  const failedStepRecord = buildWorkflowStepRecordFromTask({
    stepKey: 'propertyPrediction',
    previousStepRecord: completedStepRecord,
    task: createWorkflowTaskRef({
      id: 'task-failure',
      status: 'failure',
      toolSlug: 'molp-pc-property-prediction',
      errorMessage: 'queue timeout'
    })
  })

  assert.equal(failedStepRecord.status, 'failed')
  assert.equal(failedStepRecord.errorMessage, 'queue timeout')
})

test('任务成功后应按工具绑定规则提取标准化产物', async () => {
  const extractArtifactsFromTaskResult =
    await loadNamedFunction<ExtractArtifactsFromTaskResult>(
      '../src/workflow/artifact-resolver.ts',
      'extractArtifactsFromTaskResult'
    )

  const artifacts = extractArtifactsFromTaskResult({
    stepKey: 'molecularDockingAndAffinityPrediction',
    toolSlug: 'molecular-docking',
    task: createWorkflowTaskRef({
      id: 'task-docking-success',
      status: 'success',
      toolSlug: 'molecular-docking',
      finishedAt: '2026-05-28T15:00:00Z',
      outputFiles: [
        {
          id: 'pose-file-1',
          original_name: 'candidate_pose_1.sdf',
          filename: 'candidate_pose_1.sdf',
          content_type: 'chemical/x-mdl-sdfile',
          url: '/api/v1/files/pose-file-1/download'
        }
      ],
      outputData: {
        outputs: {
          affinity_report: {
            score: -9.3
          }
        }
      }
    })
  })

  assert.deepEqual(
    artifacts.map((artifact) => artifact.semanticType),
    ['docking_pose', 'affinity_report']
  )
  assert.equal(artifacts[0]?.fileId, 'pose-file-1')
  assert.equal(artifacts[1]?.metadata?.value && typeof artifacts[1].metadata.value, 'object')
})

test('下游工具应解析出当前可自动带入的输入来源', async () => {
  const resolveWorkflowInputSourcesForTool =
    await loadNamedFunction<ResolveWorkflowInputSourcesForTool>(
      '../src/workflow/artifact-resolver.ts',
      'resolveWorkflowInputSourcesForTool'
    )

  const inputSources = resolveWorkflowInputSourcesForTool({
    toolSlug: 'molecular-docking',
    invalidArtifactIds: ['protein-old'],
    artifacts: [
      createArtifact({
        id: 'protein-old',
        semanticType: 'protein_structure',
        stepKey: 'pocketExploration',
        toolSlug: 'pocket-explorer',
        createdAt: '2026-05-28T09:00:00Z'
      }),
      createArtifact({
        id: 'protein-new',
        semanticType: 'protein_structure',
        stepKey: 'pocketExploration',
        toolSlug: 'pocket-explorer',
        createdAt: '2026-05-28T11:00:00Z'
      }),
      createArtifact({
        id: 'ligand-1',
        semanticType: 'generated_ligand',
        stepKey: 'moleculeGenerationOrVirtualScreening',
        toolSlug: 'gcdm-pocket-generation',
        createdAt: '2026-05-28T12:00:00Z'
      })
    ]
  })

  assert.equal(inputSources[0]?.field, 'receptor_file')
  assert.equal(inputSources[0]?.artifact?.id, 'protein-new')
  assert.equal(inputSources[1]?.field, 'ligand_file')
  assert.equal(inputSources[1]?.artifact?.id, 'ligand-1')
})

test('GCDM 应优先复用 protein_pocket_residues 而不是 pocket0 产物', async () => {
  const resolveWorkflowInputSourcesForTool =
    await loadNamedFunction<ResolveWorkflowInputSourcesForTool>(
      '../src/workflow/artifact-resolver.ts',
      'resolveWorkflowInputSourcesForTool'
    )

  const inputSources = resolveWorkflowInputSourcesForTool({
    toolSlug: 'gcdm-pocket-generation',
    artifacts: [
      createArtifact({
        id: 'pocket-grid',
        semanticType: 'pocket_structure',
        stepKey: 'pocketExploration',
        toolSlug: 'pocket-explorer',
        name: 'artifacts__lv_results__input__pocket0.pdb',
        createdAt: '2026-05-28T12:00:00Z'
      }),
      createArtifact({
        id: 'pocket-residues',
        semanticType: 'pocket_structure',
        stepKey: 'pocketExploration',
        toolSlug: 'pocket-explorer',
        name: 'artifacts__lv_results__input__protein_pocket_residues.pdb',
        createdAt: '2026-05-28T11:00:00Z'
      })
    ]
  })

  assert.equal(inputSources[0]?.field, 'input_files.pocket_pdb')
  assert.equal(inputSources[0]?.artifact?.id, 'pocket-residues')
})
