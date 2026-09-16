import type { Task, TaskCreateParams, TaskRunPreparationPreview } from '@/types/models'

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

export function taskRunPreparationBlockedMessage(
  preview?: TaskRunPreparationPreview | null,
): string {
  if (!preview || preview.ready) {
    return ''
  }

  const decisionReason = Object.values(preview.binding_decisions ?? {})
    .map(decision => normalizeMessage(decision.reason))
    .find(Boolean)

  return (
    normalizeMessage(preview.blocked_reason) ||
    decisionReason ||
    '标准产物输入尚未满足工具要求'
  )
}

function normalizeMessage(value?: string | null): string {
  return typeof value === 'string' ? value.trim() : ''
}
