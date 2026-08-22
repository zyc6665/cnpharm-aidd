import { computed } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getTaskDetail } from '@/api/tasks'
import type { ToolContract } from '@/types/models'
import { mapWorkflowDefinitionToCanvasPayload, useWorkflowPersistence } from './useWorkflowPersistence'

vi.mock('@/api/tasks', () => ({
  getTaskDetail: vi.fn(),
}))

describe('mapWorkflowDefinitionToCanvasPayload', () => {
  function makeToolContract(): ToolContract {
    return {
      contract_version: '1.0',
      slug: 'lvpocket-pocket-prediction',
      name: 'LVpocket Pocket Prediction',
      status: 'published',
      executor: { type: 'ssh_job', timeout_sec: 3600 },
      schema: {
        input: { type: 'object', properties: {} },
        output: { type: 'object', properties: {} },
      },
      artifacts: {
        inputs: [{ name: 'protein', type: 'protein_structure@1', required: true }],
        outputs: [{ name: 'pocket', type: 'binding_pocket@1', cardinality: 'one', required: true }],
      },
      capability: {
        enabled: true,
        capability: 'pocket_prediction',
        stage: 'pocket_exploration',
        inputs: [],
        outputs: [],
        defaults: {},
        virtual: false,
      },
      validation: { status: 'valid', errors: [] },
    }
  }

  it('restores canvas semantic types from standard artifact slots', () => {
    const payload = mapWorkflowDefinitionToCanvasPayload({
      canvasPresetId: 'agent-draft',
      name: 'Agent Draft',
      definition: {
        nodes: [
          {
            id: 'pocket_prediction',
            kind: 'tool',
            tool_slug: 'lvpocket',
            artifact_input_slots: [
              { name: 'protein', type: 'protein_structure@1', required: true }
            ],
            artifact_outputs: [
              { name: 'pocket', type: 'binding_pocket@1', cardinality: 'one', required: true }
            ]
          }
        ],
        edges: []
      }
    })

    expect(payload.nodes[0]?.requiredInputTypes).toEqual(['protein_structure@1'])
    expect(payload.nodes[0]?.producedOutputTypes).toEqual(['binding_pocket@1'])
  })

  it('restores canvas semantic types from newly declared standard artifact refs', () => {
    const payload = mapWorkflowDefinitionToCanvasPayload({
      canvasPresetId: 'agent-draft',
      name: 'Agent Draft',
      definition: {
        nodes: [
          {
            id: 'cryoem-fit',
            kind: 'tool',
            tool_slug: 'cryoem-fit',
            artifact_input_slots: [{ name: 'map', type: 'cryoem_map@1', required: true }],
            artifact_outputs: [
              { name: 'fit_report', type: 'model_fit_report@1', cardinality: 'one', required: true }
            ]
          }
        ],
        edges: [
          {
            id: 'edge-map-fit',
            source: 'fetch-map',
            target: 'cryoem-fit',
            source_output: 'cryoem_map@1',
            target_input: 'cryoem_map@1'
          }
        ]
      }
    })

    expect(payload.nodes[0]?.requiredInputTypes).toEqual(['cryoem_map@1'])
    expect(payload.nodes[0]?.producedOutputTypes).toEqual(['model_fit_report@1'])
    expect(payload.edges[0]?.artifactType).toBe('cryoem_map@1')
  })

  it('hydrates stale saved tool nodes from current tool contracts', () => {
    const payload = mapWorkflowDefinitionToCanvasPayload({
      canvasPresetId: 'free-canvas',
      name: 'Saved Test Workflow',
      toolsBySlug: {
        'builtin-fetch-pdb': {
          contract: {
            ...makeToolContract(),
            slug: 'builtin-fetch-pdb',
            name: 'Fetch PDB Structure',
            artifacts: {
              inputs: [],
              outputs: [
                { name: 'protein', type: 'protein_structure@1', cardinality: 'one', required: true },
              ],
            },
          },
        },
        'lvpocket-pocket-prediction': {
          contract: makeToolContract(),
        },
      },
      definition: {
        nodes: [
          {
            id: 'fetch-pdb-node',
            kind: 'tool',
            tool_slug: 'builtin-fetch-pdb',
            artifact_input_slots: [],
            artifact_outputs: [],
          },
          {
            id: 'lvpocket-node',
            kind: 'tool',
            tool_slug: 'lvpocket-pocket-prediction',
            semantic_inputs: {
              'protein_structure@1': 'node:fetch-pdb-node:protein_structure@1',
            },
            artifact_input_slots: [],
            artifact_outputs: [],
          },
        ],
        edges: [
          {
            id: 'edge-fetch-to-pocket',
            source: 'fetch-pdb-node',
            target: 'lvpocket-node',
            source_output: 'protein_structure@1',
            target_input: 'protein_structure@1',
          },
        ],
      },
    })

    expect(payload.nodes[0]).toMatchObject({
      producedOutputTypes: ['protein_structure@1'],
      outputArtifactSlots: [
        { name: 'protein', type: 'protein_structure@1', cardinality: 'one', required: true },
      ],
    })
    expect(payload.nodes[1]).toMatchObject({
      requiredInputTypes: ['protein_structure@1'],
      producedOutputTypes: ['binding_pocket@1'],
      inputArtifactSlots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
      outputArtifactSlots: [
        { name: 'pocket', type: 'binding_pocket@1', cardinality: 'one', required: true },
      ],
    })
    expect(payload.edges[0]?.artifactType).toBe('protein_structure@1')
  })

  it('fills only missing artifact slot directions from current tool contracts', () => {
    const payload = mapWorkflowDefinitionToCanvasPayload({
      canvasPresetId: 'free-canvas',
      name: 'Partially Stale Workflow',
      toolsBySlug: {
        'lvpocket-pocket-prediction': {
          contract: makeToolContract(),
        },
      },
      definition: {
        nodes: [
          {
            id: 'lvpocket-node',
            kind: 'tool',
            tool_slug: 'lvpocket-pocket-prediction',
            artifact_input_slots: [
              { name: 'protein', type: 'protein_structure@1', required: true },
            ],
            artifact_outputs: [],
          },
        ],
        edges: [],
      },
    })

    expect(payload.nodes[0]).toMatchObject({
      requiredInputTypes: ['protein_structure@1'],
      producedOutputTypes: ['binding_pocket@1'],
      inputArtifactSlots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
      outputArtifactSlots: [
        { name: 'pocket', type: 'binding_pocket@1', cardinality: 'one', required: true },
      ],
    })
  })

  it('preserves artifact bindings from research board workflow drafts', () => {
    const payload = mapWorkflowDefinitionToCanvasPayload({
      canvasPresetId: 'research-board-draft',
      name: 'Board Draft',
      definition: {
        nodes: [
          {
            id: 'tool-pocket',
            kind: 'tool',
            tool_slug: 'pocket-tool',
            artifact_input_slots: [
              { name: 'protein', type: 'protein_structure@1', required: true }
            ],
            artifact_inputs: { protein: 'workflow_input:protein_structure@1' }
          }
        ],
        edges: [],
        artifact_bindings_by_node: {
          'tool-pocket': { protein: 'artifact-version-1' }
        }
      }
    })

    expect(payload.artifact_bindings_by_node).toEqual({
      'tool-pocket': { protein: 'artifact-version-1' }
    })
  })

  it('restores workflow control nodes without converting them to tools', () => {
    const payload = mapWorkflowDefinitionToCanvasPayload({
      canvasPresetId: 'control-flow-draft',
      name: 'Control Flow Draft',
      definition: {
        nodes: [
          {
            id: 'condition-score-gate',
            kind: 'condition',
            type: 'condition',
            expression: { op: '<=', left: 'node:docking:score', right: -8 },
            position: { x: 240, y: 120 },
          },
        ],
        edges: [],
      },
    })

    expect(payload.nodes[0]).toMatchObject({
      id: 'condition-score-gate',
      type: 'condition',
      expression: { op: '<=', left: 'node:docking:score', right: -8 },
      position: { x: 240, y: 120 },
    })
  })
})

