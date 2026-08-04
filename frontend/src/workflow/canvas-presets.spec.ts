import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const workflowDir = dirname(fileURLToPath(import.meta.url))

function readWorkflowFile(filename: string): string {
  return readFileSync(resolve(workflowDir, filename), 'utf8')
}

describe('workflow canvas preset naming', () => {
  it('uses canvas preset names instead of the removed workflow template domain', () => {
    const typeSource = readWorkflowFile('template-types.ts')
    const presetSource = readWorkflowFile('templates.ts')

    expect(typeSource).toContain('export type WorkflowCanvasPresetKind')
    expect(typeSource).toContain('export interface WorkflowCanvasPreset')
    expect(typeSource).not.toContain('WorkflowTemplate')

    expect(presetSource).toContain('WORKFLOW_CANVAS_PRESETS')
    expect(presetSource).toContain('FREE_WORKFLOW_CANVAS_PRESET')
    expect(presetSource).toContain('getWorkflowCanvasPresetById')
    expect(presetSource).not.toContain('WORKFLOW_TEMPLATES')
    expect(presetSource).not.toContain('FREE_WORKFLOW_TEMPLATE')
    expect(presetSource).not.toContain('getWorkflowTemplateById')
  })
})
