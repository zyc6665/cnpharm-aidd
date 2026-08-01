import { describe, expect, it } from 'vitest'
import {
  extractWorkflowInputRequirementDetails,
  extractWorkflowInputRequirements
} from './workflow-definitions'

describe('workflow input requirements', () => {
  it('extracts standard artifact workflow inputs from artifact slots', () => {
    const requirements = extractWorkflowInputRequirements({
      nodes: [
        {
          id: 'pocket_prediction',
          kind: 'tool',
          type: 'tool',
          semantic_inputs: {},
          artifact_inputs: {
            protein: 'workflow_input:protein_structure@1'
          }
        }
      ],
      edges: []
    })

    expect(requirements).toEqual(['protein_structure@1'])
  })

  it('preserves artifact input slot names for run input display', () => {
    const requirements = extractWorkflowInputRequirementDetails({
      nodes: [
        {
          id: 'pocket_prediction',
          kind: 'tool',
          type: 'tool',
          artifact_inputs: {
            protein: 'workflow_input:protein_structure@1'
          }
        }
      ],
      edges: []
    })

    expect(requirements).toEqual([
      {
        key: 'protein_structure@1',
        semanticType: 'protein_structure@1',
        slotName: 'protein',
        label: 'protein: protein_structure@1'
      }
    ])
  })

  it('deduplicates legacy semantic inputs and standard artifact inputs', () => {
    const requirements = extractWorkflowInputRequirements({
      nodes: [
        {
          id: 'legacy_pocket_prediction',
          kind: 'tool',
          type: 'tool',
          semantic_inputs: {
            protein_pdb: 'workflow_input:protein_structure@1'
          }
        },
        {
          id: 'standard_pocket_prediction',
          kind: 'tool',
          type: 'tool',
          artifact_inputs: {
            protein: 'workflow_input:protein_structure@1'
          }
        }
      ],
      edges: []
    })

    expect(requirements).toEqual(['protein_structure@1'])
  })
})
