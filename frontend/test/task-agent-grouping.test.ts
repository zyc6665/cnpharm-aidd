import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  collectAgentTaskIds,
  filterAgentRunsForTaskCenter,
  filterStandaloneTasks,
  getTaskCenterPaginationTotal,
  getAgentRunProgress,
  isActiveAgentRunStatus,
  isTerminalAgentRunStatus,
  paginateAgentRunsForTaskCenter,
  paginateStandaloneTasksForTaskCenter,
  shouldShowAgentSection,
  shouldShowStandaloneSection
} from '../src/views/tasks/agent-task-grouping.ts'
import type { AiddAgentRun, Task } from '../src/types/models.ts'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function buildTask(id: string, name: string): Task {
  return {
    id,
    name,
    tool_id: `tool-${id}`,
    status: 'success',
    progress: 100,
    created_at: '2026-06-14T00:00:00Z'
  }
}

function buildRun(overrides: Partial<AiddAgentRun> = {}): AiddAgentRun {
  return {
    id: 'run-1',
    message: 'Analyze protein and generate ligand',
    intent: 'molecule_generation',
    status: 'success',
    input_type: 'protein_pdb',
    input_files: {},
    requested_outputs: ['generated_ligand'],
    plan: {},
    summary: 'Generated ligand workflow',
    created_at: '2026-06-14T00:00:00Z',
    updated_at: '2026-06-14T00:10:00Z',
    steps: [
      {
        id: 'step-1',
        step_key: 'pocket_prediction',
        tool_slug: 'lvpocket',
        task_id: 'task-agent-1',
        status: 'success',
        sort_order: 0,
        depends_on_step_ids: [],
        semantic_inputs: {},
        semantic_outputs: {},
        params: {},
        input_file_ids: [],
        output_file_ids: [],
        created_at: '2026-06-14T00:00:00Z',
        updated_at: '2026-06-14T00:03:00Z'
      },
      {
        id: 'step-2',
        step_key: 'affinity_prediction',
        tool_slug: 'msign-affinity',
        task_id: 'task-agent-2',
        status: 'failure',
        sort_order: 1,
        depends_on_step_ids: ['pocket_prediction'],
        semantic_inputs: {},
        semantic_outputs: {},
        params: {},
        input_file_ids: [],
        output_file_ids: [],
        error_message: 'failed',
        created_at: '2026-06-14T00:03:00Z',
        updated_at: '2026-06-14T00:08:00Z'
      }
    ],
    ...overrides
  }
}

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('agent step task ids should be collected for hiding standalone task cards', () => {
  const ids = collectAgentTaskIds([buildRun()])

  assert.deepEqual([...ids].sort(), ['task-agent-1', 'task-agent-2'])
})

test('standalone task list should exclude tasks linked from agent steps', () => {
  const tasks = [
    buildTask('task-agent-1', 'Pocket task'),
    buildTask('task-standalone', 'Standalone docking')
  ]

  assert.deepEqual(
    filterStandaloneTasks(tasks, new Set(['task-agent-1'])).map(task => task.id),
    ['task-standalone']
  )
})

test('agent runs should follow task center tab and keyword filters', () => {
  const successRun = buildRun({ id: 'run-success', status: 'success' })
  const activeRun = buildRun({
    id: 'run-active',
    status: 'waiting_task',
    message: 'Run MSIGN affinity',
    summary: null
  })

  assert.deepEqual(
    filterAgentRunsForTaskCenter([successRun, activeRun], { tab: 'running' }).map(run => run.id),
    ['run-active']
  )
  assert.deepEqual(
    filterAgentRunsForTaskCenter([successRun, activeRun], { tab: 'history' }).map(run => run.id),
    ['run-success']
  )
  assert.deepEqual(
    filterAgentRunsForTaskCenter([successRun, activeRun], { tab: 'all', keyword: 'msign' }).map(run => run.id),
    ['run-success', 'run-active']
  )
})

test('agent run progress should summarize step state', () => {
  const progress = getAgentRunProgress(buildRun())

  assert.equal(progress.total, 2)
  assert.equal(progress.completed, 1)
  assert.equal(progress.failed, 1)
  assert.equal(progress.percent, 50)
})

