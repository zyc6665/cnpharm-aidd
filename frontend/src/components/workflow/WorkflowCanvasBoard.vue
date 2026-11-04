<template>
  <div
    class="workflow-canvas-board"
    :class="{ 'is-connecting': Boolean(connectingSourceNodeId), 'is-panning': isPanning }"
    :style="boardViewportStyle"
  >
    <div class="canvas-toolbar">
      <div>
        <span class="canvas-kicker">{{ t('workflow.canvas.title') }}</span>
        <h3>{{ presetName }}</h3>
      </div>
      <a-space size="small">
        <a-tag>{{ t('workflow.canvas.nodes', { count: preset.nodes.length }) }}</a-tag>
        <a-tag>{{ t('workflow.canvas.edges', { count: preset.edges.length }) }}</a-tag>
        <a-button size="small" :title="t('workflow.canvas.zoomOut')" @click="zoomOut"><ZoomOutOutlined /></a-button>
        <span class="zoom-value">{{ Math.round(zoom * 100) }}%</span>
        <a-button size="small" :title="t('workflow.canvas.zoomIn')" @click="zoomIn"><ZoomInOutlined /></a-button>
        <a-button
          size="small"
          :title="t('workflow.canvas.resetZoom')"
          :aria-label="t('workflow.canvas.resetZoom')"
          @click="resetZoom"
        >
          <ReloadOutlined />
        </a-button>
        <a-button
          size="small"
          data-testid="canvas-fit-view"
          :title="t('workflow.canvas.fitView')"
          :aria-label="t('workflow.canvas.fitView')"
          @click="fitView"
        >
          <FullscreenOutlined />
        </a-button>
      </a-space>
    </div>

    <div
      ref="viewportRef"
      class="canvas-viewport"
      @pointerdown="handleViewportPointerDown"
      @pointerup="handleViewportPointerUp"
      @pointercancel="handleViewportPointerCancel"
      @pointermove="handleViewportPointerMove"
      @keydown.esc="handleViewportEscape"
      @wheel="handleViewportWheel"
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
          <defs>
            <marker
              id="workflow-edge-arrow"
              markerWidth="10"
              markerHeight="10"
              refX="9"
              refY="5"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(59, 130, 246, 0.58)" />
            </marker>
          </defs>
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
          <WorkflowCanvasEdge
            v-if="connectionPreviewEdge"
            :source="connectionPreviewEdge.source"
            :target="connectionPreviewEdge.target"
            edge-id="connection-preview"
            :label="t('workflow.canvas.connecting')"
            :active="true"
            :preview="true"
            :show-delete="false"
          />
        </svg>

        <WorkflowCanvasPanelNode
          v-for="node in resolvedNodes"
          :key="node.id"
          :node="node"
          :title="resolveCanvasNodeLabel(node.titleKey)"
          :subtitle="node.descriptionKey ? resolveCanvasNodeLabel(node.descriptionKey) : undefined"
          :status="resolvedNodeStatuses[node.id] ?? 'idle'"
          :selected="node.id === activeNodeId"
          :deletable="node.type !== 'input'"
          :scale="zoom"
          @select-node="$emit('select-node', $event)"
          @move-node="$emit('move-node', $event.nodeId, $event.position)"
          @delete-node="$emit('delete-node', $event)"
          @configure-node="$emit('configure-node', $event)"
          @start-connect="handleStartConnect"
          @finish-connect="handleFinishConnect"
        >
          <template #preview>
            <WorkflowNodeInlinePreview
              :selected="node.id === activeNodeId"
              :task="taskByNode?.[node.id] ?? null"
              :artifacts="artifacts ?? []"
            />
          </template>
        </WorkflowCanvasPanelNode>
      </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
  import { FullscreenOutlined, ReloadOutlined, ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons-vue'
  import { useCanvasViewport } from '@/composables/useCanvasViewport'
  import { useI18n } from 'vue-i18n'
  import type { ArtifactFile } from '@/types/models'
  import type { WorkflowArtifactSemanticType, WorkflowStepStatus, WorkflowTaskRef } from '@/workflow/artifact-types'
  import { resolveWorkflowLabel } from '@/workflow/i18n-utils'
  import type { WorkflowCanvasNode as WorkflowCanvasNodeModel, WorkflowCanvasPreset } from '@/workflow/canvas-types'
  import WorkflowCanvasEdge from './WorkflowCanvasEdge.vue'
  import WorkflowCanvasPanelNode from './WorkflowCanvasPanelNode.vue'
  import WorkflowNodeInlinePreview from './WorkflowNodeInlinePreview.vue'

  const NODE_WIDTH = 420
  const NODE_HEIGHT = 340
  const CANVAS_PADDING = 96
  const { t, te } = useI18n()
  const { zoom, zoomIn, zoomOut, resetZoom, setZoom, surfaceStyle } = useCanvasViewport()
  const boardViewportStyle = {
    flex: '1 1 auto',
    width: '100%',
    maxWidth: '100%',
    minWidth: '0',
    height: '100%'
  }

  const props = defineProps<{
    preset: WorkflowCanvasPreset
    activeNodeId?: string | null
    nodeStatuses?: Record<string, WorkflowStepStatus>
    nodePositions?: Record<string, { x: number; y: number }>
    taskByNode?: Record<string, WorkflowTaskRef>
    artifacts?: ArtifactFile[]
  }>()

  const emit = defineEmits<{
    (event: 'select-node', nodeId: string): void
    (event: 'move-node', nodeId: string, position: { x: number; y: number }): void
    (event: 'add-tool-node', input: { toolSlug: string; position: { x: number; y: number } }): void
    (event: 'delete-node', nodeId: string): void
    (event: 'configure-node', nodeId: string): void
    (event: 'delete-edge', edgeId: string): void
    (event: 'add-edge', input: { source: string; target: string; artifactType?: WorkflowArtifactSemanticType }): void
  }>()

  const connectingSourceNodeId = ref<string | null>(null)
  const surfaceRef = ref<HTMLElement | null>(null)
  const viewportRef = ref<HTMLElement | null>(null)
  const connectionCursor = ref({ x: 0, y: 0 })
  const panState = ref<{
    pointerId: number
    startX: number
    startY: number
    startScrollLeft: number
    startScrollTop: number
  } | null>(null)
  const isPanning = computed(() => Boolean(panState.value))

  const presetName = computed(() => resolveWorkflowLabel(props.preset.nameKey, t, te, t('workflow.workbenchHeader.titleFallback')))

  function resolveCanvasNodeLabel(key: unknown): string {
    return resolveWorkflowLabel(key, t, te, t('workflow.canvasNode.titleFallback'))
  }
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
        label: resolveEdgeLabel(edge.artifactType, sourceNode, targetNode, edge.branch),
        active: sourceNode.id === props.activeNodeId || targetNode.id === props.activeNodeId
      }]
    })
  })

  const connectionPreviewEdge = computed(() => {
    if (!connectingSourceNodeId.value) {
      return null
    }

    const sourceNode = nodeById.value[connectingSourceNodeId.value]
    if (!sourceNode) {
      return null
    }

    return {
      source: {
        x: sourceNode.position.x + NODE_WIDTH,
        y: sourceNode.position.y + NODE_HEIGHT / 2,
      },
      target: connectionCursor.value,
    }
  })

  function resolveEdgeLabel(
    artifactType: WorkflowArtifactSemanticType | undefined,
    sourceNode: WorkflowCanvasNodeModel,
    targetNode: WorkflowCanvasNodeModel,
    branch?: 'true' | 'false',
  ) {
    const branchLabel = branch ? t(`workflow.inspector.${branch}Branch`) : ''
    if (!artifactType) {
      return branchLabel || undefined
    }

    const outputSlot = sourceNode.outputArtifactSlots?.find(slot => slot.type === artifactType)
    const inputSlot = targetNode.inputArtifactSlots?.find(slot => slot.type === artifactType)
    if (outputSlot?.name && inputSlot?.name) {
      return [branchLabel, `${outputSlot.name} -> ${inputSlot.name} · ${artifactType}`]
        .filter(Boolean)
        .join(' · ')
    }
    if (inputSlot?.name) {
      return [branchLabel, `${inputSlot.name} · ${artifactType}`].filter(Boolean).join(' · ')
    }
    return [branchLabel, artifactType].filter(Boolean).join(' · ')
  }

  function handleStartConnect(nodeId: string) {
    connectingSourceNodeId.value = nodeId
    const sourceNode = nodeById.value[nodeId]
    if (sourceNode) {
      connectionCursor.value = {
        x: sourceNode.position.x + NODE_WIDTH,
        y: sourceNode.position.y + NODE_HEIGHT / 2,
      }
    }
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

  function isPanTarget(event: PointerEvent) {
    if (!(event.target instanceof Element)) {
      return false
    }

    return !event.target.closest(
      '.workflow-canvas-panel-node, .edge-delete-control, button, input, textarea, select, a, [role="button"]',
    )
  }

  function addPanListeners() {
    if (typeof window === 'undefined') {
      return
    }

    window.addEventListener('pointermove', handlePanPointerMove)
    window.addEventListener('pointerup', handlePanPointerUp)
    window.addEventListener('pointercancel', handlePanPointerCancel)
  }

  function removePanListeners() {
    if (typeof window === 'undefined') {
      return
    }

    window.removeEventListener('pointermove', handlePanPointerMove)
    window.removeEventListener('pointerup', handlePanPointerUp)
    window.removeEventListener('pointercancel', handlePanPointerCancel)
  }

  function handleViewportPointerDown(event: PointerEvent) {
    const viewport = viewportRef.value
    if (
      !viewport
      || event.button !== 0
      || connectingSourceNodeId.value
      || !isPanTarget(event)
    ) {
      return
    }

    stopPan()
    panState.value = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startScrollLeft: viewport.scrollLeft,
      startScrollTop: viewport.scrollTop,
    }
    event.preventDefault()
    addPanListeners()
  }

  function handlePanPointerMove(event: PointerEvent) {
    const viewport = viewportRef.value
    const state = panState.value
    if (!viewport || !state || state.pointerId !== event.pointerId) {
      return
    }

    viewport.scrollLeft = state.startScrollLeft + state.startX - event.clientX
    viewport.scrollTop = state.startScrollTop + state.startY - event.clientY
    event.preventDefault()
  }

  function stopPan(event?: PointerEvent) {
    const state = panState.value
    if (!state || (event && state.pointerId !== event.pointerId)) {
      return
    }

    panState.value = null
    removePanListeners()
  }

  function handlePanPointerUp(event: PointerEvent) {
    stopPan(event)
  }

  function handlePanPointerCancel(event: PointerEvent) {
    stopPan(event)
  }

  function handleViewportPointerUp(event: PointerEvent) {
    cancelConnect()
    stopPan(event)
  }

  function handleViewportPointerCancel(event: PointerEvent) {
    cancelConnect()
    stopPan(event)
  }

  function handleViewportEscape() {
    cancelConnect()
    stopPan()
  }

  function handleViewportWheel(event: WheelEvent) {
    if (!event.ctrlKey && !event.metaKey) {
      return
    }

    event.preventDefault()
    setZoom(zoom.value - event.deltaY * 0.001)
  }

  function handleViewportPointerMove(event: PointerEvent) {
    handleConnectionPointerMove(event)
    handlePanPointerMove(event)
  }

  function handleConnectionPointerMove(event: PointerEvent) {
    if (!connectingSourceNodeId.value || !surfaceRef.value) {
      return
    }

    const rect = surfaceRef.value.getBoundingClientRect()
    connectionCursor.value = {
      x: Math.max(0, (event.clientX - rect.left) / zoom.value),
      y: Math.max(0, (event.clientY - rect.top) / zoom.value),
    }
  }

  function fitView() {
    const viewport = viewportRef.value
    if (!viewport) {
      return
    }

    const availableWidth = viewport.clientWidth - 64
    const availableHeight = viewport.clientHeight - 64
    if (availableWidth <= 0 || availableHeight <= 0) {
      return
    }

    setZoom(Math.min(
      availableWidth / canvasSize.value.width,
      availableHeight / canvasSize.value.height,
    ))
  }

  onMounted(() => {
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(fitView)
    }
  })

  onBeforeUnmount(() => {
    stopPan()
  })

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
    min-height: 560px;
    height: 100%;
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
    position: relative;
    min-height: 0;
    flex: 1;
    overflow: auto;
    cursor: grab;
    touch-action: none;
    overscroll-behavior: contain;
    background-image:
      linear-gradient(rgba(59, 130, 246, 0.06) 1px, transparent 1px),
      linear-gradient(90deg, rgba(59, 130, 246, 0.06) 1px, transparent 1px);
    background-size: 28px 28px;
  }

  .canvas-surface {
    position: relative;
    min-width: 100%;
    min-height: 100%;
  }

  .canvas-stage { position: relative; min-width: 100%; min-height: 100%; }
  .zoom-value { width: 48px; text-align: center; color: @text-secondary; font-size: @font-size-xs; }

  .workflow-canvas-board.is-connecting .canvas-viewport,
  .workflow-canvas-board.is-connecting .canvas-surface {
    cursor: crosshair;
  }

  .workflow-canvas-board.is-panning .canvas-viewport,
  .workflow-canvas-board.is-panning .canvas-surface {
    cursor: grabbing;
    user-select: none;
  }

  .workflow-canvas-board.is-connecting :deep(.node-port-input) {
    border-color: @success-color;
    background: rgba(82, 196, 26, 0.12);
    box-shadow: 0 0 0 4px rgba(82, 196, 26, 0.14);
  }

  @media (max-width: @screen-md) {
    .canvas-toolbar {
      align-items: flex-start;
      flex-direction: column;
    }

    .canvas-toolbar :deep(.ant-space) {
      width: 100%;
      flex-wrap: wrap;
    }
  }

  .canvas-edges {
    position: absolute;
    inset: 0;
  }
</style>
