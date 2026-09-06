import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { prepareTaskRun as apiPrepareTaskRun } from '@/api/tasks'
import { useTasksStore } from '../tasks'

vi.mock('@/api/tasks', () => ({
  getTaskList: vi.fn(),
  getTaskDetail: vi.fn(),
  createTask: vi.fn(),
  cancelTask: vi.fn(),
  retryTask: vi.fn(),
  deleteTask: vi.fn(),
  prepareTaskRun: vi.fn(),
}))

describe('useTasksStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(apiPrepareTaskRun).mockReset()
  })

  it('previews task run preparation without mutating task list state', async () => {
    const preview = {
      ready: false,
      project_id: 'project-1',
      tool_id: 'tool-lvpocket',
      tool_version_id: 'version-lvpocket',
      params: {},
      file_ids: [],
      input_bindings: {},
      requested_input_bindings: { protein: 'artifact-version-raw' },
      standard_input_uploads: {},
      binding_decisions: {
        protein: {
          status: 'needs_preparation',
          reason: 'Protein input requires a prepared PDB role.',
        },
      },
      blocked_reason: 'Protein input requires a prepared PDB role.',
      resource_snapshot: null,
    }
    vi.mocked(apiPrepareTaskRun).mockResolvedValue({ code: 200, message: 'ok', data: preview } as never)

    const store = useTasksStore()
    store.tasks = [{
      id: 'task-existing',
      tool_id: 'tool-existing',
      status: 'success',
      progress: 100,
      created_at: '2026-08-20T00:00:00Z',
    }]
    store.total = 1

    const result = await store.prepareTaskRun({
      tool_id: 'tool-lvpocket',
      project_id: 'project-1',
      params: {},
      input_bindings: { protein: 'artifact-version-raw' },
    })

    expect(apiPrepareTaskRun).toHaveBeenCalledWith({
      tool_id: 'tool-lvpocket',
      project_id: 'project-1',
      params: {},
      input_bindings: { protein: 'artifact-version-raw' },
    })
    expect(result).toEqual(preview)
    expect(store.tasks).toHaveLength(1)
    expect(store.total).toBe(1)
    expect(store.loading).toBe(false)
  })
})
