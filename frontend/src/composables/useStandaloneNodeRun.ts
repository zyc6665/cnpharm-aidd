import { ref, unref, type Ref } from 'vue'
import type { UploadFile } from 'ant-design-vue'
import { uploadFile } from '@/api/files'
import { createTask, getTaskDetail, isTaskTerminalStatus } from '@/api/tasks'
import { useArtifactsStore, useWorkflowStore } from '@/stores'
import { buildTaskSubmissionPayload } from '@/domain/tools'
import type { ArtifactFile, ToolSchema } from '@/types/models'

interface StandaloneRunTool {
  id: string
  name: string
}

interface ContractArtifactInput {
  name: string
  type: string
  required?: boolean
}

interface UploadedFileRef {
  fileId: string
  filename: string
  downloadUrl: string
}

type MaybeRef<T> = T | Ref<T>

export interface StandaloneNodeRunOptions {
  tool: StandaloneRunTool
  selectedToolSlug: string
  flattenedSchema: ToolSchema
  formState: Record<string, unknown>
  fileList: Record<string, UploadFile[]>
  selectedArtifacts: Record<string, ArtifactFile | undefined>
  executorType?: string
  contractArtifactInputs: ContractArtifactInput[]
}

export function useStandaloneNodeRun(input: {
  nodeId: MaybeRef<string>
  projectId?: MaybeRef<string | null | undefined>
}) {
  const workflowStore = useWorkflowStore()
  const artifactsStore = useArtifactsStore()
  const submitting = ref(false)
  let pollTimer: number | null = null
  let pollTaskId: string | null = null

  function currentNodeId() {
    return unref(input.nodeId)
  }

  function currentProjectId() {
    return unref(input.projectId)?.trim() || undefined
  }

  async function resolveUploadedFiles(options: StandaloneNodeRunOptions) {
    const uploadedFiles: Record<string, UploadedFileRef | undefined> = {}

    for (const [key, artifact] of Object.entries(options.selectedArtifacts)) {
      if (!artifact) {
        continue
      }

      uploadedFiles[key] = {
        fileId: artifact.id,
        filename: artifact.filename,
        downloadUrl: artifact.download_url,
      }
    }

    for (const [key, files] of Object.entries(options.fileList)) {
      const file = files[0]?.originFileObj as File | undefined
      if (!file) {
        continue
      }

      const response = await uploadFile(file)
      const fileId = String(response.data.id)
      uploadedFiles[key] = {
        fileId,
        filename: response.data.filename,
        downloadUrl: response.data.url ?? `/api/v1/files/${fileId}/download`,
      }
    }

    return uploadedFiles
  }

  function withBuiltinInputs(
    params: Record<string, unknown>,
    uploadedFiles: Record<string, UploadedFileRef | undefined>,
    options: StandaloneNodeRunOptions,
  ) {
    if (options.executorType !== 'builtin' || options.contractArtifactInputs.length === 0) {
      return params
    }

    const builtinInputs: Record<string, string> = {}
    const nextParams = { ...params }
    for (const contractInput of options.contractArtifactInputs) {
      delete nextParams[contractInput.name]

      const uploadedFile = uploadedFiles[contractInput.name]
      if (uploadedFile?.fileId) {
        builtinInputs[contractInput.type] = uploadedFile.fileId
      }
    }

    if (Object.keys(builtinInputs).length === 0) {
      return params
    }

    return {
      ...nextParams,
      builtin_inputs: builtinInputs,
    }
  }

  function refreshTaskBindings(
    task: Awaited<ReturnType<typeof getTaskDetail>>['data'],
    selectedToolSlug?: string,
  ) {
    workflowStore.recordNodeTask(currentNodeId(), task)
    if (selectedToolSlug) {
      workflowStore.recordTask(selectedToolSlug, task)
    }
  }

  function stopPolling() {
    if (pollTimer !== null) {
      window.clearTimeout(pollTimer)
      pollTimer = null
    }
    pollTaskId = null
  }

  function startPolling(taskId: string, selectedToolSlug?: string) {
    if (pollTaskId === taskId && pollTimer !== null) {
      return
    }

    stopPolling()
    pollTaskId = taskId

    const poll = async () => {
      try {
        const response = await getTaskDetail(taskId)
        refreshTaskBindings(response.data, selectedToolSlug)

        if (isTaskTerminalStatus(response.data.status)) {
          stopPolling()
          if (response.data.status === 'success') {
            void artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
          }
          return
        }
      } catch {
        // Keep polling through transient network errors so canvas state can recover.
      }

      pollTimer = window.setTimeout(poll, 2000)
    }

    pollTimer = window.setTimeout(poll, 2000)
  }

  async function run(options: StandaloneNodeRunOptions) {
    submitting.value = true
    try {
      const uploadedFiles = await resolveUploadedFiles(options)
      const payload = buildTaskSubmissionPayload({
        flattenedSchema: options.flattenedSchema,
        formState: options.formState,
        uploadedFiles,
        executorType: options.executorType,
      })
      const params = withBuiltinInputs(payload.params, uploadedFiles, options)
      const response = await createTask({
        name: `${options.tool.name} · ${currentNodeId()}`,
        tool_id: options.tool.id,
        project_id: currentProjectId(),
        params,
        file_ids: payload.fileIds.length > 0 ? payload.fileIds : undefined,
      })

      workflowStore.recordNodeTask(currentNodeId(), response.data)
      workflowStore.recordTask(options.selectedToolSlug, response.data)
      startPolling(response.data.id, options.selectedToolSlug)
      return response.data
    } finally {
      submitting.value = false
    }
  }

  return {
    submitting,
    run,
    startPolling,
    stopPolling,
  }
}
