import test from 'node:test'
import assert from 'node:assert/strict'

import { buildWorkflowPreflight } from '../src/workflow/preflight.ts'
import type { WorkflowTemplate } from '../src/workflow/template-types.ts'

const template: WorkflowTemplate = {
  id: 'aidd-template',
  kind: 'aidd',
  nameKey: 'workflow.template',
  nodes: [
    { id: 'input', type: 'input', titleKey: 'input', position: { x: 0, y: 0 } },
    {
      id: 'ready-tool',
      type: 'tool',
      titleKey: 'molecule.scoring',
      position: { x: 160, y: 0 },
      toolSlugs: ['score']
    },
    {
      id: 'missing-tool',
      type: 'tool',
      titleKey: 'docking',
      position: { x: 320, y: 0 },
      toolSlugs: ['dock-a', 'dock-b']
    },
    {
      id: 'waiting-upstream',
      type: 'tool',
      titleKey: 'ranking',
      position: { x: 480, y: 0 },
      requiredInputTypes: ['sdf']
    }
  ],
  edges: []
}

test('buildWorkflowPreflight reports runnable nodes and blocking issues', () => {
  const preflight = buildWorkflowPreflight({
    template,
    nodeStatuses: {
      input: 'completed',
      'ready-tool': 'ready',
      'missing-tool': 'needs_tool_selection',
      'waiting-upstream': 'idle'
    },
    readyNodeIds: ['ready-tool']
  })

  assert.equal(preflight.canRun, true)
  assert.equal(preflight.runnableCount, 1)
  assert.equal(preflight.blockedCount, 2)
  assert.equal(preflight.issues.length, 2)
  assert.equal(preflight.issues[0]?.type, 'missing_tool')
  assert.equal(preflight.issues[1]?.type, 'waiting_input')
})

test('buildWorkflowPreflight disables full run when no tool nodes are runnable', () => {
  const preflight = buildWorkflowPreflight({
    template,
    nodeStatuses: {
      input: 'completed',
      'ready-tool': 'failed',
      'missing-tool': 'needs_tool_selection',
      'waiting-upstream': 'idle'
    },
    readyNodeIds: []
  })

  assert.equal(preflight.canRun, false)
  assert.equal(preflight.failedCount, 1)
  assert.equal(preflight.issues.some(issue => issue.type === 'failed'), true)
  assert.equal(preflight.primaryMessage, '当前没有可运行节点')
})

test('buildWorkflowPreflight reports missing workflow input and invalid semantic edges', () => {
  const preflight = buildWorkflowPreflight({
    template: {
      ...template,
      nodes: [
        { id: 'input-protein', type: 'input', titleKey: 'workflow.nodes.inputProtein.title', position: { x: 0, y: 0 }, producedOutputTypes: ['protein_pdb'] },
        {
          id: 'tool-pocket',
          type: 'tool',
          titleKey: 'home.workflow.items.pocketExploration.title',
          position: { x: 160, y: 0 },
          requiredInputTypes: ['protein_pdb'],
          toolSlugs: ['pocket-explorer'],
          recommendedToolSlug: 'pocket-explorer'
        }
      ],
      edges: [
        { id: 'edge-a', source: 'input-protein', target: 'tool-pocket', artifactType: 'protein_pdb' },
        { id: 'edge-b', source: 'input-protein', target: 'tool-pocket', artifactType: 'generated_ligand' }
      ]
    },
    nodeStatuses: {
      'input-protein': 'completed',
      'tool-pocket': 'idle'
    },
    readyNodeIds: [],
    selectedWorkflowInputFiles: {},
    selectedToolByNode: {
      'tool-pocket': 'pocket-explorer'
    },
    toolsBySlug: {
      'pocket-explorer': {
        slug: 'pocket-explorer',
        contract: {
          contract_version: 'v1',
          slug: 'pocket-explorer',
          name: 'Pocket Explorer',
          status: 'published',
          executor: { type: 'python' },
          schema: {
            input: { type: 'object', properties: {} },
            output: { type: 'object', properties: {} }
          },
          capability: {
            enabled: true,
            inputs: [],
            outputs: [],
            defaults: {}
          },
          validation: {
            status: 'valid',
            errors: []
          }
        }
      }
    }
  })

  assert.equal(preflight.issues.some(issue => issue.type === 'missing_workflow_input'), true)
  assert.equal(preflight.issues.some(issue => issue.type === 'invalid_semantic_edge'), true)
  assert.equal(preflight.primaryMessage, '请先补齐工作流输入')
})
