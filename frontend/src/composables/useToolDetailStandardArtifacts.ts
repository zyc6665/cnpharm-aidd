import { ref, unref, type Ref } from 'vue'
import type { UploadFile } from 'ant-design-vue'
import type { ApiResponse } from '@/types/api'
import type { ArtifactListResponse, TypedArtifact } from '@/types/artifacts'
import type { StandardArtifactInputSlot } from '@/domain/tools'

type MaybeRef<T> = T | Ref<T>

export interface ToolDetailStandardArtifactApi {
  getProjectArtifacts: (projectId: string) => Promise<ApiResponse<ArtifactListResponse>>
}

export interface ToolDetailStandardArtifactsOptions {
  projectId: MaybeRef<string | undefined>
  standardInputSlots: MaybeRef<readonly StandardArtifactInputSlot[]>
  api: ToolDetailStandardArtifactApi
  selectStandardArtifact: (
    slotName: string,
    versionId: string | undefined,
    projectArtifacts: readonly TypedArtifact[],
  ) => void
  updateStandardInputFileList: (slotName: string, files: UploadFile[]) => void
}

export function useToolDetailStandardArtifacts(options: ToolDetailStandardArtifactsOptions) {
  const standardProjectArtifacts = ref<TypedArtifact[]>([])
  const standardArtifactsLoading = ref(false)

  async function loadStandardProjectArtifacts() {
    const projectId = unref(options.projectId)
    if (!projectId || !unref(options.standardInputSlots).length) {
      standardProjectArtifacts.value = []
      return
    }

    standardArtifactsLoading.value = true
    try {
      const res = await options.api.getProjectArtifacts(projectId)
      standardProjectArtifacts.value = res.data.items
    } catch {
      standardProjectArtifacts.value = []
    } finally {
      standardArtifactsLoading.value = false
    }
  }

  function handleStandardArtifactSelection(slotName: string, versionId?: string) {
    options.selectStandardArtifact(slotName, versionId, standardProjectArtifacts.value)
  }

  function handleStandardInputFileListChange(slotName: string, files: UploadFile[]) {
    options.updateStandardInputFileList(slotName, files)
  }

  return {
    standardProjectArtifacts,
    standardArtifactsLoading,
    loadStandardProjectArtifacts,
    handleStandardArtifactSelection,
    handleStandardInputFileListChange,
  }
}
