import { describe, expect, it } from 'vitest'
import type { ArtifactFile, ToolSchema } from '@/types/models'
import type { WorkflowNodeArtifactRecommendation } from './canvas-artifacts'
import {
  buildAutoBoundArtifactCards,
  buildArtifactInputSchema,
  resolveRecommendedArtifactBindings,
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
