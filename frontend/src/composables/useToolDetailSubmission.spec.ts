import { computed, reactive, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { UploadFile } from 'ant-design-vue'
import type { FileUploadResponse, Task, TaskRunPreparationPreview, ToolSchema } from '@/types/models'
import { useToolDetailSubmission } from './useToolDetailSubmission'

function makeUploadItem(name: string): UploadFile {
  return {
    uid: `upload-${name}`,
    name,
    originFileObj: new File(['PDB'], name) as UploadFile['originFileObj'],
  }
}

function makeFileResponse(id: string, filename: string): FileUploadResponse {
  return {
    id,
    filename,
    size_bytes: 123,
    content_type: 'chemical/x-pdb',
    sha256: 'abc',
  }
}

function makeReadyPreview(): TaskRunPreparationPreview {
  return {
    ready: true,
    project_id: 'project-1',
    tool_id: 'tool-lvpocket',
    tool_version_id: 'version-lvpocket',
    params: {},
    file_ids: [],
    input_bindings: {},
    requested_input_bindings: {},
    standard_input_uploads: {},
    binding_decisions: {},
    resource_snapshot: null,
  }
}

function makeTask(): Task {
  return {
    id: 'task-created',
    tool_id: 'tool-lvpocket',
    status: 'pending',
    progress: 0,
    created_at: '2026-09-13T00:00:00Z',
  }
}

const flattenedSchema: ToolSchema = {
  type: 'object',
  required: ['protein_pdb'],
  properties: {
    protein_pdb: { type: 'file', title: 'Protein PDB', format: 'file' },
    model_choice: { type: 'string', title: 'Model weight', default: 'auto' },
  },
}

describe('useToolDetailSubmission', () => {
  it('requires login before preparing a task run', async () => {
    const api = {
      uploadFile: vi.fn(),
      prepareTaskRun: vi.fn(),
      createTask: vi.fn(),
    }
    const onRequireLogin = vi.fn()
    const submission = useToolDetailSubmission({
      isLoggedIn: computed(() => false),
      toolId: computed(() => 'tool-lvpocket'),
      taskName: ref('Pocket run'),
      projectId: computed(() => 'project-1'),
      flattenedSchema: computed(() => flattenedSchema),
      formState: reactive({}),
      fileList: reactive({}),
      selectedArtifacts: reactive({}),
      resolvedFiles: {},
      standardInputSlots: computed(() => []),
      standardInputFileFieldBindings: computed(() => ({})),
      selectedStandardArtifacts: reactive({}),
      standardInputFileList: reactive({}),
      executorType: computed(() => 'ssh_job'),
      missingRequiredStandardSlots: computed(() => []),
      api,
      onRequireLogin,
      onNoSchema: vi.fn(),
      onMissingStandardInputs: vi.fn(),
      onBlocked: vi.fn(),
      onTaskCreated: vi.fn(),
    })

    await submission.handleSubmit()

    expect(onRequireLogin).toHaveBeenCalled()
    expect(api.prepareTaskRun).not.toHaveBeenCalled()
    expect(api.createTask).not.toHaveBeenCalled()
    expect(submission.submitting.value).toBe(false)
  })

  it('prepares and creates a task from the current run form state', async () => {
    const api = {
      uploadFile: vi.fn().mockResolvedValue(makeFileResponse('file-protein', 'protein.pdb')),
      prepareTaskRun: vi.fn().mockResolvedValue(makeReadyPreview()),
      createTask: vi.fn().mockResolvedValue(makeTask()),
    }
    const onTaskCreated = vi.fn()
    const submission = useToolDetailSubmission({
      isLoggedIn: computed(() => true),
      toolId: computed(() => 'tool-lvpocket'),
      taskName: ref('Pocket run'),
      projectId: computed(() => 'project-1'),
      flattenedSchema: computed(() => flattenedSchema),
      formState: reactive({ protein_pdb: 'upload-protein.pdb', model_choice: 'auto' }),
      fileList: reactive({ protein_pdb: [makeUploadItem('protein.pdb')] }),
      selectedArtifacts: reactive({}),
      resolvedFiles: {},
      standardInputSlots: computed(() => [{ name: 'protein', type: 'protein_structure@1', required: true }]),
      standardInputFileFieldBindings: computed(() => ({ protein: 'protein_pdb' })),
      selectedStandardArtifacts: reactive({}),
      standardInputFileList: reactive({}),
      executorType: computed(() => 'ssh_job'),
      missingRequiredStandardSlots: computed(() => []),
      api,
      onRequireLogin: vi.fn(),
      onNoSchema: vi.fn(),
      onMissingStandardInputs: vi.fn(),
      onBlocked: vi.fn(),
      onTaskCreated,
    })

    await submission.handleSubmit()

    expect(api.uploadFile).toHaveBeenCalledWith(expect.objectContaining({ name: 'protein.pdb' }))
    expect(api.prepareTaskRun).toHaveBeenCalledWith({
      name: 'Pocket run',
      tool_id: 'tool-lvpocket',
      project_id: 'project-1',
      params: { params: { model_choice: 'auto' } },
      file_ids: undefined,
      standard_input_uploads: { protein: 'file-protein' },
    })
    const preparedPayload = api.prepareTaskRun.mock.calls[0]?.[0]
    expect(preparedPayload).toBeDefined()
    expect(api.createTask).toHaveBeenCalledWith(preparedPayload)
    expect(onTaskCreated).toHaveBeenCalledWith(expect.objectContaining({ id: 'task-created' }))
    expect(submission.submitting.value).toBe(false)
  })
})
