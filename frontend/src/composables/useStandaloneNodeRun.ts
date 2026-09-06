import { ref, unref, type Ref } from 'vue'
import type { UploadFile } from 'ant-design-vue'
import { uploadFile } from '@/api/files'
import { createTask, getTaskDetail, isTaskTerminalStatus, prepareTaskRun } from '@/api/tasks'
import { useArtifactsStore, useWorkflowStore } from '@/stores'
import { buildStandardRunTaskExtras, buildTaskSubmissionPayload } from '@/domain/tools'
import type { ArtifactFile, TaskCreateParams, TaskRunPreparationPreview, ToolSchema } from '@/types/models'
import { normalizeWorkflowSemanticType } from '@/workflow/semantic-types'

interface StandaloneRunTool {
  id: string
  name: string
}

interface ContractArtifactInput {
  name: string
  type: string
  required?: boolean
  role_preferences?: string[]
  required_roles?: string[]
  readiness_policy?: string | null
  suggested_preparation_tool?: string | null
}

interface UploadedFileRef {
  fileId: string
  filename: string
  downloadUrl: string
}

interface StandardInputBindingProjection {
  inputBindings: Record<string, string>
  boundArtifactIds: Set<string>
  boundFieldKeys: Set<string>
}

interface StandardInputUploadProjection {
  standardInputUploads: Record<string, string>
  boundFieldKeys: Set<string>
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
  const preparationPreview = ref<TaskRunPreparationPreview | null>(null)
  let pollTimer: number | null = null
  let pollTaskId: string | null = null

  function currentNodeId() {
    return unref(input.nodeId)
  }

  function currentProjectId() {
    return unref(input.projectId)?.trim() || undefined
  }

  function normalizeArtifactType(value?: string | null) {
    return String(normalizeWorkflowSemanticType(String(value ?? '').trim())).trim().toLowerCase()
  }

  function artifactMatchesContractInput(
    fieldKey: string,
    artifact: ArtifactFile,
    contractInput: ContractArtifactInput,
  ) {
    if (fieldKey === contractInput.name) {
      return true
    }

    const artifactType = normalizeArtifactType(artifact.semantic_type)
    const inputType = normalizeArtifactType(contractInput.type)
    return Boolean(artifactType && inputType && artifactType === inputType)
  }

  function buildStandardInputBindings(
    options: StandaloneNodeRunOptions,
  ): StandardInputBindingProjection {
    const inputBindings: Record<string, string> = {}
    const boundArtifactIds = new Set<string>()
    const boundFieldKeys = new Set<string>()

    for (const contractInput of options.contractArtifactInputs) {
      const matchedEntry = Object.entries(options.selectedArtifacts).find(([fieldKey, artifact]) => {
        return Boolean(
          artifact?.artifact_version_id &&
          !boundArtifactIds.has(artifact.id) &&
          artifactMatchesContractInput(fieldKey, artifact, contractInput),
        )
      })

      const [fieldKey, artifact] = matchedEntry ?? []
      if (!fieldKey || !artifact?.artifact_version_id) {
        continue
      }

      inputBindings[contractInput.name] = artifact.artifact_version_id
      boundArtifactIds.add(artifact.id)
      boundFieldKeys.add(fieldKey)
    }

    return { inputBindings, boundArtifactIds, boundFieldKeys }
  }

  function omitBoundArtifactFormValues(
    formState: Record<string, unknown>,
    boundFieldKeys: Set<string>,
  ) {
    if (boundFieldKeys.size === 0) {
      return formState
    }

    const nextState = { ...formState }
    for (const key of boundFieldKeys) {
      delete nextState[key]
    }
    return nextState
  }

  function omitBoundUploadedFiles(
    uploadedFiles: Record<string, UploadedFileRef | undefined>,
    boundFieldKeys: Set<string>,
  ) {
    if (boundFieldKeys.size === 0) {
      return uploadedFiles
    }

    const nextFiles = { ...uploadedFiles }
    for (const key of boundFieldKeys) {
      delete nextFiles[key]
    }
    return nextFiles
  }

  function buildStandardInputUploads(
    options: StandaloneNodeRunOptions,
    uploadedFiles: Record<string, UploadedFileRef | undefined>,
    inputBindings: Record<string, string>,
  ): StandardInputUploadProjection {
    const standardInputUploads: Record<string, string> = {}
    const boundFieldKeys = new Set<string>()

    for (const contractInput of options.contractArtifactInputs) {
      if (inputBindings[contractInput.name]) {
        continue
      }

      const uploadedFile = uploadedFiles[contractInput.name]
      if (!uploadedFile?.fileId) {
        continue
      }

      standardInputUploads[contractInput.name] = uploadedFile.fileId
      boundFieldKeys.add(contractInput.name)
    }

    return { standardInputUploads, boundFieldKeys }
  }

  async function resolveUploadedFiles(
    options: StandaloneNodeRunOptions,
    skipArtifactIds: Set<string> = new Set(),
  ) {
    const uploadedFiles: Record<string, UploadedFileRef | undefined> = {}

    for (const [key, artifact] of Object.entries(options.selectedArtifacts)) {
      if (!artifact) {
        continue
      }

      if (skipArtifactIds.has(artifact.id)) {
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
      const bindingProjection = buildStandardInputBindings(options)
      const uploadedFiles = await resolveUploadedFiles(options, bindingProjection.boundArtifactIds)
      const uploadProjection = buildStandardInputUploads(
        options,
        uploadedFiles,
        bindingProjection.inputBindings,
      )
      const boundFieldKeys = new Set([
        ...bindingProjection.boundFieldKeys,
        ...uploadProjection.boundFieldKeys,
      ])
      const formState = omitBoundArtifactFormValues(options.formState, boundFieldKeys)
      const payload = buildTaskSubmissionPayload({
        flattenedSchema: options.flattenedSchema,
        formState,
        uploadedFiles: omitBoundUploadedFiles(uploadedFiles, uploadProjection.boundFieldKeys),
        executorType: options.executorType,
      })
      const taskPayload: TaskCreateParams = {
        name: `${options.tool.name} · ${currentNodeId()}`,
        tool_id: options.tool.id,
        params: payload.params,
        file_ids: payload.fileIds.length > 0 ? payload.fileIds : undefined,
        ...buildStandardRunTaskExtras({
          projectId: currentProjectId(),
          inputBindings: bindingProjection.inputBindings,
          standardInputUploads: uploadProjection.standardInputUploads,
        }),
      }

      preparationPreview.value = (await prepareTaskRun(taskPayload)).data
      if (!preparationPreview.value.ready) {
        return undefined
      }

      const response = await createTask(taskPayload)

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
    preparationPreview,
    run,
    startPolling,
    stopPolling,
  }
}
