import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getTaskCounts as apiGetTaskCounts,
  getTaskDetail as apiGetTaskDetail,
  prepareTaskRun as apiPrepareTaskRun,
} from '@/api/tasks'
import { useTasksStore } from '../tasks'

vi.mock('@/api/tasks', () => ({
  getTaskList: vi.fn(),
  getTaskDetail: vi.fn(),
  getTaskCounts: vi.fn(),
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
    vi.mocked(apiGetTaskCounts).mockReset()
  })

  it('loads task system view counts without replacing current task page', async () => {
    vi.mocked(apiGetTaskCounts).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: { all: 5, running: 2, history: 3, needs_attention: 1, recent_results: 1 },
    } as never)

    const store = useTasksStore()
    store.tasks = [{
      id: 'task-existing',
      tool_id: 'tool-existing',
      status: 'success',
      progress: 100,
      created_at: '2026-08-20T00:00:00Z',
    }]

    const counts = await store.fetchTaskCounts({ project_id: 'project-1', keyword: 'invalid SDF' })

    expect(apiGetTaskCounts).toHaveBeenCalledWith({
      project_id: 'project-1',
      keyword: 'invalid SDF',
    })
    expect(counts).toEqual({ all: 5, running: 2, history: 3, needs_attention: 1, recent_results: 1 })
    expect(store.viewCounts).toEqual({
      all: 5,
      running: 2,
      history: 3,
      needs_attention: 1,
      recent_results: 1,
    })
    expect(store.tasks).toHaveLength(1)
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

  it('刷新任务详情不影响列表的加载态', async () => {
    // 详情页在任务运行时会反复刷新；如果详情和列表共用一个 loading，
    // 每来一条进度事件，列表页（以及详情页自己）都会被切成骨架屏。
    let resolveDetail: (value: unknown) => void = () => undefined
    vi.mocked(apiGetTaskDetail).mockImplementation(
      () =>
        new Promise(resolve => {
          resolveDetail = resolve
        }) as never
    )

    const store = useTasksStore()
    store.loading = true // 模拟列表正在加载
    const pending = store.fetchTaskDetail('task-1')

    expect(store.detailLoading).toBe(true)
    expect(store.loading).toBe(true) // 列表的加载态不被详情的请求改写

    resolveDetail({
      code: 200,
      message: 'ok',
      data: { id: 'task-1', status: 'running', progress: 42 },
    })
    await pending

    expect(store.detailLoading).toBe(false)
    expect(store.loading).toBe(true)
    expect(store.currentTask?.id).toBe('task-1')
  })
})
