import { describe, expect, it } from 'vitest'
import type { Tool } from '@/types/models'
import { resolveToolRunInputSurface } from './tool-run-input-surface'

function makeTool(config: Record<string, unknown>): Tool {
  return {
    id: 'tool-1',
    name: 'Demo Tool',
    slug: 'demo-tool',
    description: 'Demo',
    category: 'AIDD',
    tags: [],
    status: 'published',
    usage_count: 0,
    view_count: 0,
    favorite_count: 0,
    gpu_required: false,
    created_at: '2026-09-12T00:00:00Z',
    current_version: {
      id: 'version-1',
      tool_id: 'tool-1',
      version: '1.0.0',
      is_active: true,
      deprecated: false,
      config,
    },
  }
}

const manifest = {
  api_version: 'aidd.sciminer/tool-package',
  artifacts: {
    inputs: [{ name: 'protein', type: 'protein_structure@1', required: true }],
    outputs: [],
  },
  parameters_schema: {
    type: 'object',
    properties: {
      model_choice: { type: 'string', title: 'Model weight', default: 'auto' },
    },
  },
}

describe('tool run input surface', () => {
  it('uses concrete input_schema fields when they cover all standard inputs', () => {
    const surface = resolveToolRunInputSurface(makeTool({
      type: 'ssh_job',
      tool_package_manifest: manifest,
      input_schema: {
        type: 'object',
        required: ['protein_pdb'],
        properties: {
          protein_pdb: { type: 'string', format: 'file', title: 'Protein PDB' },
          model_choice: { type: 'string', title: 'Model weight', default: 'auto' },
          device: { type: 'string', title: 'Device', default: 'auto' },
        },
      },
    }))

    expect(surface.showStandardArtifactInputs).toBe(false)
    expect(surface.usesConcreteStandardInputFields).toBe(true)
    expect(surface.standardInputFileFieldBindings).toEqual({ protein: 'protein_pdb' })
    expect(Object.keys(surface.flattenedSchema?.properties ?? {})).toEqual([
      'protein_pdb',
      'model_choice',
      'device',
    ])
  })

  it('keeps the standard artifact input block when concrete fields are incomplete', () => {
    const surface = resolveToolRunInputSurface(makeTool({
      type: 'ssh_job',
      tool_package_manifest: manifest,
      input_schema: {
        type: 'object',
        properties: {
          model_choice: { type: 'string', title: 'Model weight', default: 'auto' },
        },
      },
    }))

    expect(surface.showStandardArtifactInputs).toBe(true)
    expect(surface.usesConcreteStandardInputFields).toBe(false)
    expect(surface.standardInputFileFieldBindings).toEqual({})
    expect(Object.keys(surface.flattenedSchema?.properties ?? {})).toEqual(['model_choice'])
  })

  it('falls back to the legacy input schema when the contract schema is empty', () => {
    const tool = makeTool({
      type: 'ssh_job',
      input_schema: {
        type: 'object',
        properties: {
          model_choice: { type: 'string', default: 'auto' },
        },
      },
    })
    tool.contract = {
      executor: { type: 'ssh_job' },
      schema: { input: { type: 'object', properties: {} } },
    } as NonNullable<Tool['contract']>

    const surface = resolveToolRunInputSurface(tool)

    expect(Object.keys(surface.flattenedSchema?.properties ?? {})).toEqual(['model_choice'])
  })

  it('supports explicit standard input declarations on arbitrary file fields', () => {
    const surface = resolveToolRunInputSurface(makeTool({
      type: 'ssh_job',
      tool_package_manifest: manifest,
      input_schema: {
        type: 'object',
        required: ['uploaded_structure'],
        properties: {
          uploaded_structure: {
            type: 'string',
            format: 'file',
            title: 'Uploaded Structure',
            'x-standard-input': 'protein',
          },
        },
      },
    }))

    expect(surface.showStandardArtifactInputs).toBe(false)
    expect(surface.standardInputFileFieldBindings).toEqual({ protein: 'uploaded_structure' })
  })
})
