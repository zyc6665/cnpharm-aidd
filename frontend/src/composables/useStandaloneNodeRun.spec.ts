import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createTask, getTaskDetail, prepareTaskRun } from '@/api/tasks'
import { uploadFile } from '@/api/files'
import { useArtifactsStore, useWorkflowStore } from '@/stores'
import { useStandaloneNodeRun } from './useStandaloneNodeRun'

vi.mock('@/api/files', () => ({
  uploadFile: vi.fn(),
}))

vi.mock('@/api/tasks', () => ({
  createTask: vi.fn(),
  getTaskDetail: vi.fn(),
  prepareTaskRun: vi.fn(),
  isTaskTerminalStatus: (status: string) => ['success', 'failure', 'canceled'].includes(status),
}))

describe('useStandaloneNodeRun', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.mocked(createTask).mockReset()
    vi.mocked(getTaskDetail).mockReset()
    vi.mocked(prepareTaskRun).mockReset()
    vi.mocked(uploadFile).mockReset()
  })

  it('creates a standalone task, binds it to the node, and refreshes terminal status', async () => {
    const workflowStore = useWorkflowStore()
    const artifactsStore = useArtifactsStore()
    const fetchArtifacts = vi.spyOn(artifactsStore, 'fetchArtifacts').mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
      total_pages: 0,
    })
    vi.mocked(prepareTaskRun).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        ready: true,
        project_id: 'project-1',
        tool_id: 'tool-fetch-pdb',
        tool_version_id: 'version-fetch-pdb',
        params: { pdb_id: '1CRN' },
        file_ids: [],
        input_bindings: {},
        requested_input_bindings: {},
        standard_input_uploads: {},
        binding_decisions: {},
        blocked_reason: null,
        resource_snapshot: null,
      },
    } as never)
    vi.mocked(createTask).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        id: 'task-1',
        name: 'Fetch PDB Structure · fetch-pdb-node',
        tool_id: 'tool-fetch-pdb',
        tool_slug: 'builtin-fetch-pdb',
        status: 'pending',
        progress: 0,
        created_at: '2026-08-20T00:00:00Z',
      },
    } as never)
    vi.mocked(getTaskDetail).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        id: 'task-1',
        name: 'Fetch PDB Structure · fetch-pdb-node',
        tool_id: 'tool-fetch-pdb',
        tool_slug: 'builtin-fetch-pdb',
        status: 'success',
        progress: 100,
        created_at: '2026-08-20T00:00:00Z',
        updated_at: '2026-08-20T00:00:02Z',
      },
    } as never)

    const runner = useStandaloneNodeRun({ nodeId: 'fetch-pdb-node', projectId: 'project-1' })
    await runner.run({
      tool: { id: 'tool-fetch-pdb', name: 'Fetch PDB Structure' },
      selectedToolSlug: 'builtin-fetch-pdb',
      flattenedSchema: {
        type: 'object',
        properties: { pdb_id: { type: 'string', title: 'PDB ID' } },
        required: ['pdb_id'],
      },
      formState: { pdb_id: '1CRN' },
      fileList: {},
      selectedArtifacts: {},
      executorType: 'builtin',
      standardInputSlots: [],
      standardInputFileFieldBindings: {},
    })

    expect(prepareTaskRun).toHaveBeenCalledWith({
      name: 'Fetch PDB Structure · fetch-pdb-node',
      tool_id: 'tool-fetch-pdb',
      project_id: 'project-1',
      params: { pdb_id: '1CRN' },
      file_ids: undefined,
    })
    expect(createTask).toHaveBeenCalledWith({
      name: 'Fetch PDB Structure · fetch-pdb-node',
      tool_id: 'tool-fetch-pdb',
      project_id: 'project-1',
      params: { pdb_id: '1CRN' },
      file_ids: undefined,
    })
    expect(workflowStore.taskByNode['fetch-pdb-node']).toMatchObject({ id: 'task-1', status: 'pending' })

    await vi.advanceTimersByTimeAsync(2000)

    expect(getTaskDetail).toHaveBeenCalledWith('task-1')
    expect(workflowStore.taskByNode['fetch-pdb-node']).toMatchObject({ status: 'success' })
    expect(fetchArtifacts).toHaveBeenCalledWith({ page: 1, page_size: 100 })
  })

  it('stops before task creation when backend preparation preview is blocked', async () => {
    vi.mocked(prepareTaskRun).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
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
            selected_role: 'structure_file',
            reason: 'Protein input requires a prepared PDB role.',
          },
        },
        blocked_reason: 'Protein input requires a prepared PDB role.',
        resource_snapshot: null,
      },
    } as never)

    const runner = useStandaloneNodeRun({ nodeId: 'lvpocket-node', projectId: 'project-1' })
    const result = await runner.run({
      tool: { id: 'tool-lvpocket', name: 'LVpocket Pocket Prediction' },
      selectedToolSlug: 'lvpocket-pocket-prediction',
      flattenedSchema: {
        type: 'object',
        properties: {},
        required: [],
      },
      formState: {},
      fileList: {},
      selectedArtifacts: {
        protein: {
          id: 'file-raw',
          filename: 'raw.pdb',
          content_type: 'chemical/x-pdb',
          size_bytes: 1024,
          source_type: 'artifact',
          download_url: '/api/v1/files/file-raw/download',
          task_id: 'task-fetch-pdb',
          tool_id: 'tool-fetch-pdb',
          tool_name: 'Fetch PDB Structure',
          tool_slug: 'builtin-fetch-pdb',
          semantic_type: 'protein_structure@1',
          artifact_version_id: 'artifact-version-raw',
          created_at: '2026-08-20T00:00:00Z',
        },
      },
      executorType: 'ssh_job',
      standardInputSlots: [
        {
          name: 'protein',
          type: 'protein_structure@1',
          required: true,
        },
      ],
      standardInputFileFieldBindings: { protein: 'protein' },
    })

    expect(result).toBeUndefined()
    expect(createTask).not.toHaveBeenCalled()
    expect(runner.preparationPreview.value).toMatchObject({
      ready: false,
      blocked_reason: 'Protein input requires a prepared PDB role.',
      binding_decisions: { protein: { status: 'needs_preparation' } },
    })
  })
})
