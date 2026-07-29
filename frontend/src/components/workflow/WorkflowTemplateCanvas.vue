<template>
  <div class="workflow-template-canvas">
    <div class="canvas-toolbar">
      <div>
        <span class="canvas-kicker">{{ t('workflow.canvas.title') }}</span>
        <h3>{{ templateName }}</h3>
      </div>
      <a-space size="small">
        <a-tag>{{ t('workflow.canvas.nodes', { count: template.nodes.length }) }}</a-tag>
        <a-tag>{{ t('workflow.canvas.edges', { count: template.edges.length }) }}</a-tag>
      </a-space>
    </div>

    <div class="canvas-viewport">
      <div class="canvas-surface" :style="{ width: `${canvasSize.width}px`, height: `${canvasSize.height}px` }">
        <svg
          class="canvas-edges"
          :width="canvasSize.width"
          :height="canvasSize.height"
          role="img"
          :aria-label="t('workflow.canvas.edges', { count: template.edges.length })"
        >
          <WorkflowCanvasEdge
            v-for="edge in resolvedEdges"
            :key="edge.id"
            :source="edge.source"
            :target="edge.target"
            :label="edge.label"
            :active="edge.active"
          />
        </svg>

        <WorkflowCanvasNodeView
          v-for="node in resolvedNodes"
          :key="node.id"
          :node="node"
          :title="resolveLabel(node.titleKey)"
          :subtitle="node.descriptionKey ? resolveLabel(node.descriptionKey) : undefined"
          :status="resolvedNodeStatuses[node.id] ?? 'idle'"
          :selected="node.id === activeNodeId"
          :deletable="node.type !== 'input'"
          @select-node="$emit('select-node', $event)"
          @move-node="$emit('move-node', $event.nodeId, $event.position)"
          @delete-node="$emit('delete-node', $event)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import type { WorkflowStepStatus } from '@/workflow/artifact-types'
  import type { WorkflowCanvasNode as WorkflowCanvasNodeModel, WorkflowTemplate } from '@/workflow/template-types'
  import WorkflowCanvasEdge from './WorkflowCanvasEdge.vue'
  import WorkflowCanvasNodeView from './WorkflowCanvasNode.vue'

  const NODE_WIDTH = 188
  const NODE_HEIGHT = 112
  const CANVAS_PADDING = 64
  const { t, te } = useI18n()

  const props = defineProps<{
    template: WorkflowTemplate
    activeNodeId?: string | null
    nodeStatuses?: Record<string, WorkflowStepStatus>
    nodePositions?: Record<string, { x: number; y: number }>
  }>()

  const emit = defineEmits<{
    (event: 'select-node', nodeId: string): void
    (event: 'move-node', nodeId: string, position: { x: number; y: number }): void
    (event: 'add-tool-node', toolSlug: string): void
    (event: 'delete-node', nodeId: string): void
  }>()

  const templateName = computed(() => resolveLabel(props.template.nameKey))
  const resolvedNodeStatuses = computed(() => props.nodeStatuses ?? {})
  const resolvedNodes = computed(() => {
    return props.template.nodes.map(node => ({
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
    return props.template.edges.flatMap(edge => {
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

  function resolveLabel(key: string): string {
    if (te(key)) {
      return t(key)
    }

    const segments = key.split('.')
    const lastSegment = segments[segments.length - 1] ?? key
    return lastSegment
      .replace(/([A-Z])/g, ' $1')
      .replace(/[-_]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  }

</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-template-canvas {
    min-width: 0;
    display: flex;
    flex-direction: column;
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-md;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(250, 252, 255, 0.94)),
      @bg-light-secondary;
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

  .canvas-edges {
    position: absolute;
    inset: 0;
  }
</style>
