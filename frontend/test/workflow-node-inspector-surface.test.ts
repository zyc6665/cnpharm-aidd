import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

test('workflow node inspector exposes node configuration sections', () => {
  const file = resolve('src/components/workflow/WorkflowNodeInspector.vue')
  assert.equal(existsSync(file), true)

  const source = readFileSync(file, 'utf8')
  for (const marker of [
    'workflow-node-inspector',
    'tool selector',
    'required input',
    'run current node',
    'task result',
    'no selected node'
  ]) {
    assert.equal(source.toLowerCase().includes(marker), true, `missing ${marker}`)
  }
})
