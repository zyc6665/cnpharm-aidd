import { readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { WORKFLOW_CANVAS_PRESETS } from './canvas-presets'

const workflowDir = dirname(fileURLToPath(import.meta.url))

function readWorkflowFile(filename: string): string {
  return readFileSync(resolve(workflowDir, filename), 'utf8')
}

/**
 * 直接读后端两处来源：
 * - `platform_tool_seeding.py` 的 `REQUIRED_TOOL_SLUGS`：部署时一定会被 seed 的模型工具；
 * - `capabilities.py` 里 `builtin-*` 的内置工具。
 * 画布预置里出现的每个 slug 都必须落在这两个集合里，否则用户点「使用该模板」
 * 会得到一个「未找到工具」的空节点——这类问题在类型层面完全看不出来。
 */
function readDeployedToolSlugs(): Set<string> {
  const root = resolve(process.cwd(), '..', 'backend', 'app')
  const seeding = readFileSync(resolve(root, 'services', 'platform_tool_seeding.py'), 'utf8')
  const block = /REQUIRED_TOOL_SLUGS[^=]*=\s*\(([\s\S]*?)\)/.exec(seeding)?.[1] ?? ''
  const slugs = new Set<string>()
  for (const match of block.matchAll(/"([a-z0-9-]+)"/g)) {
    slugs.add(match[1] ?? '')
  }
  const capabilities = readFileSync(resolve(root, 'tools', 'capabilities.py'), 'utf8')
  for (const match of capabilities.matchAll(/^\s{4}"(builtin-[a-z0-9-]+)":\s*ToolCapability\(/gm)) {
    slugs.add(match[1] ?? '')
  }
  return slugs
}

describe('workflow canvas presets reference deployed tools', () => {
  it('预置模板里的每个工具 slug 都是后端真实部署的', () => {
    const deployed = readDeployedToolSlugs()
    expect(deployed.size).toBeGreaterThan(5)

    const unknown: string[] = []
    for (const preset of WORKFLOW_CANVAS_PRESETS) {
      for (const node of preset.nodes) {
        for (const slug of node.toolSlugs ?? []) {
          if (!deployed.has(slug)) {
            unknown.push(`${preset.id}/${node.id}: ${slug}`)
          }
        }
      }
    }

    expect(unknown).toEqual([])
  })

  it('每个预置模板的边都指向模板内的节点', () => {
    const dangling: string[] = []
    for (const preset of WORKFLOW_CANVAS_PRESETS) {
      const ids = new Set(preset.nodes.map((node) => node.id))
      for (const edge of preset.edges) {
        if (!ids.has(edge.source) || !ids.has(edge.target)) {
          dangling.push(`${preset.id}: ${edge.id} (${edge.source} -> ${edge.target})`)
        }
      }
    }
    expect(dangling).toEqual([])
  })

  it('靶点制备与 MD/自由能模板已登记', () => {
    const ids = WORKFLOW_CANVAS_PRESETS.map((preset) => preset.id)
    expect(ids).toContain('target-preparation-template')
    expect(ids).toContain('md-free-energy-template')
  })
})

function readSrcFile(pathFromWorkflowDir: string): string {
  return readFileSync(resolve(workflowDir, pathFromWorkflowDir), 'utf8')
}

describe('workflow canvas preset naming', () => {
  it('uses canvas preset names instead of the removed workflow template domain', () => {
    const workflowFiles = readdirSync(workflowDir)
    const typeSource = readWorkflowFile('canvas-types.ts')
    const presetSource = readWorkflowFile('canvas-presets.ts')

    expect(workflowFiles).toContain('canvas-types.ts')
    expect(workflowFiles).toContain('canvas-presets.ts')
    expect(workflowFiles).toContain('canvas-artifacts.ts')
    expect(workflowFiles).toContain('canvas-runner.ts')
    expect(workflowFiles).toContain('canvas-state.ts')
    expect(workflowFiles).not.toContain('template-types.ts')
    expect(workflowFiles).not.toContain('templates.ts')
    expect(workflowFiles).not.toContain('template-artifacts.ts')
    expect(workflowFiles).not.toContain('template-runner.ts')
    expect(workflowFiles).not.toContain('template-state.ts')

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
