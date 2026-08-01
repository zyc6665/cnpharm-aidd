import { describe, expect, it } from 'vitest'
import { mapWorkflowDefinitionToCanvasPayload } from './useWorkflowPersistence'

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
