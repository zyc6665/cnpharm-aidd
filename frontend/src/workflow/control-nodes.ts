import type { WorkflowCanvasNode, WorkflowCanvasNodeType } from './canvas-types'

export type WorkflowControlNodeType = Extract<WorkflowCanvasNodeType, 'condition' | 'map' | 'loop'>
export type AddableWorkflowControlNodeType = Extract<WorkflowControlNodeType, 'condition' | 'map'>

export type WorkflowControlNodeDefaults = Pick<
  WorkflowCanvasNode,
  | 'titleKey'
  | 'descriptionKey'
  | 'expression'
  | 'over'
  | 'max_parallelism'
  | 'body'
  | 'max_iterations'
  | 'convergence_condition'
>

export const ADDABLE_WORKFLOW_CONTROL_NODE_TYPES = [
  'condition',
  'map',
] as const satisfies readonly AddableWorkflowControlNodeType[]

const WORKFLOW_CONTROL_NODE_DEFAULTS: Record<WorkflowControlNodeType, WorkflowControlNodeDefaults> = {
  condition: {
    titleKey: 'workflow.controlNodes.condition.title',
    descriptionKey: 'workflow.controlNodes.condition.description',
    expression: { op: '==', left: true, right: true },
  },
  map: {
    titleKey: 'workflow.controlNodes.map.title',
    descriptionKey: 'workflow.controlNodes.map.description',
    over: 'workflow_input:smiles_csv',
    max_parallelism: 4,
  },
  loop: {
    titleKey: 'workflow.controlNodes.loop.title',
    descriptionKey: 'workflow.controlNodes.loop.description',
    body: [],
    max_iterations: 5,
    convergence_condition: { op: '==', left: true, right: true },
  },
}

export function createWorkflowControlNodeDefaults(
  type: WorkflowControlNodeType,
): WorkflowControlNodeDefaults {
  const defaults = WORKFLOW_CONTROL_NODE_DEFAULTS[type]

  return {
    ...defaults,
    ...(defaults.expression ? { expression: { ...defaults.expression } } : {}),
    ...(defaults.convergence_condition
      ? { convergence_condition: { ...defaults.convergence_condition } }
      : {}),
    ...(defaults.body ? { body: [...defaults.body] } : {}),
  }
}

export function resolveWorkflowControlNodeTitleKey(type: string): string {
  return isWorkflowControlNodeType(type) ? WORKFLOW_CONTROL_NODE_DEFAULTS[type].titleKey : type
}

function isWorkflowControlNodeType(type: string): type is WorkflowControlNodeType {
  return type in WORKFLOW_CONTROL_NODE_DEFAULTS
}
