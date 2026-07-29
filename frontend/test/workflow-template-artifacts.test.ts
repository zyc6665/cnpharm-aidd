import { test } from 'vitest'
import assert from 'node:assert/strict'

import {
  recommendArtifactsForNode,
  resolveNodeInputRequirements
} from '../src/workflow/template-artifacts.ts'
import { AIDD_WORKFLOW_TEMPLATE } from '../src/workflow/templates.ts'
import type { WorkflowTaskRef } from '../src/workflow/artifact-types.ts'
import type { ArtifactFile } from '../src/types/models.d.ts'

function createTask(id: string, status: WorkflowTaskRef['status'] = 'success'): WorkflowTaskRef {
  return {
    id,
    name: id,
    tool_id: `${id}-tool`,
    tool_slug: 'pocket-explorer',
    status,
    progress: 100,
    progress_message: null,
    error_message: null,
    started_at: '2026-06-15T00:00:00Z',
    finished_at: '2026-06-15T00:00:10Z',
    created_at: '2026-06-15T00:00:00Z',
    updated_at: '2026-06-15T00:00:10Z',
    output_data: null,
    output_files: []
  }
}

function createArtifact(input: {
  id: string
  taskId: string
  createdAt: string
}): ArtifactFile {
  return {
    id: input.id,
    filename: `${input.id}.pdb`,
    size_bytes: 1,
    source_type: 'task_output',
    download_url: `/files/${input.id}`,
    task_id: input.taskId,
    tool_id: 'tool-1',
    tool_name: 'Pocket Explorer',
    tool_slug: 'pocket-explorer',
    created_at: input.createdAt
  }
}

test('node input requirements follow incoming semantic edges', () => {
  const requirements = resolveNodeInputRequirements({
    template: AIDD_WORKFLOW_TEMPLATE,
    nodeId: 'tool-docking'
  })

  assert.deepEqual(
    requirements.map(requirement => requirement.semanticType).sort(),
    ['generated_ligand', 'protein_pdb']
  )
})

test('artifact recommendation prefers latest upstream task artifact', () => {
  const recommendations = recommendArtifactsForNode({
    template: AIDD_WORKFLOW_TEMPLATE,
    nodeId: 'tool-molecule-generation',
    artifacts: [
      createArtifact({
        id: 'old-pocket',
        taskId: 'pocket-task',
        createdAt: '2026-06-15T00:00:01Z'
      }),
      createArtifact({
        id: 'new-pocket',
        taskId: 'pocket-task',
        createdAt: '2026-06-15T00:00:02Z'
      })
    ],
    taskByNode: {
      'tool-pocket-exploration': createTask('pocket-task')
    }
  })

  assert.equal(recommendations[0]?.artifact?.id, 'new-pocket')
})

test('artifact recommendation marks missing input when upstream task is unavailable', () => {
  const recommendations = recommendArtifactsForNode({
    template: AIDD_WORKFLOW_TEMPLATE,
    nodeId: 'tool-molecule-generation',
    artifacts: [],
    taskByNode: {}
  })

  assert.equal(recommendations.length, 1)
  assert.equal(recommendations[0]?.semanticType, 'pocket_pdb')
  assert.equal(recommendations[0]?.artifact, null)
})
