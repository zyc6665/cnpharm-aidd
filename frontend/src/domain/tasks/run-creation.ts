import type { Task, TaskCreateParams, TaskRunPreparationPreview } from '@/types/models'
import { taskRunPreparationBlockedMessage } from './run-preparation'

export interface PreparedTaskCreationApi {
  prepareTaskRun: (payload: TaskCreateParams) => Promise<TaskRunPreparationPreview>
  createTask: (payload: TaskCreateParams) => Promise<Task>
}

export interface PreparedTaskCreatedResult {
  status: 'created'
  preview: TaskRunPreparationPreview
  task: Task
}

export interface PreparedTaskBlockedResult {
  status: 'blocked'
  preview: TaskRunPreparationPreview
  message: string
}

export type PreparedTaskCreationResult = PreparedTaskCreatedResult | PreparedTaskBlockedResult

export async function prepareAndCreateTask(
  payload: TaskCreateParams,
  api: PreparedTaskCreationApi,
): Promise<PreparedTaskCreationResult> {
  const preview = await api.prepareTaskRun(payload)
  const blockedMessage = taskRunPreparationBlockedMessage(preview)
  if (blockedMessage) {
    return { status: 'blocked', preview, message: blockedMessage }
  }

  const task = await api.createTask(payload)

  return { status: 'created', preview, task }
}
