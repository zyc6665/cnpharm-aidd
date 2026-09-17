import { describe, expect, it } from 'vitest'
import type { ArtifactFile, ToolSchema } from '@/types/models'
import type { WorkflowNodeArtifactRecommendation } from './canvas-artifacts'
import {
  applyRecommendedArtifactBindings,
  buildAutoBoundArtifactCards,
  buildArtifactInputSchema,
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
          description: '标准产物类型：protein_structure@1',
          format: 'file',
        },
        ligand: {
          type: 'file',
          title: 'ligand',
          description: '标准产物类型：ligand_structure@1',
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
              api_version: 'aidd.sciminer/tool-package.v2',
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
