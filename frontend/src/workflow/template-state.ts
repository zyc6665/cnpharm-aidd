import type { WorkflowStepStatus, WorkflowTaskRef } from './artifact-types.ts'
import type { WorkflowCanvasNode } from './template-types.ts'
import { mapTaskStatusToWorkflowStepStatus } from './task-state.ts'

export function resolveWorkflowCanvasNodeStatus(input: {
  node: WorkflowCanvasNode
  selectedToolSlug?: string | null
  hasRequiredInputs: boolean
  task?: WorkflowTaskRef | null
}): WorkflowStepStatus {
  if (input.task) {
    return mapTaskStatusToWorkflowStepStatus(input.task.status)
  }

  if (input.node.type === 'tool' && hasMultipleToolOptions(input.node) && !input.selectedToolSlug) {
    return 'needs_tool_selection'
  }

  if (!input.hasRequiredInputs) {
    return 'idle'
  }

  return 'ready'
}

function hasMultipleToolOptions(node: WorkflowCanvasNode): boolean {
  return (node.toolSlugs?.length ?? 0) > 1
}
