import type { WorkflowArtifactSemanticType, WorkflowStepKey } from './artifact-types'
import type { ArtifactInputSlot, ArtifactOutputSlot } from './contract-bindings'

export type WorkflowCanvasPresetKind = 'free' | 'aidd' | 'docking' | 'pocket' | 'screening' | 'dynamics'
export type WorkflowCanvasNodeType = 'input' | 'tool' | 'artifact' | 'result' | 'condition' | 'map' | 'loop'

export interface WorkflowConditionExpression {
  op: '==' | '!=' | '>' | '<' | '>=' | '<=' | 'in' | 'contains'
  left: unknown
  right: unknown
}

export interface WorkflowCanvasPreset {
  id: string
  kind: WorkflowCanvasPresetKind
  nameKey: string
  descriptionKey?: string
  nodes: WorkflowCanvasNode[]
  edges: WorkflowCanvasEdge[]
}

export interface WorkflowCanvasNode {
  id: string
  type: WorkflowCanvasNodeType
  stepKey?: WorkflowStepKey
  toolSlugs?: string[]
  recommendedToolSlug?: string
  titleKey: string
  descriptionKey?: string
  position: { x: number; y: number }
  requiredInputTypes?: WorkflowArtifactSemanticType[]
  producedOutputTypes?: WorkflowArtifactSemanticType[]
  inputArtifactSlots?: ArtifactInputSlot[]
  outputArtifactSlots?: ArtifactOutputSlot[]
  expression?: WorkflowConditionExpression
  over?: string
  max_parallelism?: number
  body?: WorkflowCanvasNode[]
  max_iterations?: number
  convergence_condition?: WorkflowConditionExpression
}

export interface WorkflowCanvasEdge {
  id: string
  source: string
  target: string
  artifactType?: WorkflowArtifactSemanticType
  branch?: 'true' | 'false'
  labelKey?: string
}
