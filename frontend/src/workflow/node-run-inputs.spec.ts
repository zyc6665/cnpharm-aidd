import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { ArtifactFile, ToolSchema } from '@/types/models'
import type { WorkflowNodeArtifactRecommendation } from './canvas-artifacts'
import {
  applyManualArtifactSelection,
  applyManualFileSelection,
  applyRecommendedArtifactBindings,
  buildAutoBoundArtifactCards,
  buildArtifactInputSchema,
  clearAutoBoundArtifactBindings,
  resolveRecommendedArtifactBindings,
  resolveWorkflowNodeRunInputSurface,
} from './node-run-inputs'

function artifact(partial: Partial<ArtifactFile>): ArtifactFile {
  return {
    id: 'file-1',
    filename: 'input.pdb',
    size_bytes: 1024,
    source_type: 'artifact',
    download_url: '/files/file-1',
    task_id: 'task-1',
    tool_id: 'tool-1',
    tool_name: 'Fetch PDB Structure',
    tool_slug: 'builtin-fetch-pdb',
    semantic_type: 'protein_structure@1',
    created_at: '2026-08-20T00:00:00Z',
    ...partial,
  }
}

describe('workflow node run inputs', () => {
  it('keeps generated form labels injectable instead of hardcoded', () => {
    const source = readFileSync(resolve('src/workflow/node-run-inputs.ts'), 'utf8')
    expect(source).not.toContain('标准产物类型')
    expect(source).not.toContain('上游节点')

    const labels = {
      standardArtifactDescription: (artifactType: string) => `Artifact type ${artifactType}`,
      upstreamNodeFallback: 'Previous node',
    }

    expect(buildArtifactInputSchema([
      { name: 'protein', type: 'protein_structure@1', required: true },
    ], labels).properties.protein?.description).toBe('Artifact type protein_structure@1')

    expect(buildAutoBoundArtifactCards({
      autoBoundArtifactByField: {
        protein_pdb: artifact({
          id: 'file-protein',
          filename: 'prepared.pdb',
          tool_name: undefined,
          tool_slug: undefined,
        }),
      },
      flattenedSchema: {
        type: 'object',
        properties: { protein_pdb: { type: 'file', title: 'Protein PDB' } },
        required: [],
      },
      labels,
    })[0]?.sourceLabel).toBe('Previous node · protein_structure@1')
  })

  it('builds file schema from standard artifact inputs', () => {
    expect(buildArtifactInputSchema([
      { name: 'protein', type: 'protein_structure@1', required: true },
      { name: 'ligand', type: 'ligand_structure@1', required: false },
    ])).toEqual({
      type: 'object',
      properties: {
        protein: {
          type: 'file',
          title: 'protein',
          description: 'Standard artifact type: protein_structure@1',
          format: 'file',
        },
        ligand: {
          type: 'file',
          title: 'ligand',
          description: 'Standard artifact type: ligand_structure@1',
          format: 'file',
        },
      },
      required: ['protein'],
    })
  })

  it('resolves concrete tool package fields for node runs', () => {
    const surface = resolveWorkflowNodeRunInputSurface({
      tool: {
        id: 'tool-1',
        name: 'LVpocket',
        slug: 'lvpocket-pocket-prediction',
        description: 'Predict pockets',
        category: 'AIDD',
        tags: [],
        status: 'published',
        usage_count: 0,
        view_count: 0,
        favorite_count: 0,
        gpu_required: true,
        created_at: '2026-09-15T00:00:00Z',
        current_version: {
          id: 'version-1',
          tool_id: 'tool-1',
          version: '1.0.0',
          is_active: true,
          deprecated: false,
          config: {
            type: 'ssh_job',
            tool_package_manifest: {
              api_version: 'aidd.sciminer/tool-package',
              artifacts: {
                inputs: [
                  {
                    name: 'protein',
                    type: 'protein_structure@1',
                    required: true,
                  },
                ],
                outputs: [],
              },
              parameters_schema: {
                type: 'object',
                properties: {
                  model_choice: { type: 'string', default: 'auto' },
                },
              },
            },
            input_schema: {
              type: 'object',
              required: ['protein_pdb'],
              properties: {
                protein_pdb: {
                  type: 'string',
                  format: 'file',
                  title: 'Protein PDB',
                },
                model_choice: { type: 'string', default: 'auto' },
              },
            },
          },
        },
      },
    })

    expect(surface.schema?.properties).toHaveProperty('protein_pdb')
    expect(surface.flattenedSchema.properties).toHaveProperty('protein_pdb')
    expect(surface.standardInputFileFieldBindings).toEqual({
      protein: 'protein_pdb',
    })
    expect(surface.usesSyntheticStandardInputFields).toBe(false)
  })

  it('keeps standard artifact inputs visible beside Tool Package parameters', () => {
    const surface = resolveWorkflowNodeRunInputSurface({
      tool: {
        id: 'tool-v2',
        name: 'Tool Package V2',
        slug: 'tool-package-v2',
        description: 'Consumes a standard protein input',
        category: 'AIDD',
        tags: [],
        status: 'published',
        usage_count: 0,
        view_count: 0,
        favorite_count: 0,
        gpu_required: false,
        created_at: '2026-09-15T00:00:00Z',
        current_version: {
          id: 'version-v2',
          tool_id: 'tool-v2',
          version: '1.0.0',
          is_active: true,
          deprecated: false,
          config: {
            type: 'ssh_job',
            tool_package_manifest: {
              api_version: 'aidd.sciminer/tool-package',
              artifacts: {
                inputs: [
                  {
                    name: 'protein',
                    type: 'protein_structure@1',
                    required: true,
                  },
                ],
                outputs: [],
              },
              parameters_schema: {
                type: 'object',
                properties: {
                  device: { type: 'string', default: 'auto' },
                },
              },
            },
          },
        },
      },
    })

    expect(surface.standardInputFileFieldBindings).toEqual({})
    expect(surface.showStandardArtifactInputs).toBe(true)
    expect(surface.flattenedSchema.properties).toHaveProperty('device')
  })

  it('resolves synthetic artifact fields when a node tool has slots only', () => {
    const surface = resolveWorkflowNodeRunInputSurface({
      tool: null,
      standardInputSlots: [
        { name: 'protein', type: 'protein_structure@1', required: true },
      ],
    })

    expect(surface.schema).toEqual(buildArtifactInputSchema([
      { name: 'protein', type: 'protein_structure@1', required: true },
    ]))
    expect(surface.standardInputFileFieldBindings).toEqual({
      protein: 'protein',
    })
    expect(surface.usesSyntheticStandardInputFields).toBe(true)
  })

  it('auto-binds compatible recommendations without overwriting explicit choices', () => {
    const flattenedSchema: ToolSchema = {
      type: 'object',
      properties: {
        protein_pdb: {
          type: 'string',
          format: 'file',
          title: 'Protein receptor structure',
        },
        ligand_sdf: {
          type: 'string',
          format: 'file',
          title: 'Ligand SDF',
        },
        pocket_pdb: {
          type: 'string',
          format: 'file',
          title: 'Pocket structure',
        },
      },
      required: ['protein_pdb'],
    }
    const selectedLigand = artifact({
      id: 'file-selected-ligand',
      filename: 'manual.sdf',
      semantic_type: 'ligand_structure@1',
    })
    const proteinArtifact = artifact({ id: 'file-protein', filename: '1A2B.pdb' })
    const recommendations: WorkflowNodeArtifactRecommendation[] = [
      {
        edgeId: 'edge-protein',
        sourceNodeId: 'fetch-pdb-node',
        semanticType: 'protein_pdb',
        artifact: proteinArtifact,
      },
      {
        edgeId: 'edge-ligand',
        sourceNodeId: 'ligand-node',
        semanticType: 'ligand_structure@1',
        artifact: artifact({ id: 'file-ligand', filename: 'ligand.sdf', semantic_type: 'ligand_structure@1' }),
      },
      {
        edgeId: 'edge-pocket',
        sourceNodeId: 'pocket-node',
        semanticType: 'binding_pocket@1',
        artifact: artifact({ id: 'file-pocket', filename: 'pocket.pdb', semantic_type: 'binding_pocket@1' }),
      },
    ]

    expect(resolveRecommendedArtifactBindings({
      fileFieldKeys: ['protein_pdb', 'ligand_sdf', 'pocket_pdb'],
      flattenedSchema,
      selectedArtifacts: { ligand_sdf: selectedLigand },
      fileList: { pocket_pdb: [{ uid: 'uploaded-pocket' }] },
      recommendations,
    })).toEqual({
      protein_pdb: proteinArtifact,
    })
  })

  it('applies recommended artifact bindings into run form state', () => {
    const flattenedSchema: ToolSchema = {
      type: 'object',
      properties: {
        protein_pdb: {
          type: 'string',
          format: 'file',
          title: 'Protein receptor structure',
        },
      },
      required: ['protein_pdb'],
    }
    const proteinArtifact = artifact({ id: 'file-protein', filename: '1A2B.pdb' })
    const selectedArtifacts: Record<string, ArtifactFile | undefined> = {}
    const formState: Record<string, unknown> = {}
    const autoBoundArtifactByField: Record<string, ArtifactFile | undefined> = {}

    expect(applyRecommendedArtifactBindings({
      fileFieldKeys: ['protein_pdb'],
      flattenedSchema,
      selectedArtifacts,
      fileList: {},
      formState,
      autoBoundArtifactByField,
      recommendations: [
        {
          edgeId: 'edge-protein',
          sourceNodeId: 'fetch-pdb-node',
          semanticType: 'protein_structure@1',
          artifact: proteinArtifact,
        },
      ],
    })).toEqual(['protein_pdb'])
    expect(selectedArtifacts.protein_pdb).toBe(proteinArtifact)
    expect(formState.protein_pdb).toBe('file-protein')
    expect(autoBoundArtifactByField.protein_pdb).toBe(proteinArtifact)
  })

  it('applies manual file selection and clears artifact bindings for that field', () => {
    const selectedArtifact = artifact({ id: 'file-selected' })
    const autoBoundArtifact = artifact({ id: 'file-auto' })
    const uploadedFile = { uid: 'upload-protein', name: 'protein.pdb' }
    const fileList: Record<string, typeof uploadedFile[]> = {}
    const selectedArtifacts: Record<string, ArtifactFile | undefined> = {
      protein_pdb: selectedArtifact,
    }
    const formState: Record<string, unknown> = { protein_pdb: 'file-selected' }
    const autoBoundArtifactByField: Record<string, ArtifactFile | undefined> = {
      protein_pdb: autoBoundArtifact,
    }

    applyManualFileSelection({
      fieldKey: 'protein_pdb',
      files: [uploadedFile],
      fileList,
      selectedArtifacts,
      formState,
      autoBoundArtifactByField,
    })

    expect(fileList.protein_pdb).toEqual([uploadedFile])
    expect(selectedArtifacts.protein_pdb).toBeUndefined()
    expect(formState.protein_pdb).toBe('upload-protein')
    expect(autoBoundArtifactByField.protein_pdb).toBeUndefined()
  })

  it('applies manual artifact selection and clears uploads for that field', () => {
    const selectedArtifact = artifact({ id: 'file-selected' })
    const autoBoundArtifact = artifact({ id: 'file-auto' })
    const uploadedFile = { uid: 'upload-protein', name: 'protein.pdb' }
    const fileList: Record<string, typeof uploadedFile[]> = {
      protein_pdb: [uploadedFile],
    }
    const selectedArtifacts: Record<string, ArtifactFile | undefined> = {}
    const formState: Record<string, unknown> = { protein_pdb: 'upload-protein' }
    const autoBoundArtifactByField: Record<string, ArtifactFile | undefined> = {
      protein_pdb: autoBoundArtifact,
    }

    applyManualArtifactSelection({
      fieldKey: 'protein_pdb',
      artifact: selectedArtifact,
      fileList,
      selectedArtifacts,
      formState,
      autoBoundArtifactByField,
    })

    expect(selectedArtifacts.protein_pdb).toBe(selectedArtifact)
    expect(formState.protein_pdb).toBe('file-selected')
    expect(fileList.protein_pdb).toEqual([])
    expect(autoBoundArtifactByField.protein_pdb).toBeUndefined()
  })

  it('clears all auto-bound artifact bindings', () => {
    const autoBoundArtifactByField: Record<string, ArtifactFile | undefined> = {
      protein_pdb: artifact({ id: 'file-protein' }),
      ligand_sdf: undefined,
    }

    clearAutoBoundArtifactBindings(autoBoundArtifactByField)

    expect(autoBoundArtifactByField).toEqual({})
  })

  it('builds compact auto-bound artifact cards from schema labels', () => {
    const flattenedSchema: ToolSchema = {
      type: 'object',
      properties: {
        protein_pdb: { type: 'file', title: 'Protein PDB' },
      },
      required: [],
    }

    expect(buildAutoBoundArtifactCards({
      autoBoundArtifactByField: {
        protein_pdb: artifact({ id: 'file-protein', filename: 'prepared.pdb' }),
      },
      flattenedSchema,
    })).toEqual([
      {
        key: 'protein_pdb-file-protein',
        fieldTitle: 'Protein PDB',
        sourceLabel: 'Fetch PDB Structure · protein_structure@1',
        filename: 'prepared.pdb',
      },
    ])
  })
})
