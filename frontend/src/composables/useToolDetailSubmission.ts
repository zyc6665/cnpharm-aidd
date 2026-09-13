import { ref, unref, type Ref } from 'vue'
import type { UploadFile } from 'ant-design-vue'
import type { TypedArtifact } from '@/types/artifacts'
import type {
  ArtifactFile,
  Task,
  TaskCreateParams,
  TaskRunPreparationPreview,
  ToolSchema,
} from '@/types/models'
import {
  buildToolRunTaskPayload,
  type StandardArtifactInputSlot,
  type ToolRunResolvedFiles,
  type ToolRunUploadFile,
} from '@/domain/tools'
import { taskRunPreparationBlockedMessage } from '@/domain/tasks'

type MaybeRef<T> = T | Ref<T>

export interface ToolDetailSubmissionApi {
  uploadFile: ToolRunUploadFile
  prepareTaskRun: (payload: TaskCreateParams) => Promise<TaskRunPreparationPreview>
  createTask: (payload: TaskCreateParams) => Promise<Task>
}

export interface ToolDetailSubmissionOptions {
  isLoggedIn: MaybeRef<boolean>
  toolId: MaybeRef<string | undefined>
  taskName: MaybeRef<string>
  projectId: MaybeRef<string | undefined>
  flattenedSchema: MaybeRef<ToolSchema | undefined>
  formState: Record<string, unknown>
  fileList: Record<string, UploadFile[] | undefined>
  selectedArtifacts: Record<string, ArtifactFile | undefined>
  resolvedFiles: ToolRunResolvedFiles
  standardInputSlots: MaybeRef<readonly StandardArtifactInputSlot[]>
  standardInputFileFieldBindings: MaybeRef<Record<string, string>>
  selectedStandardArtifacts: Record<string, TypedArtifact | undefined>
  standardInputFileList: Record<string, UploadFile[] | undefined>
  executorType: MaybeRef<string | undefined>
  missingRequiredStandardSlots: MaybeRef<readonly StandardArtifactInputSlot[]>
  api: ToolDetailSubmissionApi
  onRequireLogin: () => void
  onNoSchema: () => void
  onMissingStandardInputs: (slotNames: string[]) => void
  onBlocked: (message: string) => void
  onTaskCreated: (task: Task) => void
}

export function useToolDetailSubmission(options: ToolDetailSubmissionOptions) {
  const submitting = ref(false)

  async function handleSubmit() {
    if (!unref(options.isLoggedIn)) {
      options.onRequireLogin()
      return
    }

    submitting.value = true
    try {
      const schema = unref(options.flattenedSchema)
      const toolId = unref(options.toolId)
      if (!schema || !toolId) {
        options.onNoSchema()
        return
      }

      const missingSlots = unref(options.missingRequiredStandardSlots)
      if (missingSlots.length) {
        options.onMissingStandardInputs(missingSlots.map(slot => slot.name))
        return
      }

      const taskPayload = await buildToolRunTaskPayload({
        toolId,
        taskName: unref(options.taskName),
        projectId: unref(options.projectId),
        flattenedSchema: schema,
        formState: options.formState,
        fileList: options.fileList,
        selectedArtifacts: options.selectedArtifacts,
        resolvedFiles: options.resolvedFiles,
        standardInputSlots: unref(options.standardInputSlots),
        standardInputFileFieldBindings: unref(options.standardInputFileFieldBindings),
        selectedStandardArtifacts: options.selectedStandardArtifacts,
        standardInputFileList: options.standardInputFileList,
        executorType: unref(options.executorType),
        uploadFile: options.api.uploadFile,
      })

      const preparationPreview = await options.api.prepareTaskRun(taskPayload)
      const blockedMessage = taskRunPreparationBlockedMessage(preparationPreview)
      if (blockedMessage) {
        options.onBlocked(blockedMessage)
        return
      }

      const task = await options.api.createTask(taskPayload)
      options.onTaskCreated(task)
    } catch {
      // 请求层统一提示错误
    } finally {
      submitting.value = false
    }
  }

  return {
    submitting,
    handleSubmit,
  }
}
