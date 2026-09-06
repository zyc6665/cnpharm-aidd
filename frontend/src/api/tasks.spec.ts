import { describe, expect, it, vi } from 'vitest'
import { post } from './request'
import { prepareTaskRun } from './tasks'

vi.mock('./request', () => ({
  get: vi.fn(),
  post: vi.fn(),
  del: vi.fn()
}))

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
