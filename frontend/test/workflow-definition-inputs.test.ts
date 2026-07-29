import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  buildWorkflowInputFileMap,
  extractWorkflowInputRequirements,
  findLatestArtifactForSemanticType
} from '../src/workflow/workflow-definitions.ts'

test('工作流定义工具应提取模板必需输入并构建 input_files', () => {
  const requirements = extractWorkflowInputRequirements({
    nodes: [
      {
        id: 'dock',
        kind: 'tool',
        semantic_inputs: {
          protein_pdb: 'workflow_input:protein_pdb',
          ligand_sdf: 'workflow_input:ligand_sdf'
        }
      },
      {
        id: 'score',
        kind: 'tool',
        semantic_inputs: {
          protein_pdb: 'workflow_input:protein_pdb',
          ligand_sdf: 'dock:poses_sdf'
        }
      }
    ],
    edges: []
  })

  assert.deepEqual(requirements, ['protein_pdb', 'ligand_sdf'])
  assert.deepEqual(
    buildWorkflowInputFileMap(requirements, {
      protein_pdb: 'file-protein',
      ligand_sdf: '',
      ignored: 'file-extra'
    }),
    { protein_pdb: 'file-protein' }
  )
})

test('工作流定义工具应支持按语义类型匹配最新产物', () => {
  const artifact = findLatestArtifactForSemanticType(
    [
      {
        id: 'old',
        filename: 'old.pdb',
        size_bytes: 1,
        source_type: 'task_output',
        download_url: '/old',
        task_id: 'task-1',
        tool_id: 'tool-1',
        tool_name: 'Tool',
        tool_slug: 'tool',
        semantic_type: 'protein_pdb',
        created_at: '2026-01-01T00:00:00Z'
      },
      {
        id: 'new',
        filename: 'new.pdb',
        size_bytes: 1,
        source_type: 'task_output',
        download_url: '/new',
        task_id: 'task-2',
        tool_id: 'tool-1',
        tool_name: 'Tool',
        tool_slug: 'tool',
        semantic_type: 'protein_pdb',
        created_at: '2026-02-01T00:00:00Z'
      }
    ],
    'protein_pdb'
  )

  assert.equal(artifact?.id, 'new')
})
