import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createTask, getTaskDetail } from '@/api/tasks'
import { uploadFile } from '@/api/files'
import { useArtifactsStore, useWorkflowStore } from '@/stores'
import { useStandaloneNodeRun } from './useStandaloneNodeRun'

vi.mock('@/api/files', () => ({
  uploadFile: vi.fn(),
}))

vi.mock('@/api/tasks', () => ({
  createTask: vi.fn(),
  getTaskDetail: vi.fn(),
  isTaskTerminalStatus: (status: string) => ['success', 'failure', 'canceled'].includes(status),
}))

describe('useStandaloneNodeRun', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.mocked(createTask).mockReset()
    vi.mocked(getTaskDetail).mockReset()
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
      contractArtifactInputs: [],
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
})
