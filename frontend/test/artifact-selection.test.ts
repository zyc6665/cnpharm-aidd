import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { ArtifactFile } from '../src/types/models'

function artifact(overrides: Partial<ArtifactFile>): ArtifactFile {
  return {
    id: 'artifact',
    filename: 'result.pdb',
    content_type: 'chemical/x-pdb',
    size_bytes: 128,
    source_type: 'output',
    download_url: '/files/artifact',
    task_id: 'task-a',
    tool_id: 'tool-a',
    tool_name: 'Pocket Tool',
    tool_slug: 'pocket-tool',
    created_at: '2026-05-29T09:00:00Z',
    ...overrides
  }
}

test('groupCompatibleArtifactsByTask 应按 accept 过滤产物并排除日志与中间文件', async () => {
  const { groupCompatibleArtifactsByTask } = await import('../src/components/tools/artifact-selection.ts')

  const groups = groupCompatibleArtifactsByTask(
    [
      artifact({ id: 'pdb-old', filename: 'output/protein_old.pdb', task_id: 'task-a', created_at: '2026-05-29T08:00:00Z' }),
      artifact({ id: 'log-file', filename: 'output/logs/run.log', task_id: 'task-a', created_at: '2026-05-29T09:00:00Z' }),
      artifact({ id: 'tmp-file', filename: 'output/intermediate/cache.sdf', task_id: 'task-a', created_at: '2026-05-29T10:00:00Z' }),
      artifact({ id: 'sdf-new', filename: 'output/poses/ligand.sdf', task_id: 'task-b', tool_name: 'Docking', created_at: '2026-05-29T11:00:00Z' }),
      artifact({ id: 'csv-file', filename: 'output/report.csv', task_id: 'task-b', content_type: 'text/csv', created_at: '2026-05-29T12:00:00Z' })
    ],
    '.pdb,.sdf'
  )

  assert.deepEqual(groups.map((group) => group.taskId), ['task-b', 'task-a'])
  assert.deepEqual(groups.flatMap((group) => group.artifacts.map((item) => item.id)), ['sdf-new', 'pdb-old'])
})

test('groupCompatibleArtifactsByTask 应在未指定 accept 时仍隐藏噪音文件', async () => {
  const { groupCompatibleArtifactsByTask } = await import('../src/components/tools/artifact-selection.ts')

  const groups = groupCompatibleArtifactsByTask([
    artifact({ id: 'result-file', filename: 'output/result.json', content_type: 'application/json' }),
    artifact({ id: 'stderr-file', filename: 'output/stderr.txt', content_type: 'text/plain' })
  ])

  assert.deepEqual(groups.map((group) => group.artifacts.map((item) => item.id)), [['result-file']])
})

test('groupCompatibleArtifactsByTask 应只展示当前工具产生的任务', async () => {
  const { groupCompatibleArtifactsByTask } = await import('../src/components/tools/artifact-selection.ts')

  const groups = groupCompatibleArtifactsByTask(
    [
      artifact({ id: 'same-tool-a', task_id: 'task-a', tool_id: 'tool-current', tool_slug: 'current-tool', created_at: '2026-05-29T08:00:00Z' }),
      artifact({ id: 'same-tool-b', task_id: 'task-b', tool_id: 'tool-current', tool_slug: 'current-tool', created_at: '2026-05-29T09:00:00Z' }),
      artifact({ id: 'other-tool', task_id: 'task-c', tool_id: 'tool-other', tool_slug: 'other-tool', created_at: '2026-05-29T10:00:00Z' })
    ],
    '.pdb',
    { toolId: 'tool-current', toolSlug: 'current-tool' }
  )

  assert.deepEqual(groups.map((group) => group.taskId), ['task-b', 'task-a'])
  assert.deepEqual(groups.flatMap((group) => group.artifacts.map((item) => item.id)), ['same-tool-b', 'same-tool-a'])
})
