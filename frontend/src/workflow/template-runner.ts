import type { WorkflowStepStatus } from './artifact-types.ts'
import type { WorkflowTemplate } from './template-types.ts'

export function resolveReadyToolNodeIds(input: {
  template: WorkflowTemplate
  nodeStatuses: Record<string, WorkflowStepStatus>
}): string[] {
  return input.template.nodes
    .filter(node => node.type === 'tool')
    .filter(node => input.nodeStatuses[node.id] === 'ready')
    .map(node => node.id)
}
