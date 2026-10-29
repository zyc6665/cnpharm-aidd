import { describe, expect, it } from 'vitest'
import type { TypedArtifact } from '@/types/artifacts'
import type { ArtifactFile, Tool, ToolContract, ToolSchema } from '@/types/models'
import {
  buildStandardInputBindings,
  buildStandardInputBindingsFromFileFields,
  buildStandardInputUploadsFromFileFields,
  filterCompatibleProjectArtifacts,
  getStandardInputAccept,
  hasConcreteStandardInputUploadSelection,
  hasStandardInputFileFieldBindings,
  missingRequiredStandardInputSlots,
  resolveStandardInputFileFieldBindings,
  resolveStandardInputRunState,
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

function makeArtifactFile(overrides: Partial<ArtifactFile> = {}): ArtifactFile {
  return {
    id: 'file-1',
    filename: 'target.pdb',
    content_type: 'chemical/x-pdb',
    size_bytes: 123,
    source_type: 'task_output',
    download_url: '/api/v1/files/file-1/download',
    task_id: 'task-1',
    tool_id: 'tool-1',
    tool_name: 'LVpocket',
    tool_slug: 'lvpocket-standard-pocket',
    created_at: '2026-08-02T00:00:00Z',
    ...overrides,
  }
}

describe('standard artifact tool inputs', () => {
  it('detects whether concrete file field bindings are present', () => {
    expect(hasStandardInputFileFieldBindings({ protein: 'protein_pdb' })).toBe(true)
    expect(hasStandardInputFileFieldBindings({ protein: '' })).toBe(false)
    expect(hasStandardInputFileFieldBindings({})).toBe(false)
  })

  it('detects concrete standard input upload selections from file field state', () => {
    expect(hasConcreteStandardInputUploadSelection({
      slotName: 'protein',
      fileFieldBindings: { protein: 'protein_pdb' },
      fileList: { protein_pdb: [{ uid: 'upload-protein' }] },
      selectedArtifacts: {},
    })).toBe(true)
    expect(hasConcreteStandardInputUploadSelection({
      slotName: 'protein',
      fileFieldBindings: { protein: 'protein_pdb' },
      selectedArtifacts: { protein_pdb: makeArtifactFile({ id: 'file-1' }) },
    })).toBe(true)
    expect(hasConcreteStandardInputUploadSelection({
      slotName: 'protein',
      fileFieldBindings: { protein: 'protein_pdb' },
      selectedArtifacts: { protein_pdb: makeArtifactFile({ artifact_version_id: 'version-1' }) },
      fileList: { protein_pdb: [{ uid: 'upload-protein' }] },
    })).toBe(false)
    expect(hasConcreteStandardInputUploadSelection({
      slotName: 'ligand',
      fileFieldBindings: { protein: 'protein_pdb' },
      selectedArtifacts: {},
    })).toBe(false)
  })

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
              api_version: 'aidd.sciminer/tool-package',
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
              api_version: 'aidd.sciminer/tool-package',
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

  it('maps legacy protein file fields to standard input slots', () => {
    const flattenedSchema: ToolSchema = {
      type: 'object',
      required: ['protein_pdb'],
      properties: {
        protein_pdb: {
          type: 'file',
          title: 'Protein PDB',
          format: 'file',
        },
        model_choice: { type: 'string', title: 'Model weight' },
      },
    }

    expect(
      resolveStandardInputFileFieldBindings({
        slots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
        flattenedSchema,
      })
    ).toEqual({ protein: 'protein_pdb' })
  })

  it('does not bind standard input slots without a matching legacy file field', () => {
    const flattenedSchema: ToolSchema = {
      type: 'object',
      properties: {
        notes: { type: 'string', title: 'Notes' },
      },
    }

    expect(
      resolveStandardInputFileFieldBindings({
        slots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
        flattenedSchema,
      })
    ).toEqual({})
  })

  it('projects selected legacy standard artifact files into input bindings', () => {
    expect(
      buildStandardInputBindingsFromFileFields({
        slots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
        fileFieldBindings: { protein: 'protein_pdb' },
        selectedArtifacts: {
          protein_pdb: makeArtifactFile({ artifact_version_id: 'artifact-version-1' }),
        },
      })
    ).toEqual({
      inputBindings: { protein: 'artifact-version-1' },
      boundFieldKeys: ['protein_pdb'],
    })
  })

  it('projects legacy file uploads into standard input uploads', () => {
    expect(
      buildStandardInputUploadsFromFileFields({
        slots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
        fileFieldBindings: { protein: 'protein_pdb' },
        selectedArtifacts: {},
        uploadedFiles: {
          protein_pdb: {
            fileId: 'file-upload-1',
            filename: 'target.pdb',
            downloadUrl: '/api/v1/files/file-upload-1/download',
          },
        },
        inputBindings: {},
      })
    ).toEqual({
      standardInputUploads: { protein: 'file-upload-1' },
      boundFieldKeys: ['protein_pdb'],
    })
  })

  it('projects selected legacy non-standard artifact files into standard input uploads', () => {
    expect(
      buildStandardInputUploadsFromFileFields({
        slots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
        fileFieldBindings: { protein: 'protein_pdb' },
        selectedArtifacts: { protein_pdb: makeArtifactFile({ id: 'artifact-file-1' }) },
        uploadedFiles: {},
        inputBindings: {},
      })
    ).toEqual({
      standardInputUploads: { protein: 'artifact-file-1' },
      boundFieldKeys: ['protein_pdb'],
    })
  })

  it('resolves direct upload file accept values from standard input type', () => {
    expect(getStandardInputAccept({ name: 'protein', type: 'protein_structure@1', required: true })).toBe('.pdb')
    expect(getStandardInputAccept({ name: 'ligand', type: 'ligand_structure@1', required: true })).toBe('.sdf')
    expect(getStandardInputAccept({ name: 'molecules', type: 'molecule_table@1', required: true })).toBe('.csv,.json,.smi,.txt')
    expect(getStandardInputAccept({ name: 'map', type: 'cryoem_map@1', required: true })).toBeUndefined()
  })

  it('reports only required standard input slots without a binding or upload', () => {
    const slots = [
      { name: 'protein', type: 'protein_structure@1', required: true },
      { name: 'ligand', type: 'ligand_structure@1', required: true },
      { name: 'optional', type: 'molecule_table@1', required: false },
    ] as const

    expect(
      missingRequiredStandardInputSlots({
        slots,
        inputBindings: { protein: 'version-1' },
        hasUpload: slotName => slotName === 'optional',
      }).map(slot => slot.name)
    ).toEqual(['ligand'])
  })

  it('resolves concrete standard input run state from file-field ArtifactVersion selections', () => {
    const state = resolveStandardInputRunState({
      slots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
      fileFieldBindings: { protein: 'protein_pdb' },
      selectedArtifacts: {
        protein_pdb: makeArtifactFile({ artifact_version_id: 'artifact-version-1' }),
      },
      selectedStandardArtifacts: {},
      hasUpload: () => false,
    })

    expect(state.usesConcreteStandardInputFields).toBe(true)
    expect(state.inputBindings).toEqual({ protein: 'artifact-version-1' })
    expect(state.missingRequiredSlots).toEqual([])
  })

  it('resolves direct standard input run state from selected versions and uploads', () => {
    const slots = [
      { name: 'protein', type: 'protein_structure@1', required: true },
      { name: 'ligand', type: 'ligand_structure@1', required: true },
    ] as const

    const state = resolveStandardInputRunState({
      slots,
      fileFieldBindings: {},
      selectedArtifacts: {},
      selectedStandardArtifacts: { protein: makeArtifact() },
      hasUpload: (slotName, context) => !context.usesConcreteStandardInputFields && slotName === 'ligand',
    })

    expect(state.usesConcreteStandardInputFields).toBe(false)
    expect(state.inputBindings).toEqual({ protein: 'version-1' })
    expect(state.missingRequiredSlots).toEqual([])
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
              api_version: 'aidd.sciminer/tool-package',
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
})
