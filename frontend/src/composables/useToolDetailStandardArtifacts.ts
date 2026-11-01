import { ref, unref, type Ref } from 'vue'
import type { UploadFile } from 'ant-design-vue'
import type { ApiResponse } from '@/types/api'
import type { ArtifactListResponse, TypedArtifact } from '@/types/artifacts'
import type { StandardArtifactInputSlot } from '@/domain/tools'

type MaybeRef<T> = T | Ref<T>

export interface ToolDetailStandardArtifactApi {
  getAllProjectArtifacts: (projectId: string) => Promise<ApiResponse<ArtifactListResponse>>
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
  let requestId = 0

  async function loadStandardProjectArtifacts() {
    const currentRequestId = ++requestId
    const projectId = unref(options.projectId)
    if (!projectId || !unref(options.standardInputSlots).length) {
      standardProjectArtifacts.value = []
      standardArtifactsLoading.value = false
      return
    }

    standardArtifactsLoading.value = true
    try {
      const res = await options.api.getAllProjectArtifacts(projectId)
      if (currentRequestId === requestId) {
        standardProjectArtifacts.value = res.data.items
      }
    } catch {
      if (currentRequestId === requestId) {
        standardProjectArtifacts.value = []
      }
    } finally {
      if (currentRequestId === requestId) {
        standardArtifactsLoading.value = false
      }
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
