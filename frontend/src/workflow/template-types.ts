import type { WorkflowArtifactSemanticType, WorkflowStepKey } from './artifact-types'

export type WorkflowTemplateKind = 'free' | 'aidd' | 'docking' | 'pocket' | 'screening'
export type WorkflowCanvasNodeType = 'input' | 'tool' | 'artifact' | 'result'

export interface WorkflowTemplate {
  id: string
  kind: WorkflowTemplateKind
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
}

export interface WorkflowCanvasEdge {
  id: string
  source: string
  target: string
  artifactType?: WorkflowArtifactSemanticType
  labelKey?: string
}
