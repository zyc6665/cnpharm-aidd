import { ref, unref, type Ref } from 'vue'
import type { UploadFile } from 'ant-design-vue'
import type {
  ArtifactFile,
  FileUploadResponse,
  Tool,
  ToolExample,
  ToolExampleApplyResult,
  ToolExampleFilePreview,
  ToolSchema,
} from '@/types/models'
import type { ApiResponse } from '@/types/api'
import { flattenExampleParams, resolveExampleFileFormKey } from '@/domain/tools'

type MaybeRef<T> = T | Ref<T>

export interface ToolDetailExampleApi {
  getExample: (toolId: string) => Promise<ApiResponse<ToolExample | null>>
  applyExample: (toolId: string) => Promise<ApiResponse<ToolExampleApplyResult>>
  previewFile: (toolId: string, field: string) => Promise<ApiResponse<ToolExampleFilePreview>>
}

export interface ToolDetailExamplesOptions {
  tool: MaybeRef<Tool | null | undefined>
  isLoggedIn: MaybeRef<boolean>
  flattenedSchema: MaybeRef<ToolSchema | undefined>
  formState: Record<string, unknown>
  fileList: Record<string, UploadFile[] | undefined>
  selectedArtifacts: Record<string, ArtifactFile | undefined>
  exampleFiles: Record<string, FileUploadResponse | undefined>
  convertedFiles: Record<string, FileUploadResponse | undefined>
  api: ToolDetailExampleApi
  onRequireLogin: () => void
  onExampleLoaded?: () => void
}

export function useToolDetailExamples(options: ToolDetailExamplesOptions) {
  const example = ref<ToolExample | null>(null)
  const applyingExample = ref(false)
  const previewOpen = ref(false)
  const previewLoading = ref(false)
  const preview = ref<ToolExampleFilePreview | null>(null)
  let exampleRequestId = 0
  let previewRequestId = 0

  async function fetchExample(toolId: string) {
    const requestId = ++exampleRequestId
    example.value = null
    try {
      const res = await options.api.getExample(toolId)
      if (requestId === exampleRequestId && unref(options.tool)?.id === toolId) {
        example.value = res.data
      }
    } catch {
      if (requestId === exampleRequestId) {
        example.value = null
      }
    }
  }

  function applyExampleParams(params: Record<string, unknown>) {
    const schema = unref(options.flattenedSchema)
    if (!schema) {
      return
    }

    const flattenedValues = flattenExampleParams(schema, params)
    Object.entries(flattenedValues).forEach(([key, value]) => {
      options.formState[key] = value
    })
  }

  async function handleUseExample() {
    const currentTool = unref(options.tool)
    if (!currentTool || !example.value) {
      return
    }

    if (!unref(options.isLoggedIn)) {
      options.onRequireLogin()
      return
    }

    applyingExample.value = true
    try {
      const res = await options.api.applyExample(currentTool.id)
      if (unref(options.tool)?.id !== currentTool.id) {
        return
      }
      applyExampleParams(res.data.params)

      Object.entries(res.data.files).forEach(([field, file]) => {
        const formKey = resolveExampleFileFormKey(unref(options.flattenedSchema), field)
        options.exampleFiles[formKey] = file
        options.fileList[formKey] = []
        options.selectedArtifacts[formKey] = undefined
        options.convertedFiles[formKey] = undefined
        options.formState[formKey] = file.id
      })

      options.onExampleLoaded?.()
    } catch {
      // 请求层统一提示错误
    } finally {
      applyingExample.value = false
    }
  }

  async function handlePreviewExampleFile(field: string) {
    const currentTool = unref(options.tool)
    if (!currentTool) {
      return
    }

    const requestId = ++previewRequestId
    previewOpen.value = true
    previewLoading.value = true
    preview.value = null
    try {
      const res = await options.api.previewFile(currentTool.id, field)
      if (requestId === previewRequestId && unref(options.tool)?.id === currentTool.id) {
        preview.value = res.data
      }
    } catch {
      if (requestId === previewRequestId) {
        previewOpen.value = false
      }
    } finally {
      if (requestId === previewRequestId) {
        previewLoading.value = false
      }
    }
  }

  return {
    example,
    applyingExample,
    previewOpen,
    previewLoading,
    preview,
    fetchExample,
    applyExampleParams,
    handleUseExample,
    handlePreviewExampleFile,
  }
}
