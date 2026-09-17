import { computed, ref, unref, type Ref } from 'vue'
import type { UploadFile } from 'ant-design-vue'
import { uploadFile } from '@/api/files'
import { createTask, getTaskDetail, isTaskTerminalStatus, prepareTaskRun } from '@/api/tasks'
import { useArtifactsStore, useWorkflowStore } from '@/stores'
import {
  buildToolRunTaskPayload,
  type StandardArtifactInputSlot,
} from '@/domain/tools'
import { prepareAndCreateTask, taskRunPreparationBlockedMessage } from '@/domain/tasks'
import type { ArtifactFile, TaskRunPreparationPreview, ToolSchema } from '@/types/models'

interface StandaloneRunTool {
  id: string
  name: string
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
  standardInputSlots: readonly StandardArtifactInputSlot[]
  standardInputFileFieldBindings: Record<string, string>
}

export function useStandaloneNodeRun(input: {
  nodeId: MaybeRef<string>
  projectId?: MaybeRef<string | null | undefined>
}) {
  const workflowStore = useWorkflowStore()
  const artifactsStore = useArtifactsStore()
  const submitting = ref(false)
  const preparationPreview = ref<TaskRunPreparationPreview | null>(null)
  const preparationBlockedReason = computed(() => taskRunPreparationBlockedMessage(preparationPreview.value))
  let pollTimer: number | null = null
  let pollTaskId: string | null = null

  function currentNodeId() {
    return unref(input.nodeId)
  }

  function currentProjectId() {
    return unref(input.projectId)?.trim() || undefined
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
        standardInputSlots: options.standardInputSlots,
        standardInputFileFieldBindings: options.standardInputFileFieldBindings,
        selectedStandardArtifacts: {},
        standardInputFileList: {},
        executorType: options.executorType,
        uploadFile: async file => (await uploadFile(file)).data,
      })

      const taskResult = await prepareAndCreateTask(taskPayload, {
        prepareTaskRun: async payload => (await prepareTaskRun(payload)).data,
        createTask: async payload => (await createTask(payload)).data,
      })
      preparationPreview.value = taskResult.preview
      if (taskResult.status === 'blocked') {
        return undefined
      }

      workflowStore.recordNodeTask(currentNodeId(), taskResult.task)
      workflowStore.recordTask(options.selectedToolSlug, taskResult.task)
      startPolling(taskResult.task.id, options.selectedToolSlug)
      return taskResult.task
    } finally {
      submitting.value = false
    }
  }

  return {
    submitting,
    preparationPreview,
    preparationBlockedReason,
    run,
    startPolling,
    stopPolling,
  }
}
