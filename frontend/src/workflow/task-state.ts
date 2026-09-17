import type { Task, TaskStatus } from '@/types/models'
import type { WorkflowStepStatus, WorkflowTaskRef } from './artifact-types.ts'

type WorkflowTaskDrivenStatus = Extract<WorkflowStepStatus, 'running' | 'completed' | 'failed'>

export function mapTaskStatusToWorkflowStepStatus(taskStatus: TaskStatus): WorkflowTaskDrivenStatus {
  switch (taskStatus) {
    case 'pending':
    case 'running':
      return 'running'
    case 'success':
      return 'completed'
    case 'failure':
    case 'canceled':
      return 'failed'
    default:
      return 'failed'
  }
}

export function toWorkflowTaskRef(task: Task | WorkflowTaskRef): WorkflowTaskRef {
  return {
    id: task.id,
    name: task.name,
    tool_id: task.tool_id,
    tool_slug: task.tool_slug,
    status: task.status,
    progress: task.progress,
    progress_message: task.progress_message,
    error_message: task.error_message,
    started_at: task.started_at,
    finished_at: task.finished_at,
    created_at: task.created_at,
    updated_at: task.updated_at,
    output_data: task.output_data,
    output_files: task.output_files,
    binding_decisions: task.binding_decisions
  }
}
