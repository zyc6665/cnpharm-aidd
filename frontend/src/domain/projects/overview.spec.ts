import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { TypedArtifact } from '@/types/artifacts'
import {
  PROJECT_ARTIFACT_FILTER_PRESETS,
  formatProjectResourceSize,
  formatProjectResourceTime,
  getProjectArtifactTypeLabel,
  getProjectOverviewStatCards
} from './overview'

function artifact(overrides: Partial<TypedArtifact> = {}): TypedArtifact {
  return {
    id: 'artifact-1',
    project_id: 'project-1',
    artifact_type: 'binding_pocket',
    semantic_type: 'pocket_semantic',
    name: 'Pocket',
    latest_version: {
      id: 'version-1',
      version: 1,
      filename: 'pocket.pdb',
      size_bytes: 2048,
      sha256: 'a'.repeat(64),
      status: 'available',
      created_at: '2026-08-05T00:00:00Z'
    },
    created_at: '2026-08-05T00:00:00Z',
    updated_at: '2026-08-05T00:00:00Z',
    ...overrides
  }
}

test('项目总览统计卡片按固定标签输出', () => {
  assert.deepEqual(
    getProjectOverviewStatCards({ artifacts: 2, tasks: 3, workflows: 4, boards: 5 }),
    [
      { label: 'Artifact', value: 2 },
      { label: '任务', value: 3 },
      { label: '工作流', value: 4 },
      { label: '白板', value: 5 }
    ]
  )
  assert.deepEqual(getProjectOverviewStatCards(undefined).map(item => item.value), [0, 0, 0, 0])
})

test('Artifact 类型标签优先使用标准类型和版本', () => {
  assert.equal(
    getProjectArtifactTypeLabel(
      artifact({ standard_type: 'binding_pocket', standard_version: 2 })
    ),
    'binding_pocket@2'
  )
  assert.equal(
    getProjectArtifactTypeLabel(artifact({ standard_type: 'binding_pocket', standard_version: null })),
    'binding_pocket@1'
  )
  assert.equal(
    getProjectArtifactTypeLabel(artifact({ standard_type: null, semantic_type: 'semantic-pocket' })),
    'semantic-pocket'
  )
})

test('项目资源大小和时间格式保持 Overview 页面约定', () => {
  assert.equal(formatProjectResourceSize(1), '1 KB')
  assert.equal(formatProjectResourceSize(2048), '2 KB')
  assert.equal(formatProjectResourceSize(1024 * 1024), '1.0 MB')
  assert.equal(formatProjectResourceTime('2026-07-31T08:00:00Z'), '2026-07-31 08:00')
})

test('项目 Artifact 常用筛选预设映射到后端检索参数', () => {
  assert.deepEqual(
    PROJECT_ARTIFACT_FILTER_PRESETS.map(item => [item.key, item.label, item.params]),
    [
      ['recent', '最近', undefined],
      ['protein_structure', '蛋白结构', { standard_type: 'protein_structure' }],
      ['molecule_table', '分子表格', { standard_type: 'molecule_table' }],
      ['molp_pc', 'MolP-PC', { metadata_model_name: 'MolP-PC' }]
    ]
  )
})
