import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  WORKFLOW_ARTIFACT_SEMANTIC_TYPES,
  type WorkflowArtifactSemanticType
} from '@/workflow/artifact-types'
import type { ArtifactInputSlot, ArtifactOutputSlot } from '@/workflow/contract-bindings'
import type {
  WorkflowCanvasEdge,
  WorkflowCanvasNode,
  WorkflowCanvasNodeType,
  WorkflowCanvasPreset as CanvasWorkflowPreset
} from '@/workflow/canvas-types'
import { normalizeRecord, type WorkflowCanvasPosition } from './workflow-session'

function resolveCanvasEdgeArtifactType(value: unknown): WorkflowCanvasEdge['artifactType'] {
  if (
    typeof value === 'string' &&
    WORKFLOW_ARTIFACT_SEMANTIC_TYPES.includes(value as WorkflowArtifactSemanticType)
  ) {
    return value as WorkflowArtifactSemanticType
  }
  return undefined
}

export const useWorkflowCanvasStore = defineStore(
  'workflow-canvas',
  () => {
    const activeNodeId = ref<string | null>(null)
    const activeGroupId = ref<string | null>(null)
    const nodePositionById = ref<Record<string, WorkflowCanvasPosition>>({})
    const canvasNodes = ref<WorkflowCanvasNode[]>([])
    const canvasEdges = ref<WorkflowCanvasEdge[]>([])
    const hasCanvasOverride = ref(false)

    function normalizeShape() {
      if (activeNodeId.value !== null && typeof activeNodeId.value !== 'string') {
        activeNodeId.value = null
      }
      if (activeGroupId.value !== null && typeof activeGroupId.value !== 'string') {
        activeGroupId.value = null
      }
      nodePositionById.value = normalizeRecord<WorkflowCanvasPosition>(nodePositionById.value)
      canvasNodes.value = Array.isArray(canvasNodes.value) ? canvasNodes.value : []
      canvasEdges.value = Array.isArray(canvasEdges.value) ? canvasEdges.value : []
      if (typeof hasCanvasOverride.value !== 'boolean') {
        hasCanvasOverride.value = canvasNodes.value.length > 0 || canvasEdges.value.length > 0
      }
    }

    function reset() {
      activeNodeId.value = null
      activeGroupId.value = null
      nodePositionById.value = {}
      canvasNodes.value = []
      canvasEdges.value = []
      hasCanvasOverride.value = false
    }

    function setActiveNode(nodeId: string | null) {
      activeNodeId.value = nodeId
    }

    function setActiveGroup(groupId: string | null) {
      activeGroupId.value = groupId
    }

    function moveNode(nodeId: string, position: WorkflowCanvasPosition) {
      const nextPosition = {
        x: Math.max(0, Math.round(position.x)),
        y: Math.max(0, Math.round(position.y))
      }
      nodePositionById.value = {
        ...nodePositionById.value,
        [nodeId]: nextPosition
      }
      canvasNodes.value = canvasNodes.value.map(node =>
        node.id === nodeId ? { ...node, position: nextPosition } : node
      )
    }

    function setNodePositions(positions: Record<string, WorkflowCanvasPosition>) {
      nodePositionById.value = Object.entries(positions).reduce<
        Record<string, WorkflowCanvasPosition>
      >((next, [nodeId, pos]) => {
        next[nodeId] = {
          x: Math.max(0, Math.round(pos.x)),
          y: Math.max(0, Math.round(pos.y))
        }
        return next
      }, {})
    }

    function ensureCanvasFromPreset(preset: CanvasWorkflowPreset) {
      if (hasCanvasOverride.value) return

      canvasNodes.value = preset.nodes.map(node => ({
        ...node,
        position: nodePositionById.value[node.id] ?? node.position
      }))
      canvasEdges.value = preset.edges.map(edge => ({ ...edge }))
      hasCanvasOverride.value = true
      syncNodeSemanticTypes()
    }

    function syncNodeSemanticTypes() {
      const nodeIds = new Set(canvasNodes.value.map(node => node.id))
      canvasEdges.value = canvasEdges.value.filter(
        edge => nodeIds.has(edge.source) && nodeIds.has(edge.target)
      )
    }

    function addNode(input: {
      id: string
      toolSlug: string
      toolName?: string
      toolDescription?: string
      position?: WorkflowCanvasPosition
      requiredInputTypes?: WorkflowArtifactSemanticType[]
      producedOutputTypes?: WorkflowArtifactSemanticType[]
      inputArtifactSlots?: ArtifactInputSlot[]
      outputArtifactSlots?: ArtifactOutputSlot[]
    }): WorkflowCanvasNode {
      const position = input.position ?? {
        x: 320 + canvasNodes.value.length * 32,
        y: 120 + canvasNodes.value.length * 24
      }
      const node: WorkflowCanvasNode = {
        id: input.id,
        type: 'tool',
        toolSlugs: [input.toolSlug],
        recommendedToolSlug: input.toolSlug,
        titleKey: input.toolName || input.toolSlug,
        descriptionKey: input.toolDescription,
        position,
        requiredInputTypes: input.requiredInputTypes ?? [],
        producedOutputTypes: input.producedOutputTypes ?? [],
        inputArtifactSlots: input.inputArtifactSlots ?? [],
        outputArtifactSlots: input.outputArtifactSlots ?? []
      }
      canvasNodes.value = [...canvasNodes.value, node]
      nodePositionById.value = { ...nodePositionById.value, [input.id]: position }
      activeNodeId.value = input.id
      hasCanvasOverride.value = true
      return node
    }

    function addControlNode(input: {
      id: string
      type: Extract<WorkflowCanvasNodeType, 'condition' | 'map' | 'loop'>
      titleKey: string
      descriptionKey?: string
      position?: WorkflowCanvasPosition
      expression?: WorkflowCanvasNode['expression']
      over?: string
      max_parallelism?: number
      body?: WorkflowCanvasNode[]
      max_iterations?: number
      convergence_condition?: WorkflowCanvasNode['convergence_condition']
    }): WorkflowCanvasNode {
      const position = input.position ?? {
        x: 320 + canvasNodes.value.length * 32,
        y: 120 + canvasNodes.value.length * 24
      }
      const node: WorkflowCanvasNode = {
        id: input.id,
        type: input.type,
        titleKey: input.titleKey,
        descriptionKey: input.descriptionKey,
        position,
        expression: input.expression,
        over: input.over,
        max_parallelism: input.max_parallelism,
        body: input.body,
        max_iterations: input.max_iterations,
        convergence_condition: input.convergence_condition
      }
      canvasNodes.value = [...canvasNodes.value, node]
      nodePositionById.value = { ...nodePositionById.value, [input.id]: position }
      activeNodeId.value = input.id
      hasCanvasOverride.value = true
      return node
    }

    function deleteNode(nodeId: string) {
      const node = canvasNodes.value.find(item => item.id === nodeId)
      if (!node || node.type === 'input') return

      canvasNodes.value = canvasNodes.value.filter(item => item.id !== nodeId)
      canvasEdges.value = canvasEdges.value.filter(
        edge => edge.source !== nodeId && edge.target !== nodeId
      )
      syncNodeSemanticTypes()

      const nextPos = { ...nodePositionById.value }
      delete nextPos[nodeId]
      nodePositionById.value = nextPos

      if (activeNodeId.value === nodeId) {
        activeNodeId.value = canvasNodes.value[0]?.id ?? null
      }
    }

    function addEdge(input: {
      source: string
      target: string
      artifactType?: WorkflowCanvasEdge['artifactType']
    }): WorkflowCanvasEdge | null {
      if (input.source === input.target) return null
      if (!canvasNodes.value.some(n => n.id === input.source)) return null
      if (!canvasNodes.value.some(n => n.id === input.target)) return null

      const existing = canvasEdges.value.find(
        e =>
          e.source === input.source &&
          e.target === input.target &&
          e.artifactType === input.artifactType
      )
      if (existing) return existing

      const edge: WorkflowCanvasEdge = {
        id: `edge-${input.source}-${input.target}-${Date.now()}`,
        source: input.source,
        target: input.target,
        artifactType: input.artifactType
      }
      canvasEdges.value = [...canvasEdges.value, edge]
      syncNodeSemanticTypes()
      return edge
    }

    function deleteEdge(edgeId: string) {
      if (!canvasEdges.value.some(e => e.id === edgeId)) return
      canvasEdges.value = canvasEdges.value.filter(e => e.id !== edgeId)
      syncNodeSemanticTypes()
    }

    function exportNodes(nodes: WorkflowCanvasNode[]) {
      const source = hasCanvasOverride.value ? canvasNodes.value : nodes
      return source.map(node => ({
        ...node,
        position: nodePositionById.value[node.id] ?? node.position
      }))
    }

    function exportEdges(edges: WorkflowCanvasEdge[]) {
      return hasCanvasOverride.value ? canvasEdges.value : edges
    }

    function applyDefinition(workflow: {
      nodes: Array<{ id: string; position?: WorkflowCanvasPosition } & Record<string, unknown>>
      edges: Array<{
        id?: string
        source: string
        target: string
        artifactType?: unknown
        source_output?: unknown
        target_input?: unknown
      }>
    }) {
      canvasNodes.value = workflow.nodes.map(node => node as unknown as WorkflowCanvasNode)
      canvasEdges.value = workflow.edges.map((edge, index) => ({
        id: edge.id ?? `edge-${index}`,
        source: edge.source,
        target: edge.target,
        artifactType: resolveCanvasEdgeArtifactType(
          edge.artifactType ?? edge.source_output ?? edge.target_input
        )
      }))
      hasCanvasOverride.value = true
      syncNodeSemanticTypes()
      activeNodeId.value = workflow.nodes[0]?.id ?? null

      setNodePositions(
        workflow.nodes.reduce<Record<string, WorkflowCanvasPosition>>((positions, node) => {
          if (node.position) positions[node.id] = node.position
          return positions
        }, {})
      )
    }

    // Compute a summarized view for persistence compatibility
    const snapshot = computed(() => ({
      activeNodeId: activeNodeId.value,
      activeGroupId: activeGroupId.value,
      nodePositionById: nodePositionById.value,
      canvasNodes: canvasNodes.value,
      canvasEdges: canvasEdges.value,
      hasCanvasOverride: hasCanvasOverride.value
    }))

    return {
      activeNodeId,
      activeGroupId,
      nodePositionById,
      canvasNodes,
      canvasEdges,
      hasCanvasOverride,
      snapshot,
      normalizeShape,
      reset,
      setActiveNode,
      setActiveGroup,
      moveNode,
      setNodePositions,
      ensureCanvasFromPreset,
      syncNodeSemanticTypes,
      addNode,
      addControlNode,
      deleteNode,
      addEdge,
      deleteEdge,
      exportNodes,
      exportEdges,
      applyDefinition
    }
  },
  {
    persist: {
      pick: [
        'activeNodeId',
        'activeGroupId',
        'nodePositionById',
        'canvasNodes',
        'canvasEdges',
        'hasCanvasOverride'
      ]
    }
  }
)
