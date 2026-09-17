import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { formatWorkflowKey, resolveWorkflowLabel } from '../src/workflow/i18n-utils'

describe('workflow i18n utils', () => {
  it('格式化未翻译的工作流 key', () => {
    expect(formatWorkflowKey('workflow.step.moleculeGeneration')).toBe('molecule Generation')
    expect(formatWorkflowKey('workflow.step.pocket_prediction')).toBe('pocket prediction')
  })

  it('优先返回已有翻译', () => {
    expect(resolveWorkflowLabel('workflow.step.input', () => '输入节点', () => true)).toBe('输入节点')
    expect(resolveWorkflowLabel('workflow.step.unknownKey', key => key, () => false)).toBe('unknown Key')
  })
})

it('workflow canvas reuses shared i18n label helpers', () => {
  const source = readFileSync(resolve('src/composables/useWorkflowCanvas.ts'), 'utf8')
  const boardSource = readFileSync(resolve('src/components/workflow/WorkflowCanvasBoard.vue'), 'utf8')

  expect(source.includes("import { resolveWorkflowLabel } from '@/workflow/i18n-utils'")).toBe(true)
  expect(source.includes('workflow.canvasNode.titleFallback')).toBe(true)
  expect(boardSource.includes('workflow.canvasNode.titleFallback')).toBe(true)
  expect(source.includes('function resolveLabel')).toBe(false)
  expect(source.includes("replace(/[-_]/g, ' ')")).toBe(false)
})
