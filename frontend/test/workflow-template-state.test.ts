import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveWorkflowCanvasNodeStatus } from '../src/workflow/template-state.ts'
import type { WorkflowCanvasNode } from '../src/workflow/template-types.ts'

const toolNode: WorkflowCanvasNode = {
  id: 'tool-node',
  type: 'tool',
  stepKey: 'pocketExploration',
  toolSlugs: ['pocket-explorer', 'alt-explorer'],
  titleKey: 'workflow.nodes.tool.title',
  position: { x: 0, y: 0 },
  requiredInputTypes: ['protein_structure']
}

test('workflow canvas node status requires tool selection for multi-tool nodes', () => {
  assert.equal(
    resolveWorkflowCanvasNodeStatus({
      node: toolNode,
      selectedToolSlug: null,
      hasRequiredInputs: true,
      task: null
    }),
    'needs_tool_selection'
  )
})

test('workflow canvas node status stays idle when required inputs are missing', () => {
  assert.equal(
    resolveWorkflowCanvasNodeStatus({
      node: toolNode,
      selectedToolSlug: 'pocket-explorer',
      hasRequiredInputs: false,
      task: null
    }),
    'idle'
  )
})

test('workflow canvas node status becomes ready when tool and inputs are available', () => {
  assert.equal(
    resolveWorkflowCanvasNodeStatus({
      node: toolNode,
      selectedToolSlug: 'pocket-explorer',
      hasRequiredInputs: true,
      task: null
    }),
    'ready'
  )
})

test('workflow canvas node status mirrors task runtime state', () => {
  assert.equal(
    resolveWorkflowCanvasNodeStatus({
      node: toolNode,
      selectedToolSlug: 'pocket-explorer',
      hasRequiredInputs: true,
      task: {
        id: 'task-1',
        name: 'Pocket exploration',
        tool_id: 'tool-1',
        tool_slug: 'pocket-explorer',
        status: 'running',
        progress: 50,
        progress_message: 'running',
        error_message: null,
        started_at: '2026-06-15T00:00:00Z',
        finished_at: null,
        created_at: '2026-06-15T00:00:00Z',
        updated_at: '2026-06-15T00:00:01Z',
        output_data: null,
        output_files: []
      }
    }),
    'running'
  )
})

test('workflow canvas node status becomes failed for failed tasks', () => {
  assert.equal(
    resolveWorkflowCanvasNodeStatus({
      node: toolNode,
      selectedToolSlug: 'pocket-explorer',
      hasRequiredInputs: true,
      task: {
        id: 'task-2',
        name: 'Pocket exploration',
        tool_id: 'tool-1',
        tool_slug: 'pocket-explorer',
        status: 'failure',
        progress: 100,
        progress_message: 'failed',
        error_message: 'boom',
        started_at: '2026-06-15T00:00:00Z',
        finished_at: '2026-06-15T00:00:10Z',
        created_at: '2026-06-15T00:00:00Z',
        updated_at: '2026-06-15T00:00:10Z',
        output_data: null,
        output_files: []
      }
    }),
    'failed'
  )
})

test('workflow canvas node status becomes completed for successful tasks', () => {
  assert.equal(
    resolveWorkflowCanvasNodeStatus({
      node: toolNode,
      selectedToolSlug: 'pocket-explorer',
      hasRequiredInputs: true,
      task: {
        id: 'task-3',
        name: 'Pocket exploration',
        tool_id: 'tool-1',
        tool_slug: 'pocket-explorer',
        status: 'success',
        progress: 100,
        progress_message: 'done',
        error_message: null,
        started_at: '2026-06-15T00:00:00Z',
        finished_at: '2026-06-15T00:00:10Z',
        created_at: '2026-06-15T00:00:00Z',
        updated_at: '2026-06-15T00:00:10Z',
        output_data: null,
        output_files: []
      }
    }),
    'completed'
  )
})
