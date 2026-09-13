import { computed } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { UploadFile } from 'ant-design-vue'
import type { TypedArtifact } from '@/types/artifacts'
import { useToolDetailStandardArtifacts } from './useToolDetailStandardArtifacts'

function makeArtifact(id: string, versionId: string): TypedArtifact {
  return {
    id,
    project_id: 'project-1',
    artifact_type: 'protein_structure',
    semantic_type: 'protein_structure@1',
    name: 'target.pdb',
    latest_version: {
      id: versionId,
      version: 1,
      filename: 'target.pdb',
      content_type: 'chemical/x-pdb',
      size_bytes: 123,
      sha256: 'abc',
      status: 'available',
      created_at: '2026-09-13T00:00:00Z',
    },
    created_at: '2026-09-13T00:00:00Z',
    updated_at: '2026-09-13T00:00:00Z',
  }
}

describe('useToolDetailStandardArtifacts', () => {
  it('clears project artifacts when project context or standard slots are missing', async () => {
    const getProjectArtifacts = vi.fn()
    const standardArtifacts = useToolDetailStandardArtifacts({
      projectId: computed(() => undefined),
      standardInputSlots: computed(() => []),
      api: { getProjectArtifacts },
      selectStandardArtifact: vi.fn(),
      updateStandardInputFileList: vi.fn(),
    })
    standardArtifacts.standardProjectArtifacts.value = [makeArtifact('artifact-old', 'version-old')]

    await standardArtifacts.loadStandardProjectArtifacts()

    expect(getProjectArtifacts).not.toHaveBeenCalled()
    expect(standardArtifacts.standardProjectArtifacts.value).toEqual([])
    expect(standardArtifacts.standardArtifactsLoading.value).toBe(false)
  })

  it('loads project artifacts and delegates standard input selection changes', async () => {
    const artifact = makeArtifact('artifact-protein', 'version-protein')
    const getProjectArtifacts = vi.fn().mockResolvedValue({ data: { items: [artifact] } })
    const selectStandardArtifact = vi.fn()
    const updateStandardInputFileList = vi.fn()
    const standardArtifacts = useToolDetailStandardArtifacts({
      projectId: computed(() => 'project-1'),
      standardInputSlots: computed(() => [{ name: 'protein', type: 'protein_structure@1', required: true }]),
      api: { getProjectArtifacts },
      selectStandardArtifact,
      updateStandardInputFileList,
    })
    const files: UploadFile[] = [{ uid: 'upload-protein', name: 'protein.pdb' }]

    await standardArtifacts.loadStandardProjectArtifacts()
    standardArtifacts.handleStandardArtifactSelection('protein', 'version-protein')
    standardArtifacts.handleStandardInputFileListChange('protein', files)

    expect(getProjectArtifacts).toHaveBeenCalledWith('project-1')
    expect(standardArtifacts.standardProjectArtifacts.value).toEqual([artifact])
    expect(standardArtifacts.standardArtifactsLoading.value).toBe(false)
    expect(selectStandardArtifact).toHaveBeenCalledWith('protein', 'version-protein', [artifact])
    expect(updateStandardInputFileList).toHaveBeenCalledWith('protein', files)
  })
})
