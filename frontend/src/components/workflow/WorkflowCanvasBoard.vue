<template>
  <div class="workflow-canvas-board">
    <div class="canvas-toolbar">
      <div>
        <span class="canvas-kicker">{{ t('workflow.canvas.title') }}</span>
        <h3>{{ presetName }}</h3>
      </div>
      <a-space size="small">
        <a-tag>{{ t('workflow.canvas.nodes', { count: preset.nodes.length }) }}</a-tag>
        <a-tag>{{ t('workflow.canvas.edges', { count: preset.edges.length }) }}</a-tag>
        <a-button size="small" title="缩小" @click="zoomOut"><ZoomOutOutlined /></a-button>
        <span class="zoom-value">{{ Math.round(zoom * 100) }}%</span>
        <a-button size="small" title="放大" @click="zoomIn"><ZoomInOutlined /></a-button>
        <a-button size="small" @click="resetZoom">复位</a-button>
      </a-space>
    </div>

    <div
      class="canvas-viewport"
      @pointerup="cancelConnect"
      @wheel.ctrl.prevent="setZoom(zoom - $event.deltaY * 0.001)"
      @dragover.prevent="handleToolDragOver"
      @drop.prevent="handleToolDrop"
    >
      <div class="canvas-stage" :style="{ width: `${canvasSize.width * zoom}px`, height: `${canvasSize.height * zoom}px` }">
      <div ref="surfaceRef" class="canvas-surface" :style="{ width: `${canvasSize.width}px`, height: `${canvasSize.height}px`, ...surfaceStyle }">
        <svg
          class="canvas-edges"
          :width="canvasSize.width"
          :height="canvasSize.height"
          role="img"
          :aria-label="t('workflow.canvas.edges', { count: preset.edges.length })"
        >
          <WorkflowCanvasEdge
            v-for="edge in resolvedEdges"
            :key="edge.id"
            :source="edge.source"
            :target="edge.target"
            :edge-id="edge.id"
            :label="edge.label"
            :active="edge.active"
            @delete-edge="$emit('delete-edge', edge.id)"
          />
        </svg>

        <WorkflowCanvasPanelNode
          v-for="node in resolvedNodes"
          :key="node.id"
          :node="node"
          :title="resolveWorkflowLabel(node.titleKey, t, te)"
          :subtitle="node.descriptionKey ? resolveWorkflowLabel(node.descriptionKey, t, te) : undefined"
          :status="resolvedNodeStatuses[node.id] ?? 'idle'"
          :selected="node.id === activeNodeId"
          :deletable="node.type !== 'input'"
          :scale="zoom"
          @select-node="$emit('select-node', $event)"
          @move-node="$emit('move-node', $event.nodeId, $event.position)"
          @delete-node="$emit('delete-node', $event)"
          @run-node="$emit('run-node', $event)"
          @start-connect="handleStartConnect"
          @finish-connect="handleFinishConnect"
        />
      </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref } from 'vue'
  import { ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons-vue'
  import { useCanvasViewport } from '@/composables/useCanvasViewport'
  import { useI18n } from 'vue-i18n'
  import type { WorkflowArtifactSemanticType, WorkflowStepStatus } from '@/workflow/artifact-types'
  import { resolveWorkflowLabel } from '@/workflow/i18n-utils'
  import type { WorkflowCanvasNode as WorkflowCanvasNodeModel, WorkflowCanvasPreset } from '@/workflow/canvas-types'
  import WorkflowCanvasEdge from './WorkflowCanvasEdge.vue'
  import WorkflowCanvasPanelNode from './WorkflowCanvasPanelNode.vue'

  const NODE_WIDTH = 380
  const NODE_HEIGHT = 280
  const CANVAS_PADDING = 96
  const { t, te } = useI18n()
  const { zoom, zoomIn, zoomOut, resetZoom, setZoom, surfaceStyle } = useCanvasViewport()

  const props = defineProps<{
    preset: WorkflowCanvasPreset
    activeNodeId?: string | null
    nodeStatuses?: Record<string, WorkflowStepStatus>
    nodePositions?: Record<string, { x: number; y: number }>
  }>()

  const emit = defineEmits<{
    (event: 'select-node', nodeId: string): void
    (event: 'move-node', nodeId: string, position: { x: number; y: number }): void
    (event: 'add-tool-node', input: { toolSlug: string; position: { x: number; y: number } }): void
    (event: 'delete-node', nodeId: string): void
    (event: 'run-node', nodeId: string): void
    (event: 'delete-edge', edgeId: string): void
    (event: 'add-edge', input: { source: string; target: string; artifactType?: WorkflowArtifactSemanticType }): void
  }>()

  const connectingSourceNodeId = ref<string | null>(null)
  const surfaceRef = ref<HTMLElement | null>(null)

  const presetName = computed(() => resolveWorkflowLabel(props.preset.nameKey, t, te))
  const resolvedNodeStatuses = computed(() => props.nodeStatuses ?? {})
  const resolvedNodes = computed(() => {
    return props.preset.nodes.map(node => ({
      ...node,
      position: props.nodePositions?.[node.id] ?? node.position
    }))
  })

  const canvasSize = computed(() => {
    const maxX = Math.max(...resolvedNodes.value.map(node => node.position.x), 0)
    const maxY = Math.max(...resolvedNodes.value.map(node => node.position.y), 0)

    return {
      width: maxX + NODE_WIDTH + CANVAS_PADDING,
      height: maxY + NODE_HEIGHT + CANVAS_PADDING
    }
  })

  const nodeById = computed(() => {
    return resolvedNodes.value.reduce<Record<string, WorkflowCanvasNodeModel>>((nodes, node) => {
      nodes[node.id] = node
      return nodes
    }, {})
  })

  const resolvedEdges = computed(() => {
    return props.preset.edges.flatMap(edge => {
      const sourceNode = nodeById.value[edge.source]
      const targetNode = nodeById.value[edge.target]

      if (!sourceNode || !targetNode) {
        return []
      }

      return [{
        id: edge.id,
        source: {
          x: sourceNode.position.x + NODE_WIDTH,
          y: sourceNode.position.y + NODE_HEIGHT / 2
        },
        target: {
          x: targetNode.position.x,
          y: targetNode.position.y + NODE_HEIGHT / 2
        },
        label: edge.artifactType,
        active: sourceNode.id === props.activeNodeId || targetNode.id === props.activeNodeId
      }]
    })
  })

  function handleStartConnect(nodeId: string) {
    connectingSourceNodeId.value = nodeId
  }

  function handleFinishConnect(targetNodeId: string) {
    const sourceNodeId = connectingSourceNodeId.value
    connectingSourceNodeId.value = null
    if (!sourceNodeId || sourceNodeId === targetNodeId) {
      return
    }

    const sourceNode = nodeById.value[sourceNodeId]
    const targetNode = nodeById.value[targetNodeId]
    if (!sourceNode || !targetNode) {
      return
    }

    emit('add-edge', {
      source: sourceNodeId,
      target: targetNodeId,
      artifactType: resolveCompatibleArtifactType(sourceNode, targetNode),
    })
  }

  function cancelConnect() {
    connectingSourceNodeId.value = null
  }

  function handleToolDragOver(event: DragEvent) {
    if (!event.dataTransfer) {
      return
    }

    event.dataTransfer.dropEffect = 'copy'
  }

  function handleToolDrop(event: DragEvent) {
    const toolSlug = event.dataTransfer?.getData('application/x-workflow-tool')
      || event.dataTransfer?.getData('text/plain')
    const surface = surfaceRef.value
    if (!toolSlug || !surface) {
      return
    }

    const rect = surface.getBoundingClientRect()
    emit('add-tool-node', {
      toolSlug,
      position: {
        x: Math.max(0, Math.round((event.clientX - rect.left) / zoom.value)),
        y: Math.max(0, Math.round((event.clientY - rect.top) / zoom.value)),
      },
    })
  }

  function resolveCompatibleArtifactType(
    sourceNode: WorkflowCanvasNodeModel,
    targetNode: WorkflowCanvasNodeModel,
  ): WorkflowArtifactSemanticType | undefined {
    const sourceOutputs = sourceNode.producedOutputTypes ?? []
    const targetInputs = targetNode.requiredInputTypes ?? []
    return targetInputs.find((semanticType) => sourceOutputs.includes(semanticType))
      ?? sourceOutputs[0]
      ?? targetInputs[0]
  }

</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-canvas-board {
    min-width: 0;
    display: flex;
    flex-direction: column;
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-md;
    background: @bg-surface;
    box-shadow: @shadow-sm;
    overflow: hidden;
  }

  .canvas-toolbar {
    min-height: 72px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    padding: @spacing-md @spacing-lg;
    border-bottom: 1px solid @border-color-light;
  }

  .canvas-toolbar h3 {
    margin: 2px 0 0;
    color: @text-color-light-primary;
    font-size: @font-size-lg;
    font-weight: 800;
  }

  .canvas-kicker {
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 800;
    letter-spacing: 0;
    text-transform: uppercase;
  }

  .canvas-viewport {
    min-height: 560px;
    overflow: auto;
    background-image:
      linear-gradient(rgba(59, 130, 246, 0.06) 1px, transparent 1px),
      linear-gradient(90deg, rgba(59, 130, 246, 0.06) 1px, transparent 1px);
    background-size: 28px 28px;
  }

  .canvas-surface {
    position: relative;
    min-width: 100%;
    min-height: 560px;
  }

  .canvas-stage { position: relative; min-width: 100%; min-height: 560px; }
  .zoom-value { width: 48px; text-align: center; color: @text-secondary; font-size: @font-size-xs; }

  .canvas-edges {
    position: absolute;
    inset: 0;
  }
</style>
