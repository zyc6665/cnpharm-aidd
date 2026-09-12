import { ref, unref, type Ref } from 'vue'
import type { UploadFile } from 'ant-design-vue'
import { uploadFile } from '@/api/files'
import { createTask, getTaskDetail, isTaskTerminalStatus, prepareTaskRun } from '@/api/tasks'
import { useArtifactsStore, useWorkflowStore } from '@/stores'
import {
  buildToolRunTaskPayload,
  type StandardArtifactInputSlot,
} from '@/domain/tools'
import type { ArtifactFile, TaskRunPreparationPreview, ToolSchema } from '@/types/models'
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
  standardInputFileFieldBindings?: Record<string, string>
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

  function toStandardInputSlots(inputs: ContractArtifactInput[]): StandardArtifactInputSlot[] {
    return inputs.map(input => ({
      name: input.name,
      type: normalizeArtifactType(input.type) as StandardArtifactInputSlot['type'],
      required: input.required ?? true,
    }))
  }

  function standardInputFileFieldBindings(options: StandaloneNodeRunOptions) {
    if (options.standardInputFileFieldBindings) {
      return options.standardInputFileFieldBindings
    }

    return Object.fromEntries(
      options.contractArtifactInputs.map(input => [input.name, input.name])
    )
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
      const taskPayload = await buildToolRunTaskPayload({
        toolId: options.tool.id,
        taskName: `${options.tool.name} · ${currentNodeId()}`,
        projectId: currentProjectId(),
        flattenedSchema: options.flattenedSchema,
        formState: options.formState,
        fileList: options.fileList,
        selectedArtifacts: options.selectedArtifacts,
        standardInputSlots: toStandardInputSlots(options.contractArtifactInputs),
        standardInputFileFieldBindings: standardInputFileFieldBindings(options),
        selectedStandardArtifacts: {},
        standardInputFileList: {},
        executorType: options.executorType,
        uploadFile: async file => (await uploadFile(file)).data,
      })

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
