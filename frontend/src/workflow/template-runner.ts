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

export function resolveWorkflowExecutionOrder(input: {
  template: WorkflowTemplate
  candidateNodeIds: string[]
}): string[] {
  const candidateIds = new Set(input.candidateNodeIds)
  const nodeOrder = new Map(input.template.nodes.map((node, index) => [node.id, index]))
  const dependencyByNode = new Map<string, Set<string>>()

  for (const nodeId of candidateIds) {
    dependencyByNode.set(nodeId, new Set())
  }

  for (const edge of input.template.edges) {
    if (!candidateIds.has(edge.source) || !candidateIds.has(edge.target)) {
      continue
    }

    dependencyByNode.get(edge.target)?.add(edge.source)
  }

  const ordered: string[] = []
  const remaining = new Set(candidateIds)

  while (remaining.size > 0) {
    const runnable = Array.from(remaining)
      .filter(nodeId => {
        const dependencies = dependencyByNode.get(nodeId) ?? new Set()
        return Array.from(dependencies).every(dependencyId => ordered.includes(dependencyId))
      })
      .sort((left, right) => (nodeOrder.get(left) ?? 0) - (nodeOrder.get(right) ?? 0))

    if (runnable.length === 0) {
      return [
        ...ordered,
        ...Array.from(remaining).sort((left, right) => (nodeOrder.get(left) ?? 0) - (nodeOrder.get(right) ?? 0))
      ]
    }

    for (const nodeId of runnable) {
      ordered.push(nodeId)
      remaining.delete(nodeId)
    }
  }

  return ordered
}
