import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  buildWorkflowRunSummary,
  getWorkflowRunStatusTone,
  isWorkflowRunTerminal,
  shouldAutoSyncWorkflowRun
} from '../src/workflow/workflow-runs.ts'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

test('工作流运行摘要应按执行顺序输出节点状态和完成比例', () => {
  const summary = buildWorkflowRunSummary({
    id: 'run-1',
    owner_id: 'user-1',
    name: 'Docking flow',
    status: 'waiting_task',
    definition: { nodes: [], edges: [] },
    input_files: {},
    execution_order: ['prepare', 'dock', 'score'],
    node_states: {
      prepare: {
        status: 'success',
        task_id: 'task-1',
        tool_slug: 'prepare-tool',
        tool_version_id: 'version-1',
        input_file_ids: ['file-protein'],
        semantic_outputs: {
          pocket_pdb: { file_id: 'file-pocket' }
        },
        params: { device: 'cpu' }
      },
      dock: {
        status: 'waiting_task',
        task_id: 'task-2',
        tool_slug: 'dock-tool',
        tool_version_id: 'version-2',
        input_file_ids: ['file-pocket'],
        params: { exhaustiveness: 8 }
      },
      score: { status: 'pending', tool_slug: 'score-tool' }
    },
    artifact_lineage: {},
    created_at: '2026-06-17T00:00:00Z',
    updated_at: '2026-06-17T00:00:00Z'
  })

  assert.equal(summary.total, 3)
  assert.equal(summary.completed, 1)
  assert.equal(summary.running, 1)
  assert.equal(summary.failed, 0)
  assert.equal(summary.percent, 33)
  assert.deepEqual(
    summary.nodes.map((node) => [
      node.id,
      node.status,
      node.toolSlug,
      node.taskId,
      node.toolVersionId,
      node.inputFileIds.join(','),
      node.outputSemanticTypes.join(',')
    ]),
    [
      ['prepare', 'success', 'prepare-tool', 'task-1', 'version-1', 'file-protein', 'pocket_pdb'],
      ['dock', 'waiting_task', 'dock-tool', 'task-2', 'version-2', 'file-pocket', ''],
      ['score', 'pending', 'score-tool', null, null, '', '']
    ]
  )
})

test('工作流运行摘要应识别终态和展示色调', () => {
  assert.equal(isWorkflowRunTerminal('success'), true)
  assert.equal(isWorkflowRunTerminal('failure'), true)
  assert.equal(isWorkflowRunTerminal('waiting_task'), false)
  assert.equal(getWorkflowRunStatusTone('success'), 'success')
  assert.equal(getWorkflowRunStatusTone('failure'), 'error')
  assert.equal(getWorkflowRunStatusTone('waiting_task'), 'processing')
})

test('工作流运行自动同步应只覆盖可轮询的非终态运行', () => {
  const baseRun = {
    id: 'run-1',
    owner_id: 'user-1',
    name: 'Docking flow',
    status: 'waiting_task',
    definition: { nodes: [], edges: [] },
    input_files: {},
    execution_order: [],
    node_states: {},
    artifact_lineage: {},
    created_at: '2026-06-17T00:00:00Z',
    updated_at: '2026-06-17T00:00:00Z'
  }

  assert.equal(
    shouldAutoSyncWorkflowRun(baseRun, {
      isLoggedIn: true,
      isLoading: false,
      isSyncing: false
    }),
    true
  )
  assert.equal(
    shouldAutoSyncWorkflowRun({ ...baseRun, status: 'success' }, {
      isLoggedIn: true,
      isLoading: false,
      isSyncing: false
    }),
    false
  )
  assert.equal(
    shouldAutoSyncWorkflowRun(baseRun, {
      isLoggedIn: false,
      isLoading: false,
      isSyncing: false
    }),
    false
  )
  assert.equal(
    shouldAutoSyncWorkflowRun(baseRun, {
      isLoggedIn: true,
      isLoading: true,
      isSyncing: false
    }),
    false
  )
})

test('工作流运行状态面板应展示节点输入输出和版本追踪信息', () => {
  const source = readFileSync(
    resolve(rootDir, 'src/components/workflow/WorkflowRunStatusPanel.vue'),
    'utf8'
  )

  assert.equal(source.includes('node.toolVersionId'), true)
  assert.equal(source.includes('node.inputFileIds'), true)
  assert.equal(source.includes('node.outputSemanticTypes'), true)
  assert.equal(source.includes('node.paramsText'), true)
})
