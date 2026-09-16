import { describe, expect, it, vi } from 'vitest'
import { prepareAndCreateTask, taskRunPreparationBlockedMessage } from './run-preparation'
import type { Task, TaskCreateParams, TaskRunPreparationPreview } from '@/types/models'

function makePreview(input: Partial<TaskRunPreparationPreview>): TaskRunPreparationPreview {
  return {
    ready: true,
    project_id: 'project-1',
    tool_id: 'tool-1',
    tool_version_id: 'version-1',
    params: {},
    file_ids: [],
    input_bindings: {},
    requested_input_bindings: {},
    standard_input_uploads: {},
    binding_decisions: {},
    blocked_reason: null,
    resource_snapshot: null,
    ...input,
  }
}

function makeTask(): Task {
  return {
    id: 'task-1',
    tool_id: 'tool-1',
    status: 'pending',
    progress: 0,
    created_at: '2026-09-16T00:00:00Z',
  }
}

const taskPayload: TaskCreateParams = {
  tool_id: 'tool-1',
  params: {},
  file_ids: undefined,
}

describe('taskRunPreparationBlockedMessage', () => {
  it('returns empty message for missing or ready preview', () => {
    expect(taskRunPreparationBlockedMessage(null)).toBe('')
    expect(taskRunPreparationBlockedMessage(makePreview({ ready: true }))).toBe('')
  })

  it('uses blocked_reason first when preview is blocked', () => {
    expect(taskRunPreparationBlockedMessage(makePreview({
      ready: false,
      blocked_reason: 'Protein input requires a prepared PDB role.',
      binding_decisions: {
        protein: { status: 'needs_preparation', reason: 'Fallback reason.' },
      },
    }))).toBe('Protein input requires a prepared PDB role.')
  })

  it('falls back to binding decision reason and then generic message', () => {
    expect(taskRunPreparationBlockedMessage(makePreview({
      ready: false,
      blocked_reason: null,
      binding_decisions: {
        protein: { status: 'needs_preparation', reason: 'Prepare protein first.' },
      },
    }))).toBe('Prepare protein first.')

    expect(taskRunPreparationBlockedMessage(makePreview({
      ready: false,
      blocked_reason: null,
      binding_decisions: {},
    }))).toBe('标准产物输入尚未满足工具要求')
  })
})

describe('prepareAndCreateTask', () => {
  it('creates the task after a ready preparation preview', async () => {
    const preview = makePreview({ ready: true })
    const task = makeTask()
    const api = {
      prepareTaskRun: vi.fn().mockResolvedValue(preview),
      createTask: vi.fn().mockResolvedValue(task),
    }

    await expect(prepareAndCreateTask(taskPayload, api)).resolves.toEqual({
      status: 'created',
      preview,
      task,
    })
    expect(api.prepareTaskRun).toHaveBeenCalledWith(taskPayload)
    expect(api.createTask).toHaveBeenCalledWith(taskPayload)
  })

  it('returns a blocked result without creating a task when preparation is not ready', async () => {
    const preview = makePreview({
      ready: false,
      blocked_reason: 'Protein input requires a prepared PDB role.',
    })
    const api = {
      prepareTaskRun: vi.fn().mockResolvedValue(preview),
      createTask: vi.fn().mockResolvedValue(makeTask()),
    }

    await expect(prepareAndCreateTask(taskPayload, api)).resolves.toEqual({
      status: 'blocked',
      preview,
      message: 'Protein input requires a prepared PDB role.',
    })
    expect(api.prepareTaskRun).toHaveBeenCalledWith(taskPayload)
    expect(api.createTask).not.toHaveBeenCalled()
  })
})
