import test from 'node:test'
import assert from 'node:assert/strict'

import {
  AIDD_WORKFLOW_TEMPLATE,
  GENERATION_TO_PROPERTY_TEMPLATE,
  POCKET_TO_GENERATION_TEMPLATE,
  PROTEIN_LIGAND_TO_DOCKING_TEMPLATE,
  PROTEIN_TO_POCKET_TEMPLATE,
  WORKFLOW_TEMPLATES,
  getWorkflowTemplateById
} from '../src/workflow/templates.ts'

test('AIDD workflow template defines a connected node graph', () => {
  assert.equal(AIDD_WORKFLOW_TEMPLATE.id, 'aidd-template')
  assert.equal(AIDD_WORKFLOW_TEMPLATE.nodes.length >= 7, true)

  const nodeTypes = new Set(AIDD_WORKFLOW_TEMPLATE.nodes.map(node => node.type))
  assert.equal(nodeTypes.has('input'), true)
  assert.equal(nodeTypes.has('tool'), true)
  assert.equal(nodeTypes.has('result'), true)

  const nodeIds = new Set(AIDD_WORKFLOW_TEMPLATE.nodes.map(node => node.id))
  for (const edge of AIDD_WORKFLOW_TEMPLATE.edges) {
    assert.equal(nodeIds.has(edge.source), true, `missing source node ${edge.source}`)
    assert.equal(nodeIds.has(edge.target), true, `missing target node ${edge.target}`)
  }

  assert.equal(AIDD_WORKFLOW_TEMPLATE.nodes.some(node => node.position.x > 0), true)
  assert.equal(AIDD_WORKFLOW_TEMPLATE.nodes.some(node => node.position.y > 0), true)
})

test('workflow templates can be resolved by id', () => {
  assert.equal(WORKFLOW_TEMPLATES.includes(AIDD_WORKFLOW_TEMPLATE), true)
  assert.equal(getWorkflowTemplateById('aidd-template'), AIDD_WORKFLOW_TEMPLATE)
  assert.equal(getWorkflowTemplateById('protein-pocket-template'), PROTEIN_TO_POCKET_TEMPLATE)
  assert.equal(getWorkflowTemplateById('pocket-generation-template'), POCKET_TO_GENERATION_TEMPLATE)
  assert.equal(getWorkflowTemplateById('protein-ligand-docking-template'), PROTEIN_LIGAND_TO_DOCKING_TEMPLATE)
  assert.equal(getWorkflowTemplateById('generation-property-template'), GENERATION_TO_PROPERTY_TEMPLATE)
  assert.equal(getWorkflowTemplateById('missing-template'), null)
})

test('workflow templates include stage-oriented researcher presets', () => {
  const templateIds = new Set(WORKFLOW_TEMPLATES.map((template) => template.id))

  for (const templateId of [
    'protein-pocket-template',
    'pocket-generation-template',
    'protein-ligand-docking-template',
    'generation-property-template'
  ]) {
    assert.equal(templateIds.has(templateId), true, `missing ${templateId}`)
  }
})
