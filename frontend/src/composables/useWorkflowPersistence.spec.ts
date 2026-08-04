import { computed } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { mapWorkflowDefinitionToCanvasPayload, useWorkflowPersistence } from './useWorkflowPersistence'

describe('mapWorkflowDefinitionToCanvasPayload', () => {
  it('restores canvas semantic types from standard artifact slots', () => {
    const payload = mapWorkflowDefinitionToCanvasPayload({
      templateId: 'agent-draft',
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
      editableTemplate: computed(() => ({
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
