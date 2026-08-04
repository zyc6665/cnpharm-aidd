import type { WorkflowDefinition, WorkflowDefinitionNode } from '../types/models'
import type { WorkflowStepStatus } from './artifact-types.ts'
import type { WorkflowCanvasPreset } from './template-types.ts'

export class WorkflowExecutionOrderError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'WorkflowExecutionOrderError'
  }
}

export type WorkflowDefinitionValidationResult =
  | {
      valid: true
      executionOrder: string[]
      message?: undefined
    }
  | {
      valid: false
      executionOrder: []
      message: string
    }

function isWorkflowDefinition(value: unknown): value is WorkflowDefinition {
  return Boolean(value) && typeof value === 'object' && Array.isArray((value as WorkflowDefinition).nodes)
}

function isExecutableToolNode(node: WorkflowDefinitionNode): boolean {
  return node.kind === 'tool' || node.type === 'tool' || Boolean(node.tool_slug || node.tool_id)
}

function collectDefinitionNodes(definition: WorkflowDefinition): WorkflowDefinitionNode[] {
  const nodes = definition.nodes ?? []
  const nodeIds = nodes.map((node) => node.id)

  if (nodeIds.some((nodeId) => typeof nodeId !== 'string' || !nodeId.trim())) {
    throw new WorkflowExecutionOrderError('Workflow node id is required')
  }

  if (new Set(nodeIds).size !== nodeIds.length) {
    throw new WorkflowExecutionOrderError('Workflow node ids must be unique')
  }

  return nodes
}

function buildDefinitionDependencyMap(definition: WorkflowDefinition): Map<string, Set<string>> {
  const allNodes = collectDefinitionNodes(definition)
  const nodeIds = new Set(allNodes.map((node) => node.id))
  const toolNodes = allNodes.filter(isExecutableToolNode)
  const toolNodeIds = new Set(toolNodes.map((node) => node.id))
  const dependencies = new Map<string, Set<string>>()

  for (const nodeId of toolNodeIds) {
    dependencies.set(nodeId, new Set())
  }

  for (const edge of definition.edges ?? []) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
      throw new WorkflowExecutionOrderError('Workflow edge references unknown node')
    }
    if (!toolNodeIds.has(edge.target) || !toolNodeIds.has(edge.source)) {
      continue
    }
    dependencies.get(edge.target)?.add(edge.source)
  }

  for (const node of toolNodes) {
    for (const source of Object.values(node.semantic_inputs ?? {})) {
      if (typeof source !== 'string' || !source.startsWith('node:')) {
        continue
      }

      const [, sourceNodeId] = source.split(':', 3)
      if (!sourceNodeId || !nodeIds.has(sourceNodeId)) {
        throw new WorkflowExecutionOrderError(
          `Workflow semantic input references unknown node: ${source}`
        )
      }
      if (toolNodeIds.has(sourceNodeId)) {
        dependencies.get(node.id)?.add(sourceNodeId)
      }
    }
  }

  return dependencies
}

function resolveDefinitionExecutionOrder(definition: WorkflowDefinition): string[] {
  const toolNodes = collectDefinitionNodes(definition).filter(isExecutableToolNode)
  const dependencies = buildDefinitionDependencyMap(definition)
  const completed = new Set<string>()
  const executionOrder: string[] = []

  while (executionOrder.length < toolNodes.length) {
    const readyNode = toolNodes.find((node) => {
      if (completed.has(node.id)) {
        return false
      }

      const requiredDependencies = dependencies.get(node.id) ?? new Set<string>()
      return [...requiredDependencies].every((dependencyId) => completed.has(dependencyId))
    })

    if (!readyNode) {
      const unresolvedIds = toolNodes
        .map((node) => node.id)
        .filter((nodeId) => !completed.has(nodeId))
      throw new WorkflowExecutionOrderError(
        `Workflow definition contains a cycle or unresolved dependency: ${unresolvedIds.join(', ')}`
      )
    }

    completed.add(readyNode.id)
    executionOrder.push(readyNode.id)
  }

  return executionOrder
}

export function resolveReadyToolNodeIds(input: {
  template: WorkflowCanvasPreset
  nodeStatuses: Record<string, WorkflowStepStatus>
}): string[] {
  return input.template.nodes
    .filter(node => node.type === 'tool')
    .filter(node => input.nodeStatuses[node.id] === 'ready')
    .map(node => node.id)
}

export function getReadyWorkflowToolNodeIds(
  definition: WorkflowDefinition,
  completedNodeIds: ReadonlySet<string>
): string[] {
  const dependencies = buildDefinitionDependencyMap(definition)

  return collectDefinitionNodes(definition)
    .filter(isExecutableToolNode)
    .filter((node) => {
      if (completedNodeIds.has(node.id)) {
        return false
      }

      const requiredDependencies = dependencies.get(node.id) ?? new Set<string>()
      return [...requiredDependencies].every((dependencyId) => completedNodeIds.has(dependencyId))
    })
    .map((node) => node.id)
}

export function resolveWorkflowExecutionOrder(input: {
  template: WorkflowCanvasPreset
  candidateNodeIds: string[]
}): string[]
export function resolveWorkflowExecutionOrder(input: WorkflowDefinition): string[]
export function resolveWorkflowExecutionOrder(input: {
  template: WorkflowCanvasPreset
  candidateNodeIds: string[]
} | WorkflowDefinition): string[] {
  if (isWorkflowDefinition(input)) {
    return resolveDefinitionExecutionOrder(input)
  }

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

export function validateWorkflowDefinition(
  definition: WorkflowDefinition
): WorkflowDefinitionValidationResult {
  try {
    return {
      valid: true,
      executionOrder: resolveDefinitionExecutionOrder(definition)
    }
  } catch (error) {
    return {
      valid: false,
      executionOrder: [],
      message: error instanceof Error ? error.message : 'Workflow definition is invalid'
    }
  }
}

export function validateWorkflowExecutionOrder(
  definition: WorkflowDefinition
): WorkflowDefinitionValidationResult {
  return validateWorkflowDefinition(definition)
}
