import { describe, expect, it } from 'vitest'
import type { TypedArtifact } from '@/types/artifacts'
import type { Tool, ToolContract } from '@/types/models'
import {
  buildStandardTaskRequestExtras,
  buildStandardInputBindings,
  filterCompatibleProjectArtifacts,
  resolveToolPackageParameterSchema,
  resolveToolStandardInputSlots,
} from './standard-artifact-inputs'

function makeToolContract(overrides: Partial<ToolContract> = {}): ToolContract {
  return {
    contract_version: '1.0',
    id: 'tool-1',
    slug: 'lvpocket-standard-pocket',
    name: 'LVpocket',
    description: null,
    status: 'published',
    is_public: true,
    version: { id: 'version-1', version: '1.0.0', is_active: true, deprecated: false },
    executor: { type: 'tool_package', timeout_sec: null },
    schema: {
      input: { type: 'object', properties: {} },
      output: { type: 'object', properties: {} },
    },
    capability: {
      enabled: true,
      capability: 'pocket_prediction',
      stage: 'pocket_prediction',
      inputs: [],
      outputs: [],
      defaults: {},
    },
    artifacts: {
      inputs: [{ name: 'protein', type: 'protein_structure@1', required: true }],
      outputs: [],
    },
    validation: { status: 'valid', errors: [] },
    ...overrides,
  }
}

function makeTool(overrides: Partial<Tool> = {}): Tool {
  return {
    id: 'tool-1',
    name: 'LVpocket',
    slug: 'lvpocket-standard-pocket',
    description: 'Pocket prediction',
    category: 'AIDD',
    tags: [],
    status: 'published',
    usage_count: 0,
    view_count: 0,
    favorite_count: 0,
    gpu_required: false,
    created_at: '2026-08-02T00:00:00Z',
    ...overrides,
  }
}

function makeArtifact(overrides: Partial<TypedArtifact> = {}): TypedArtifact {
  return {
    id: 'artifact-1',
    project_id: 'project-1',
    artifact_type: 'protein_structure@1',
    semantic_type: 'protein_structure@1',
    name: 'target.pdb',
    latest_version: {
      id: 'version-1',
      version: 1,
      filename: 'target.pdb',
      content_type: 'chemical/x-pdb',
      size_bytes: 123,
      sha256: 'abc',
      status: 'available',
      created_at: '2026-08-02T00:00:00Z',
    },
    created_at: '2026-08-02T00:00:00Z',
    updated_at: '2026-08-02T00:00:00Z',
    ...overrides,
  }
}

describe('standard artifact tool inputs', () => {
  it('resolves standard input slots from the tool contract first', () => {
    const tool = makeTool({ contract: makeToolContract() } as Partial<Tool>)

    expect(resolveToolStandardInputSlots(tool)).toEqual([
      {
        name: 'protein',
        type: 'protein_structure@1',
        required: true,
      },
    ])
  })

  it('falls back to the embedded Tool Package v2 manifest when detail lacks contract', () => {
    const tool = makeTool({
      current_version: {
        id: 'tool-version-1',
        tool_id: 'tool-1',
        version: '1.0.0',
        is_active: true,
        deprecated: false,
        config: {
          tool_package: {
            manifest: {
              api_version: 'aidd.sciminer/tool-package.v2',
              artifacts: {
                inputs: [
                  { name: 'protein', type: 'protein_structure@1', required: true },
                  { name: 'legacy', type: 'unknown_type', required: true },
                ],
              },
            },
          },
        },
      },
    })

    expect(resolveToolStandardInputSlots(tool)).toEqual([
      {
        name: 'protein',
        type: 'protein_structure@1',
        required: true,
      },
    ])
  })

  it('keeps newly declared standard artifact refs from embedded Tool Package v2 manifests', () => {
    const tool = makeTool({
      current_version: {
        id: 'tool-version-1',
        tool_id: 'tool-1',
        version: '1.0.0',
        is_active: true,
        deprecated: false,
        config: {
          tool_package: {
            manifest: {
              api_version: 'aidd.sciminer/tool-package.v2',
              artifacts: {
                inputs: [
                  { name: 'map', type: 'cryoem_map@1', required: true },
                  { name: 'invalid', type: 'unknown_type', required: true },
                ],
              },
            },
          },
        },
      },
    })

    expect(resolveToolStandardInputSlots(tool)).toEqual([
      {
        name: 'map',
        type: 'cryoem_map@1',
        required: true,
      },
    ])
  })

  it('keeps only compatible available project artifacts for a standard slot', () => {
    const slot = {
      name: 'protein',
      type: 'protein_structure@1',
      required: true,
    } as const
    const compatible = makeArtifact()
    const aliasCompatible = makeArtifact({
      id: 'artifact-2',
      semantic_type: 'protein_pdb',
      latest_version: { ...makeArtifact().latest_version, id: 'version-2' },
    })
    const incompatible = makeArtifact({
      id: 'artifact-3',
      semantic_type: 'binding_pocket@1',
      artifact_type: 'binding_pocket@1',
      latest_version: { ...makeArtifact().latest_version, id: 'version-3' },
    })
    const unavailable = makeArtifact({
      id: 'artifact-4',
      latest_version: { ...makeArtifact().latest_version, id: 'version-4', status: 'processing' },
    })

    expect(
      filterCompatibleProjectArtifacts(slot, [
        incompatible,
        unavailable,
        compatible,
        aliasCompatible,
      ]).map((artifact) => artifact.id)
    ).toEqual(['artifact-1', 'artifact-2'])
  })

  it('builds task input bindings from selected latest ArtifactVersions', () => {
    const bindings = buildStandardInputBindings({
      protein: makeArtifact({
        id: 'artifact-1',
        latest_version: { ...makeArtifact().latest_version, id: 'version-1' },
      }),
      pocket: undefined,
    })

    expect(bindings).toEqual({ protein: 'version-1' })
  })

  it('resolves v2 parameter schema from the embedded manifest instead of legacy input schema', () => {
    const tool = makeTool({
      current_version: {
        id: 'tool-version-1',
        tool_id: 'tool-1',
        version: '1.0.0',
        is_active: true,
        deprecated: false,
        config: {
          input_schema: {
            type: 'object',
            required: ['protein_file'],
            properties: {
              protein_file: { type: 'file', title: 'Legacy protein file' },
            },
          },
          tool_package: {
            manifest: {
              api_version: 'aidd.sciminer/tool-package.v2',
              parameters_schema: {
                type: 'object',
                properties: {
                  threshold: { type: 'number', title: 'Threshold', default: 0.5 },
                },
              },
              artifacts: {
                inputs: [{ name: 'protein', type: 'protein_structure@1', required: true }],
              },
            },
          },
        },
      },
    })

    expect(resolveToolPackageParameterSchema(tool)).toEqual({
      type: 'object',
      properties: {
        threshold: { type: 'number', title: 'Threshold', default: 0.5 },
      },
    })
  })

  it('adds project context and input bindings only when standard bindings are present', () => {
    expect(
      buildStandardTaskRequestExtras({
        projectId: 'project-1',
        inputBindings: { protein: 'version-1' },
      })
    ).toEqual({
      project_id: 'project-1',
      input_bindings: { protein: 'version-1' },
    })

    expect(
      buildStandardTaskRequestExtras({
        projectId: 'project-1',
        inputBindings: {},
      })
    ).toEqual({})
  })
})
