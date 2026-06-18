import test from 'node:test'
import assert from 'node:assert/strict'

import { suggestWorkflowEdgesForNode } from '../src/workflow/template-artifacts.ts'
import type { WorkflowTemplate } from '../src/workflow/template-types.ts'

const template: WorkflowTemplate = {
  id: 'aidd-template',
  kind: 'aidd',
  nameKey: 'workflow.template',
  nodes: [
    {
      id: 'protein-input',
      type: 'input',
      titleKey: 'Protein input',
      position: { x: 0, y: 0 },
      producedOutputTypes: ['protein_structure']
    },
    {
      id: 'generation',
      type: 'tool',
      titleKey: 'Molecule generation',
      position: { x: 200, y: 0 },
      producedOutputTypes: ['generated_ligand']
    },
    {
      id: 'docking',
      type: 'tool',
      titleKey: 'Docking',
      position: { x: 400, y: 0 },
      requiredInputTypes: ['protein_structure', 'generated_ligand']
    }
  ],
  edges: [
    {
      id: 'edge-generation-docking',
      source: 'generation',
      target: 'docking',
      artifactType: 'generated_ligand'
    }
  ]
}

test('suggestWorkflowEdgesForNode suggests missing compatible upstream edges', () => {
  const suggestions = suggestWorkflowEdgesForNode({
    template,
    nodeId: 'docking'
  })

  assert.equal(suggestions.length, 1)
  assert.equal(suggestions[0]?.sourceNodeId, 'protein-input')
  assert.equal(suggestions[0]?.targetNodeId, 'docking')
  assert.equal(suggestions[0]?.semanticType, 'protein_structure')
})

test('suggestWorkflowEdgesForNode does not duplicate existing semantic edges', () => {
  const suggestions = suggestWorkflowEdgesForNode({
    template,
    nodeId: 'generation'
  })

  assert.deepEqual(suggestions, [])
})
