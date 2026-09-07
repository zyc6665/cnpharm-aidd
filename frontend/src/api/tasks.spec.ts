import { describe, expect, it, vi } from 'vitest'
import { get, post } from './request'
import { getTaskCounts, getTaskList, prepareTaskRun } from './tasks'

vi.mock('./request', () => ({
  get: vi.fn(),
  post: vi.fn(),
  del: vi.fn()
}))

describe('getTaskList', () => {
  it('透传系统任务视图筛选参数', async () => {
    const response = {
      code: 200,
      message: 'ok',
      data: { items: [], total: 0, page: 1, page_size: 20 }
    }
    vi.mocked(get).mockResolvedValueOnce(response as never)

    const result = await getTaskList({
      view: 'needs_attention',
      project_id: 'project-1',
      created_from: '2026-09-01T00:00:00.000Z',
      created_to: '2026-09-07T23:59:59.999Z',
      workflow_run_id: 'workflow-run-1',
      workflow_node_id: 'protein_preparation'
    })

    expect(get).toHaveBeenCalledWith(
      '/tasks',
      {
        view: 'needs_attention',
        project_id: 'project-1',
        created_from: '2026-09-01T00:00:00.000Z',
        created_to: '2026-09-07T23:59:59.999Z',
        workflow_run_id: 'workflow-run-1',
        workflow_node_id: 'protein_preparation'
      },
      undefined
    )
    expect(result).toEqual(response)
  })
})

describe('getTaskCounts', () => {
  it('调用任务系统视图计数接口并透传筛选参数', async () => {
    const response = {
      code: 200,
      message: 'ok',
      data: { all: 5, running: 2, history: 3, needs_attention: 1, recent_results: 1 }
    }
    vi.mocked(get).mockResolvedValueOnce(response as never)

    const result = await getTaskCounts({
      project_id: 'project-1',
      keyword: 'invalid SDF',
      created_from: '2026-09-01T00:00:00.000Z',
    })

    expect(get).toHaveBeenCalledWith(
      '/tasks/counts',
      {
        project_id: 'project-1',
        keyword: 'invalid SDF',
        created_from: '2026-09-01T00:00:00.000Z',
      },
      undefined
    )
    expect(result).toEqual(response)
  })
})

describe('prepareTaskRun', () => {
  it('调用后端运行准备预览接口并透传任务创建 payload', async () => {
    const payload = {
      tool_id: 'tool-1',
      project_id: 'project-1',
      params: { params: { model_choice: 'auto' } },
      input_bindings: { protein: 'artifact-version-1' }
    }
    const preview = {
      ready: true,
      project_id: 'project-1',
      tool_id: 'tool-1',
      tool_version_id: 'version-1',
      params: { input_files: { protein_pdb: 'input/prepared.pdb' } },
      file_ids: ['file-prepared'],
      input_bindings: {},
      requested_input_bindings: { protein: 'artifact-version-1' },
      standard_input_uploads: {},
      binding_decisions: { protein: { status: 'ready', selected_role: 'prepared_pdb' } },
      blocked_reason: null,
      resource_snapshot: {
        executor_type: 'ssh_job',
        gpu_required: false,
        gpu_memory_mb: 0,
        timeout_sec: 600,
        resource_profile: {}
      }
    }
    vi.mocked(post).mockResolvedValueOnce({ code: 200, message: 'ok', data: preview } as never)

    const response = await prepareTaskRun(payload)

    expect(post).toHaveBeenCalledWith('/tasks/prepare-preview', payload)
    expect(response.data).toEqual(preview)
  })
})
