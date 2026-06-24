import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

function readSource(relativePath: string): string {
  return readFileSync(resolve(relativePath), 'utf8')
}

test('workflow palette and inspector empty states should guide the next action', () => {
  const paletteSource = readSource('src/components/workflow/WorkflowToolPalette.vue')
  const inspectorSource = readSource('src/components/workflow/WorkflowNodeInspector.vue')
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')

  for (const marker of [
    'workflow.palette.empty',
    'workflow.inspector.noOutputFiles',
    'workflow.inspector.noTaskResult'
  ]) {
    assert.equal(paletteSource.includes(marker) || inspectorSource.includes(marker), true, `missing ${marker}`)
  }

  for (const marker of [
    'noOutputFiles',
    'filterStage',
    'filterInput',
    'filterOutput',
    'filterExecutor',
    'viewTaskDetail',
    'rerunDownstream'
  ]) {
    assert.equal(zhSource.includes(marker), true, `missing zh ${marker}`)
    assert.equal(enSource.includes(marker), true, `missing en ${marker}`)
  }
})
