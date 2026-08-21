import { computed } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { mapWorkflowDefinitionToCanvasPayload, useWorkflowPersistence } from './useWorkflowPersistence'

describe('mapWorkflowDefinitionToCanvasPayload', () => {
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
