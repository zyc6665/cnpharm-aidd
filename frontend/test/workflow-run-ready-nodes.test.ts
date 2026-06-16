import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { resolveReadyToolNodeIds } from '../src/workflow/template-runner.ts'
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
      titleKey: 'ready',
      position: { x: 160, y: 0 },
      toolSlugs: ['tool-a']
    },
    {
      id: 'blocked-tool',
      type: 'tool',
      titleKey: 'blocked',
      position: { x: 320, y: 0 },
      toolSlugs: ['tool-b']
    }
  ],
  edges: []
}

test('resolveReadyToolNodeIds returns only tool nodes currently marked ready', () => {
  assert.deepEqual(
    resolveReadyToolNodeIds({
      template,
      nodeStatuses: {
        input: 'completed',
        'ready-tool': 'ready',
        'blocked-tool': 'idle'
      }
    }),
    ['ready-tool']
  )
})

test('workflow page exposes save, load and run-ready controls', () => {
  const source = readFileSync(resolve('src/views/workflow/index.vue'), 'utf8')

  for (const marker of [
    'handleSaveWorkflow',
    'handleLoadWorkflow',
    'handleRunReadyNodes',
    'resolveReadyToolNodeIds',
    'workflow-definition-bar'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }
})