describe('useWorkflowPersistence API', () => {
  beforeEach(() => {
    vi.mocked(getTaskDetail).mockReset()
  })

  function buildTaskResponse(taskId: string) {
    return {
      code: 200,
      message: 'ok',
      data: {
        id: taskId,
        name: 'Fetch PDB',
        tool_id: 'tool-fetch-pdb',
        tool_slug: 'builtin-fetch-pdb',
        status: 'success',
        progress: 100,
        created_at: '2026-08-21T00:00:00Z',
        updated_at: '2026-08-21T00:01:00Z',
        output_data: { ok: true },
        output_files: [],
      },
    } as never
  }

  function createPersistenceHarness(options: {
    workflow?: Record<string, unknown>
    runPage?: Record<string, unknown>
    run?: Record<string, unknown>
    taskByNode?: Record<string, Record<string, unknown>>
    projectId?: string
  } = {}) {
    const applyWorkflowDefinition = vi.fn()
    const loadWorkflowRuns = vi.fn().mockResolvedValue(options.runPage ?? { items: [] })
    const loadWorkflowRun = vi.fn().mockResolvedValue(options.run ?? {
      id: 'run-1',
      workflow_definition_id: 'workflow-1',
      status: 'success',
      node_states: {},
    })
    const recordNodeTask = vi.fn()
    const clearActiveWorkflowRun = vi.fn()
    const saveWorkflowDefinition = vi.fn(async (payload: Record<string, unknown>) => ({
      id: 'workflow-1',
      name: String(payload.name ?? 'Saved Workflow'),
      canvas_preset_id: payload.canvas_preset_id,
      nodes: payload.nodes,
      edges: payload.edges,
      selected_tool_by_node: payload.selected_tool_by_node,
      artifact_bindings_by_node: payload.artifact_bindings_by_node,
      task_bindings_by_node: payload.task_bindings_by_node,
      status: payload.status ?? 'draft',
    }))
    const loadWorkflowDefinition = vi.fn().mockResolvedValue(options.workflow ?? {
      id: 'workflow-1',
      name: 'Saved Workflow',
      canvas_preset_id: 'free-canvas',
      nodes: [{ id: 'fetch-pdb', kind: 'tool', tool_slug: 'builtin-fetch-pdb' }],
      edges: [],
      selected_tool_by_node: { 'fetch-pdb': 'builtin-fetch-pdb' },
      artifact_bindings_by_node: {},
      status: 'draft',
    })

    const persistence = useWorkflowPersistence({
      userStore: {
        authReady: true,
        isLoggedIn: true,
        user: { id: 'user-1' }
      },
      artifactsStore: {
        items: [],
        fetchArtifacts: vi.fn(),
      },
      workflowStore: {
        selectedToolByNode: {},
        artifactBindingsByNode: {},
        taskByNode: options.taskByNode ?? {},
        hasMoreWorkflowRuns: false,
        workflowRunsPagination: { page: 1, pageSize: 20 },
        isLoadingWorkflowRun: false,
        isSyncingWorkflowRun: false,
        activeWorkflowRun: null,
        activeWorkflowRunId: null,
        resetSession: vi.fn(),
        clearActiveWorkflowRun,
        applyWorkflowDefinition,
        runWorkflowDefinition: vi.fn(),
        loadWorkflowRuns,
        loadWorkflowRun,
        syncActiveWorkflowRun: vi.fn(),
        exportWorkflowNodes: vi.fn(() => []),
        exportWorkflowEdges: vi.fn(() => []),
        recordNodeTask,
      },
      workflowDefinitionsStore: {
        workflowDefinitions: [],
        currentWorkflowDefinition: null,
        clearCurrentWorkflowDefinition: vi.fn(),
        saveWorkflowDefinition,
        archiveWorkflowDefinition: vi.fn(),
        removeWorkflowDefinition: vi.fn(),
        loadWorkflowDefinition,
      },
      editableCanvasPreset: computed(() => ({
        id: 'free-canvas',
        nodes: [],
        edges: []
      })),
      projectId: computed(() => options.projectId ?? 'project-1'),
      workflowInputRequirements: computed(() => []),
      buildCurrentWorkflowDefinition: () => ({ nodes: [], edges: [] })
    } as never)

    return {
      persistence,
      applyWorkflowDefinition,
      clearActiveWorkflowRun,
      loadWorkflowRuns,
      loadWorkflowRun,
      recordNodeTask,
      saveWorkflowDefinition,
    }
  }

  it('保存工作流时应持久化节点任务快照', async () => {
    const { persistence, saveWorkflowDefinition } = createPersistenceHarness({
      taskByNode: {
        'fetch-pdb': {
          id: 'task-fetch-pdb',
          status: 'success',
        },
        'empty-task': {
          status: 'success',
        },
      },
    })

    await persistence.handleSaveWorkflow()

    expect(saveWorkflowDefinition).toHaveBeenCalledWith(expect.objectContaining({
      task_bindings_by_node: {
        'fetch-pdb': 'task-fetch-pdb',
      },
    }), undefined)
  })

  it('加载没有历史运行的已保存工作流时应从定义任务快照恢复节点任务', async () => {
    vi.mocked(getTaskDetail).mockResolvedValue(buildTaskResponse('task-fetch-pdb'))
    const { persistence, loadWorkflowRun, recordNodeTask } = createPersistenceHarness({
      workflow: {
        id: 'workflow-1',
        name: 'Saved Workflow',
        canvas_preset_id: 'free-canvas',
        nodes: [{ id: 'fetch-pdb', kind: 'tool', tool_slug: 'builtin-fetch-pdb' }],
        edges: [],
        selected_tool_by_node: { 'fetch-pdb': 'builtin-fetch-pdb' },
        artifact_bindings_by_node: {},
        task_bindings_by_node: { 'fetch-pdb': 'task-fetch-pdb' },
        status: 'draft',
      },
      runPage: { items: [] },
    })

    persistence.selectedSavedWorkflowId.value = 'workflow-1'

    await persistence.handleLoadWorkflow()

    expect(loadWorkflowRun).not.toHaveBeenCalled()
    expect(getTaskDetail).toHaveBeenCalledWith('task-fetch-pdb', { silent: true })
    expect(recordNodeTask).toHaveBeenCalledWith('fetch-pdb', expect.objectContaining({
      id: 'task-fetch-pdb',
      status: 'success',
    }))
  })

  it('加载旧版已保存工作流时应保留当前会话中同节点的任务绑定', async () => {
    vi.mocked(getTaskDetail).mockResolvedValue(buildTaskResponse('task-fetch-pdb'))
    const { persistence, recordNodeTask } = createPersistenceHarness({
      taskByNode: {
        'fetch-pdb': {
          id: 'task-fetch-pdb',
          status: 'success',
        },
        'other-node': {
          id: 'task-other',
          status: 'success',
        },
      },
      workflow: {
        id: 'workflow-1',
        name: 'Legacy Saved Workflow',
        canvas_preset_id: 'free-canvas',
        nodes: [{ id: 'fetch-pdb', kind: 'tool', tool_slug: 'builtin-fetch-pdb' }],
        edges: [],
        selected_tool_by_node: { 'fetch-pdb': 'builtin-fetch-pdb' },
        artifact_bindings_by_node: {},
        status: 'draft',
      },
      runPage: { items: [] },
    })

    persistence.selectedSavedWorkflowId.value = 'workflow-1'

    await persistence.handleLoadWorkflow()

    expect(getTaskDetail).toHaveBeenCalledTimes(1)
    expect(getTaskDetail).toHaveBeenCalledWith('task-fetch-pdb', { silent: true })
    expect(recordNodeTask).toHaveBeenCalledWith('fetch-pdb', expect.objectContaining({
      id: 'task-fetch-pdb',
      status: 'success',
    }))
    expect(recordNodeTask).not.toHaveBeenCalledWith('other-node', expect.anything())
  })

  it('加载已保存工作流时应恢复最新运行的节点任务', async () => {
    vi.mocked(getTaskDetail).mockResolvedValue(buildTaskResponse('task-fetch-pdb'))
    const { persistence, applyWorkflowDefinition, loadWorkflowRuns, loadWorkflowRun, recordNodeTask } =
      createPersistenceHarness({
        runPage: {
          items: [
            {
              id: 'run-1',
              workflow_definition_id: 'workflow-1',
              status: 'success',
            },
          ],
        },
        run: {
          id: 'run-1',
          workflow_definition_id: 'workflow-1',
          status: 'success',
          node_states: {
            'fetch-pdb': {
              status: 'success',
              tool_slug: 'builtin-fetch-pdb',
              task_id: 'task-fetch-pdb',
            },
          },
        },
      })

    persistence.selectedSavedWorkflowId.value = 'workflow-1'

    await persistence.handleLoadWorkflow()

    expect(applyWorkflowDefinition).toHaveBeenCalledWith(expect.objectContaining({
      canvas_preset_id: 'free-canvas',
      name: 'Saved Workflow',
      nodes: [expect.objectContaining({
        id: 'fetch-pdb',
        type: 'tool',
        recommendedToolSlug: 'builtin-fetch-pdb',
      })],
    }))
    expect(loadWorkflowRuns).toHaveBeenCalledWith(expect.objectContaining({
      project_id: 'project-1',
      workflow_definition_id: 'workflow-1',
      page: 1,
      page_size: 20,
    }))
    expect(loadWorkflowRun).toHaveBeenCalledWith('run-1')
    expect(recordNodeTask).toHaveBeenCalledWith('fetch-pdb', expect.objectContaining({
      id: 'task-fetch-pdb',
      status: 'success',
    }))
  })

  it('恢复运行任务时应将同一个任务详情回填到所有关联节点', async () => {
    vi.mocked(getTaskDetail).mockResolvedValue(buildTaskResponse('task-shared'))
    const { persistence, recordNodeTask } = createPersistenceHarness({
      runPage: { items: [{ id: 'run-shared', workflow_definition_id: 'workflow-1', status: 'success' }] },
      run: {
        id: 'run-shared',
        workflow_definition_id: 'workflow-1',
        status: 'success',
        node_states: {
          'node-a': { status: 'success', task_id: 'task-shared' },
          'node-b': { status: 'success', task_id: 'task-shared' },
        },
      },
    })

    persistence.selectedSavedWorkflowId.value = 'workflow-1'

    await persistence.handleLoadWorkflow()

    expect(getTaskDetail).toHaveBeenCalledTimes(1)
    expect(recordNodeTask).toHaveBeenCalledWith('node-a', expect.objectContaining({ id: 'task-shared' }))
    expect(recordNodeTask).toHaveBeenCalledWith('node-b', expect.objectContaining({ id: 'task-shared' }))
  })

  it('历史运行恢复失败时仍应保留已加载的工作流定义', async () => {
    const { persistence, applyWorkflowDefinition, loadWorkflowRuns } = createPersistenceHarness({
      runPage: { items: [] },
    })
    loadWorkflowRuns.mockRejectedValueOnce(new Error('run list failed'))

    persistence.selectedSavedWorkflowId.value = 'workflow-1'

    await persistence.handleLoadWorkflow()

    expect(applyWorkflowDefinition).toHaveBeenCalledWith(expect.objectContaining({
      canvas_preset_id: 'free-canvas',
      name: 'Saved Workflow',
      nodes: [expect.objectContaining({ id: 'fetch-pdb', type: 'tool' })],
    }))
  })

  it('exposes definition run handlers without the legacy workflow template facade', () => {
    const persistence = useWorkflowPersistence({
      userStore: {
        authReady: true,
        isLoggedIn: true,
        user: { id: 'user-1' }
      },
      artifactsStore: {
        items: []
      },
      workflowStore: {
        selectedToolByNode: {},
        artifactBindingsByNode: {},
        hasMoreWorkflowRuns: false,
        workflowRunsPagination: { page: 1, pageSize: 20 },
        isLoadingWorkflowRun: false,
        isSyncingWorkflowRun: false,
        activeWorkflowRun: null,
        activeWorkflowRunId: null,
        resetSession: vi.fn(),
        clearActiveWorkflowRun: vi.fn(),
        applyWorkflowDefinition: vi.fn(),
        runWorkflowDefinition: vi.fn(),
        loadWorkflowRuns: vi.fn(),
        loadWorkflowRun: vi.fn(),
        syncActiveWorkflowRun: vi.fn(),
        exportWorkflowNodes: vi.fn(() => []),
        exportWorkflowEdges: vi.fn(() => [])
      },
      workflowDefinitionsStore: {
        workflowDefinitions: [],
        currentWorkflowDefinition: null,
        clearCurrentWorkflowDefinition: vi.fn(),
        saveWorkflowDefinition: vi.fn(),
        archiveWorkflowDefinition: vi.fn(),
        removeWorkflowDefinition: vi.fn(),
        loadWorkflowDefinition: vi.fn()
      },
      editableCanvasPreset: computed(() => ({
        id: 'free-canvas',
        nodes: [],
        edges: []
      })),
      workflowInputRequirements: computed(() => []),
      buildCurrentWorkflowDefinition: () => ({ nodes: [], edges: [] })
    } as never)

    expect('handleRunWorkflowDefinition' in persistence).toBe(true)
    expect('handleRunWorkflowTemplate' in persistence).toBe(false)
    expect('workflowTemplateOptions' in persistence).toBe(false)
    expect('handleSaveWorkflowTemplate' in persistence).toBe(false)
    expect('restoreActiveWorkflowTemplate' in persistence).toBe(false)
  })
})
