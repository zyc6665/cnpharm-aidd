import { describe, expect, it } from 'vitest'
import { taskRunPreparationBlockedMessage } from './run-preparation'
import type { TaskRunPreparationPreview } from '@/types/models'

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
