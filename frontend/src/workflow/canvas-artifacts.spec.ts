import { describe, expect, it } from 'vitest'
import type { ArtifactFile } from '@/types/models'
import type { WorkflowCanvasPreset } from './canvas-types'
import { recommendArtifactsForNode } from './canvas-artifacts'

function artifact(overrides: Partial<ArtifactFile>): ArtifactFile {
  return {
    id: 'file-1',
    filename: 'artifact.dat',
    content_type: 'application/octet-stream',
    size_bytes: 1,
    source_type: 'artifact',
    download_url: '/api/v1/files/file-1/download',
    task_id: 'task-fetch-pdb',
    tool_id: 'tool-fetch-pdb',
    tool_name: 'Fetch PDB Structure',
    tool_slug: 'builtin-fetch-pdb',
    semantic_type: 'run_report@1',
    created_at: '2026-08-20T00:00:00Z',
    ...overrides
  }
}

describe('recommendArtifactsForNode', () => {
  it('按连线语义推荐上游任务产物，避免把报告文件绑定到蛋白输入', () => {
    const template: WorkflowCanvasPreset = {
      id: 'flow',
      kind: 'free',
      nameKey: 'Flow',
      nodes: [
        { id: 'fetch-pdb-node', type: 'tool', titleKey: 'Fetch PDB', position: { x: 0, y: 0 } },
        { id: 'lvpocket-node', type: 'tool', titleKey: 'LVpocket', position: { x: 320, y: 0 } }
      ],
      edges: [
        {
          id: 'edge-fetch-pdb-to-lvpocket',
          source: 'fetch-pdb-node',
          target: 'lvpocket-node',
          artifactType: 'protein_structure@1'
        }
      ]
    }

    const recommendations = recommendArtifactsForNode({
      template,
      nodeId: 'lvpocket-node',
      taskByNode: {
        'fetch-pdb-node': {
          id: 'task-fetch-pdb',
          name: 'Fetch PDB Structure',
          tool_id: 'tool-fetch-pdb',
          tool_slug: 'builtin-fetch-pdb',
          status: 'success',
          progress: 100,
          created_at: '2026-08-20T00:00:00Z'
        }
      },
      artifacts: [
        artifact({
          id: 'file-report',
          filename: 'fetch_pdb_report.json',
          content_type: 'application/json',
          semantic_type: 'run_report@1',
          created_at: '2026-08-20T00:03:00Z'
        }),
        artifact({
          id: 'file-pdb',
          filename: '1A2B.pdb',
          content_type: 'chemical/x-pdb',
          semantic_type: 'protein_structure@1',
          created_at: '2026-08-20T00:01:00Z'
        })
      ]
    })

    expect(recommendations).toHaveLength(1)
    expect(recommendations[0]?.artifact?.id).toBe('file-pdb')
  })
})
