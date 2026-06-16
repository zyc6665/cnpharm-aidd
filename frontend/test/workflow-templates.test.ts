import test from 'node:test'
import assert from 'node:assert/strict'

import {
  AIDD_WORKFLOW_TEMPLATE,
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
  assert.equal(getWorkflowTemplateById('missing-template'), null)
})
