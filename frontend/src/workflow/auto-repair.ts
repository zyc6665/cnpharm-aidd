import type { WorkflowArtifactSemanticType } from './artifact-types'
import type { ArtifactInputSlot, ArtifactOutputSlot } from './contract-bindings'
import type { WorkflowCanvasEdge, WorkflowCanvasNode, WorkflowCanvasPreset } from './canvas-types'
import { normalizeWorkflowSemanticType } from './semantic-types'

export interface WorkflowAutoRepairTool {
  slug: string
  name?: string
  description?: string
  inputSemanticTypes?: readonly WorkflowArtifactSemanticType[]
  outputSemanticTypes?: readonly WorkflowArtifactSemanticType[]
  inputArtifactSlots?: readonly ArtifactInputSlot[]
  outputArtifactSlots?: readonly ArtifactOutputSlot[]
}

export interface WorkflowAutoRepairAction {
  id: string
  sourceEdgeId: string
  sourceNodeId: string
  targetNodeId: string
  inputSlotName: string
  artifactType: WorkflowArtifactSemanticType
  toolSlug: string
  reason: string
  position: { x: number; y: number }
}

export interface WorkflowAutoRepairPlan {
  actions: WorkflowAutoRepairAction[]
  repairableCount: number
}

export function buildWorkflowAutoRepairPlan(input: {
  template: WorkflowCanvasPreset
  tools: readonly WorkflowAutoRepairTool[]
}): WorkflowAutoRepairPlan {
  const nodeById = new Map(input.template.nodes.map(node => [node.id, node]))
  const toolBySlug = new Map(input.tools.map(tool => [tool.slug, tool]))
  const actions: WorkflowAutoRepairAction[] = []
  const plannedKeys = new Set<string>()

  for (const targetNode of input.template.nodes) {
    if (targetNode.type !== 'tool') {
      continue
    }

    for (const slot of targetNode.inputArtifactSlots ?? []) {
      const artifactType = normalizeArtifactType(slot.type)
      const toolSlug = repairToolSlugForSlot(slot)
      if (!artifactType || !toolSlug) {
        continue
      }

      const repairTool = toolBySlug.get(toolSlug)
      if (!repairTool || !toolCanRepairArtifact(repairTool, artifactType)) {
        continue
      }

      if (hasExistingRepairPath(input.template, targetNode.id, artifactType, toolSlug)) {
        continue
      }

      const sourceEdge = findIncomingEdgeForArtifact(input.template.edges, targetNode.id, artifactType)
      if (!sourceEdge) {
        continue
      }

      const sourceNode = nodeById.get(sourceEdge.source)
      const actionKey = `${targetNode.id}:${slot.name}:${artifactType}:${toolSlug}`
      if (plannedKeys.has(actionKey)) {
        continue
      }
      plannedKeys.add(actionKey)

      actions.push({
        id: `repair-${actionKey}`,
        sourceEdgeId: sourceEdge.id,
        sourceNodeId: sourceEdge.source,
        targetNodeId: targetNode.id,
        inputSlotName: slot.name,
        artifactType,
        toolSlug,
        reason: repairReasonForSlot(slot),
        position: repairNodePosition({ sourceNode, targetNode }),
      })
    }
  }

  return { actions, repairableCount: actions.length }
}

function normalizeArtifactType(value?: string | null): WorkflowArtifactSemanticType | null {
  const normalized = normalizeWorkflowSemanticType(String(value ?? '').trim())
  return normalized ? normalized : null
}

function repairToolSlugForSlot(slot: ArtifactInputSlot): string | null {
  if (slot.suggestedPreparationTool) {
    return slot.suggestedPreparationTool
  }

  const artifactType = normalizeArtifactType(slot.type)
  const policy = String(slot.readinessPolicy ?? '')
  const requiredRoles = new Set(slot.requiredRoles ?? [])

  if (
    artifactType === 'protein_structure@1' &&
    (
      policy === 'require_prepared' ||
      policy === 'prefer_prepared_warn_raw' ||
      policy === 'require_receptor' ||
      requiredRoles.has('prepared_pdb') ||
      requiredRoles.has('receptor_pdbqt')
    )
  ) {
    return 'builtin-protein-preparation'
  }

  if (
    artifactType === 'ligand_structure@1' &&
    (policy === 'prefer_3d_ligand' || requiredRoles.has('structure_3d_sdf'))
  ) {
    return 'builtin-rdkit-conformer'
  }

  return null
}

function toolCanRepairArtifact(
  tool: WorkflowAutoRepairTool,
  artifactType: WorkflowArtifactSemanticType,
): boolean {
  return toolAcceptsArtifact(tool, artifactType) && toolProducesArtifact(tool, artifactType)
}

function toolAcceptsArtifact(
  tool: WorkflowAutoRepairTool,
  artifactType: WorkflowArtifactSemanticType,
): boolean {
  return [
    ...(tool.inputArtifactSlots ?? []).map(slot => slot.type),
    ...(tool.inputSemanticTypes ?? []),
  ].map(normalizeWorkflowSemanticType).includes(artifactType)
}

function toolProducesArtifact(
  tool: WorkflowAutoRepairTool,
  artifactType: WorkflowArtifactSemanticType,
): boolean {
  return [
    ...(tool.outputArtifactSlots ?? []).map(slot => slot.type),
    ...(tool.outputSemanticTypes ?? []),
  ].map(normalizeWorkflowSemanticType).includes(artifactType)
}

function hasExistingRepairPath(
  template: WorkflowCanvasPreset,
  targetNodeId: string,
  artifactType: WorkflowArtifactSemanticType,
  toolSlug: string,
): boolean {
  const nodeById = new Map(template.nodes.map(node => [node.id, node]))
  return template.edges.some(edge => {
    if (edge.target !== targetNodeId || normalizeArtifactType(edge.artifactType) !== artifactType) {
      return false
    }
    const sourceNode = nodeById.get(edge.source)
    return Boolean(
      sourceNode &&
      (sourceNode.recommendedToolSlug === toolSlug || sourceNode.toolSlugs?.includes(toolSlug))
    )
  })
}

function findIncomingEdgeForArtifact(
  edges: readonly WorkflowCanvasEdge[],
  targetNodeId: string,
  artifactType: WorkflowArtifactSemanticType,
): WorkflowCanvasEdge | undefined {
  return edges.find(edge => (
    edge.target === targetNodeId && normalizeArtifactType(edge.artifactType) === artifactType
  ))
}

function repairNodePosition(input: {
  sourceNode?: WorkflowCanvasNode
  targetNode: WorkflowCanvasNode
}) {
  if (input.sourceNode) {
    return {
      x: Math.max(0, Math.round((input.sourceNode.position.x + input.targetNode.position.x) / 2)),
      y: Math.max(0, Math.round((input.sourceNode.position.y + input.targetNode.position.y) / 2 + 96)),
    }
  }

  return {
    x: Math.max(0, input.targetNode.position.x - 260),
    y: Math.max(0, input.targetNode.position.y + 96),
  }
}

function repairReasonForSlot(slot: ArtifactInputSlot): string {
  const policy = String(slot.readinessPolicy ?? '')
  if (policy === 'prefer_3d_ligand') {
    return '需要先生成 3D 配体构象'
  }
  if (policy === 'require_receptor') {
    return '需要先生成 receptor_pdbqt'
  }
  return '需要先准备或转换输入产物'
}
