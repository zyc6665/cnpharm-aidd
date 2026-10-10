import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

function readSource(relativePath: string): string {
  return readFileSync(resolve(relativePath), 'utf8')
}

test('workflow palette and inspector empty states should guide the next action', () => {
  const paletteSource = readSource('src/components/workflow/WorkflowToolPalette.vue')
  const inspectorSource = readSource('src/components/workflow/WorkflowNodeInspector.vue')
  const resultSource = readSource('src/components/workflow/NodeResultPanel.vue')
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')

  for (const marker of [
    'workflow.palette.empty',
    'workflow.inspector.noOutputFiles',
    'workflow.inspector.noTaskResult'
  ]) {
    assert.equal(paletteSource.includes(marker) || inspectorSource.includes(marker) || resultSource.includes(marker), true, `missing ${marker}`)
  }

  for (const marker of [
    'noOutputFiles',
    'filterStage',
    'filterInput',
    'filterOutput',
    'viewTaskDetail',
    'runWorkflow'
  ]) {
    assert.equal(zhSource.includes(marker), true, `missing zh ${marker}`)
    assert.equal(enSource.includes(marker), true, `missing en ${marker}`)
  }
})

test('workflow canvas exposes keyboard movement and graph semantics', () => {
  const canvasSource = readSource('src/components/workflow/WorkflowCanvasBoard.vue')
  const nodeSource = readSource('src/components/workflow/WorkflowCanvasPanelNode.vue')

  for (const marker of ['role="img"', ':aria-label="t(\'workflow.canvas.edges\'']) {
    assert.equal(canvasSource.includes(marker), true, `canvas missing ${marker}`)
  }

  for (const marker of [':aria-grabbed="isDragging"', 'handleKeydown', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']) {
    assert.equal(nodeSource.includes(marker), true, `node missing ${marker}`)
  }
})