test('agent status helpers should distinguish active and terminal runs', () => {
  assert.equal(isTerminalAgentRunStatus('success'), true)
  assert.equal(isTerminalAgentRunStatus('failure'), true)
  assert.equal(isTerminalAgentRunStatus('waiting_task'), false)
  assert.equal(isActiveAgentRunStatus('waiting_task'), true)
  assert.equal(isActiveAgentRunStatus('success'), false)
})

test('task content type tabs should control visible sections', () => {
  assert.equal(shouldShowAgentSection('all'), true)
  assert.equal(shouldShowAgentSection('agent'), true)
  assert.equal(shouldShowAgentSection('standalone'), false)

  assert.equal(shouldShowStandaloneSection('all'), true)
  assert.equal(shouldShowStandaloneSection('agent'), false)
  assert.equal(shouldShowStandaloneSection('standalone'), true)
})

test('task center pagination total should not collapse to current visible page size', () => {
  assert.equal(getTaskCenterPaginationTotal({
    taskTypeTab: 'all',
    visibleStandaloneTaskTotal: 29,
    filteredAgentRunTotal: 4
  }), 29)

  assert.equal(getTaskCenterPaginationTotal({
    taskTypeTab: 'standalone',
    visibleStandaloneTaskTotal: 29,
    filteredAgentRunTotal: 4
  }), 29)

  assert.equal(getTaskCenterPaginationTotal({
    taskTypeTab: 'agent',
    visibleStandaloneTaskTotal: 29,
    filteredAgentRunTotal: 4
  }), 4)
})

test('standalone tasks should paginate after agent child tasks are filtered out', () => {
  const tasks = Array.from({ length: 12 }, (_, index) => buildTask(`task-${index + 1}`, `Task ${index + 1}`))

  assert.deepEqual(
    paginateStandaloneTasksForTaskCenter(tasks, {
      taskTypeTab: 'all',
      currentPage: 1,
      pageSize: 10
    }).map(task => task.id),
    ['task-1', 'task-2', 'task-3', 'task-4', 'task-5', 'task-6', 'task-7', 'task-8', 'task-9', 'task-10']
  )
  assert.deepEqual(
    paginateStandaloneTasksForTaskCenter(tasks, {
      taskTypeTab: 'all',
      currentPage: 2,
      pageSize: 10
    }).map(task => task.id),
    ['task-11', 'task-12']
  )
  assert.deepEqual(
    paginateStandaloneTasksForTaskCenter(tasks, {
      taskTypeTab: 'agent',
      currentPage: 1,
      pageSize: 10
    }),
    []
  )
})

test('agent runs should only be mixed into the first ordinary task page and paginate in agent-only view', () => {
  const runs = Array.from({ length: 12 }, (_, index) => buildRun({ id: `run-${index + 1}` }))

  assert.equal(paginateAgentRunsForTaskCenter(runs, {
    taskTypeTab: 'all',
    currentPage: 1,
    pageSize: 10
  }).length, 12)
  assert.equal(paginateAgentRunsForTaskCenter(runs, {
    taskTypeTab: 'all',
    currentPage: 2,
    pageSize: 10
  }).length, 0)
  assert.deepEqual(
    paginateAgentRunsForTaskCenter(runs, {
      taskTypeTab: 'agent',
      currentPage: 2,
      pageSize: 10
    }).map(run => run.id),
    ['run-11', 'run-12']
  )
})

test('task center source should expose an agent run task card integration point', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/views/tasks/AgentRunTaskCard.vue')), true)

  const source = readSource('src/views/tasks/List.vue')
  assert.equal(source.includes('AgentRunTaskCard'), true)
  assert.equal(source.includes('filterStandaloneTasks'), true)
  assert.equal(source.includes('filterAgentRunsForTaskCenter'), true)
  assert.equal(source.includes('taskTypeTab'), true)
  assert.equal(source.includes('a-segmented'), true)
  assert.equal(source.includes('agent-task-section'), true)
  assert.equal(source.includes('standalone-task-section'), true)
})
