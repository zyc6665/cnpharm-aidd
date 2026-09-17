import type { WorkflowArtifactSemanticType } from './artifact-types'
import type { ArtifactInputSlot, ArtifactOutputSlot } from './contract-bindings'
import type { WorkflowCanvasEdge, WorkflowCanvasNode, WorkflowCanvasPreset } from './canvas-types'
import { formatArtifactRole } from './artifact-role-registry'
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
  targetNodeTitle: string
  inputSlotName: string
  artifactType: WorkflowArtifactSemanticType
  toolSlug: string
  toolName: string
  requiredRoles: readonly string[]
  roleLabels: readonly string[]
  reason: string
  position: { x: number; y: number }
}

export interface WorkflowAutoRepairPlan {
  actions: WorkflowAutoRepairAction[]
  repairableCount: number
}

export interface WorkflowAutoRepairReasonInput {
  targetNodeTitle: string
  inputSlotName: string
  toolName: string
  requiredRoleLabels: readonly string[]
}

export interface WorkflowAutoRepairLabels {
  reasonWithRoles: (input: WorkflowAutoRepairReasonInput) => string
  reasonWithoutRoles: (input: WorkflowAutoRepairReasonInput) => string
}

const DEFAULT_WORKFLOW_AUTO_REPAIR_LABELS: WorkflowAutoRepairLabels = {
  reasonWithRoles: input => `${input.targetNodeTitle} ${input.inputSlotName} requires ${input.requiredRoleLabels.join(', ')}; ${input.toolName} can auto-repair it.`,
  reasonWithoutRoles: input => `${input.targetNodeTitle} ${input.inputSlotName} needs preparation or conversion before use; ${input.toolName} can auto-repair it.`,
}

export function buildWorkflowAutoRepairPlan(input: {
  template: WorkflowCanvasPreset
  tools: readonly WorkflowAutoRepairTool[]
  labels?: WorkflowAutoRepairLabels
}): WorkflowAutoRepairPlan {
  const labels = input.labels ?? DEFAULT_WORKFLOW_AUTO_REPAIR_LABELS
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
      if (!artifactType) {
        continue
      }

      const toolSlug = resolveRepairToolSlugForSlot(slot, input.tools)
      if (!toolSlug) {
        continue
      }
      const repairTool = toolBySlug.get(toolSlug)
      if (!repairTool) {
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
      const requiredRoles = desiredRolesForSlot(slot)
      const roleLabels = requiredRoles.map(formatArtifactRole)
      const targetNodeTitle = String(targetNode.titleKey || targetNode.id)
      const toolName = repairTool.name || toolSlug

      actions.push({
        id: `repair-${actionKey}`,
        sourceEdgeId: sourceEdge.id,
        sourceNodeId: sourceEdge.source,
        targetNodeId: targetNode.id,
        targetNodeTitle,
        inputSlotName: slot.name,
        artifactType,
        toolSlug,
        toolName,
        requiredRoles,
        roleLabels,
        reason: repairReasonForSlot({ slot, targetNodeTitle, toolName, requiredRoles, roleLabels, labels }),
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

function resolveRepairToolSlugForSlot(
  slot: ArtifactInputSlot,
  tools: readonly WorkflowAutoRepairTool[],
): string | null {
  const suggestedToolSlug = String(slot.suggestedPreparationTool ?? '').trim()
  const suggestedTool = suggestedToolSlug ? tools.find(tool => tool.slug === suggestedToolSlug) : undefined
  if (suggestedTool && toolCanRepairSlot(suggestedTool, slot, { requireProvidedRoles: false })) {
    return suggestedTool.slug
  }

  const roleAwareTool = tools.find(tool => toolCanRepairSlot(tool, slot, { requireProvidedRoles: true }))
  if (roleAwareTool) {
    return roleAwareTool.slug
  }

  const fallbackToolSlug = fallbackRepairToolSlugForSlot(slot)
  const fallbackTool = fallbackToolSlug ? tools.find(tool => tool.slug === fallbackToolSlug) : undefined
  if (fallbackTool && toolCanRepairSlot(fallbackTool, slot, { requireProvidedRoles: false })) {
    return fallbackTool.slug
  }

  return null
}

function fallbackRepairToolSlugForSlot(slot: ArtifactInputSlot): string | null {
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

function toolCanRepairSlot(
  tool: WorkflowAutoRepairTool,
  slot: ArtifactInputSlot,
  options: { requireProvidedRoles: boolean },
): boolean {
  const artifactType = normalizeArtifactType(slot.type)
  if (!artifactType || !toolAcceptsArtifact(tool, artifactType)) {
    return false
  }
  return toolProducesArtifactForSlot(tool, artifactType, desiredRolesForSlot(slot), options)
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

function toolProducesArtifactForSlot(
  tool: WorkflowAutoRepairTool,
  artifactType: WorkflowArtifactSemanticType,
  desiredRoles: readonly string[],
  options: { requireProvidedRoles: boolean },
): boolean {
  for (const slot of tool.outputArtifactSlots ?? []) {
    if (normalizeWorkflowSemanticType(slot.type) !== artifactType) {
      continue
    }
    if (outputSlotSatisfiesRoles(slot, desiredRoles, options)) {
      return true
    }
  }

  return !options.requireProvidedRoles && (tool.outputSemanticTypes ?? [])
    .map(normalizeWorkflowSemanticType)
    .includes(artifactType)
}

function outputSlotSatisfiesRoles(
  outputSlot: ArtifactOutputSlot,
  desiredRoles: readonly string[],
  options: { requireProvidedRoles: boolean },
): boolean {
  if (desiredRoles.length === 0) {
    return !options.requireProvidedRoles
  }
  const providedRoles = new Set(outputSlot.providedRoles ?? [])
  if (providedRoles.size === 0) {
    return !options.requireProvidedRoles
  }
  return desiredRoles.every(role => providedRoles.has(role))
}

function desiredRolesForSlot(slot: ArtifactInputSlot): readonly string[] {
  const roles = new Set(slot.requiredRoles ?? [])
  const policy = String(slot.readinessPolicy ?? '')

  if (policy === 'require_receptor') {
    roles.add('receptor_pdbqt')
  } else if (policy === 'require_prepared' || policy === 'prefer_prepared_warn_raw') {
    roles.add('prepared_pdb')
  } else if (policy === 'prefer_3d_ligand') {
    roles.add('structure_3d_sdf')
  }

  return [...roles]
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

function repairReasonForSlot(input: {
  slot: ArtifactInputSlot
  targetNodeTitle: string
  toolName: string
  requiredRoles: readonly string[]
  roleLabels: readonly string[]
  labels: WorkflowAutoRepairLabels
}): string {
  const reasonInput: WorkflowAutoRepairReasonInput = {
    targetNodeTitle: input.targetNodeTitle,
    inputSlotName: input.slot.name,
    toolName: input.toolName,
    requiredRoleLabels: input.roleLabels,
  }
  if (input.requiredRoles.length > 0) {
    return input.labels.reasonWithRoles(reasonInput)
  }
  return input.labels.reasonWithoutRoles(reasonInput)
}
