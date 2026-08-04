import { readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const workflowDir = dirname(fileURLToPath(import.meta.url))

function readWorkflowFile(filename: string): string {
  return readFileSync(resolve(workflowDir, filename), 'utf8')
}

function readSrcFile(pathFromWorkflowDir: string): string {
  return readFileSync(resolve(workflowDir, pathFromWorkflowDir), 'utf8')
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

  it('uses canvas preset naming in workflow UI modules', () => {
    const componentFiles = readdirSync(resolve(workflowDir, '../components/workflow'))
    const viewSource = readSrcFile('../views/workflow/index.vue')
    const composableSource = readSrcFile('../composables/useWorkflowCanvas.ts')
    const zhLocaleSource = readSrcFile('../locales/zh-CN/index.ts')
    const enLocaleSource = readSrcFile('../locales/en-US/index.ts')

    expect(componentFiles).toContain('WorkflowCanvasBoard.vue')
    expect(componentFiles).not.toContain('WorkflowTemplateCanvas.vue')
    expect(componentFiles).not.toContain('WorkflowTemplateToolbar.vue')

    expect(viewSource).toContain('WorkflowCanvasBoard')
    expect(viewSource).not.toContain('WorkflowTemplateCanvas')
    expect(viewSource).not.toContain('workflow-template')

    expect(composableSource).toContain('activeCanvasPreset')
    expect(composableSource).toContain('editableCanvasPreset')
    expect(composableSource).toContain('canvasPresetOptions')
    expect(composableSource).toContain('handleCanvasPresetChange')
    expect(composableSource).not.toContain('activeTemplate')
    expect(composableSource).not.toContain('editableTemplate')
    expect(composableSource).not.toContain('templateOptions')
    expect(composableSource).not.toContain('handleTemplateChange')

    expect(zhLocaleSource).toContain('canvasPresets:')
    expect(enLocaleSource).toContain('canvasPresets:')
    expect(zhLocaleSource).not.toContain('templates:')
    expect(enLocaleSource).not.toContain('templates:')
  })
})
