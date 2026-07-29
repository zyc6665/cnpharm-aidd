import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const source = readFileSync(resolve('src/stores/workflow.ts'), 'utf8')

test('workflow store includes template canvas session fields', () => {
  for (const field of [
    'templateId',
    'activeNodeId',
    'selectedToolByNode',
    'nodeFormDrafts',
    'taskByNode',
    'artifactBindingsByNode'
  ]) {
    assert.equal(source.includes(field), true, `missing ${field}`)
  }
})

test('workflow store exposes template canvas actions', () => {
  for (const action of [
    'setTemplate',
    'setActiveNode',
    'selectNodeTool',
    'setNodeFormDraft',
    'recordNodeTask',
    'setNodeArtifactBinding'
  ]) {
    assert.equal(source.includes(action), true, `missing ${action}`)
  }
})
