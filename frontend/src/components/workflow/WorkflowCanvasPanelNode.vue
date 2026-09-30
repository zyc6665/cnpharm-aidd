<template>
  <article
    role="group"
    tabindex="0"
    :aria-label="`${title}. ${status}`"
    :aria-grabbed="isDragging"
    class="workflow-canvas-panel-node"
    :class="[`is-${node.type}`, `status-${status}`, { 'is-selected': selected, 'is-dragging': isDragging }]"
    :style="{ left: `${node.position.x}px`, top: `${node.position.y}px` }"
    @click="handleClick"
    @keydown.enter.prevent="$emit('select-node', node.id)"
    @keydown.space.prevent="$emit('select-node', node.id)"
    @keydown="handleKeydown"
    @pointerdown="handlePointerDown"
  >
    <button
      v-if="node.type !== 'input'"
      type="button"
      class="node-port node-port-input"
      :data-node-port="`${node.id}-input`"
      :aria-label="t('workflow.canvasNode.connectTo')"
      @pointerup.stop="$emit('finish-connect', node.id)"
      @pointerdown.stop
    />
    <button
      v-if="node.type !== 'result'"
      type="button"
      class="node-port node-port-output"
      :data-node-port="`${node.id}-output`"
      :aria-label="t('workflow.canvasNode.connectFrom')"
      @pointerdown.stop="$emit('start-connect', node.id)"
    />

    <header class="panel-node-header">
      <div class="panel-node-title-group">
        <span class="panel-node-kind">{{ t('workflow.nodeType.' + node.type) }}</span>
        <h3>{{ title }}</h3>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
      <div class="panel-node-actions">
        <WorkflowNodeStatusBadge :status="status" />
        <button
          v-if="node.type === 'tool'"
          type="button"
          class="panel-node-run-button"
          data-testid="configure-node-button"
          @click.stop="$emit('configure-node', node.id)"
          @pointerdown.stop
        >
          {{ t('workflow.canvasNode.configure') }}
        </button>
        <button
          v-if="deletable"
          type="button"
          class="panel-node-delete-button"
          :aria-label="t('workflow.canvasNode.delete')"
          @click.stop="$emit('delete-node', node.id)"
          @pointerdown.stop
        >
          <DeleteOutlined />
        </button>
      </div>
    </header>

    <section class="panel-node-body">
      <div class="panel-node-summary">
        <slot name="summary">
          <span v-if="node.requiredInputTypes?.length" class="panel-node-chip">
            {{ t('workflow.canvasNode.inputs', { count: node.requiredInputTypes.length }) }}
          </span>
          <span v-if="node.producedOutputTypes?.length" class="panel-node-chip">
            {{ t('workflow.canvasNode.outputs', { count: node.producedOutputTypes.length }) }}
          </span>
          <span v-if="!node.requiredInputTypes?.length && !node.producedOutputTypes?.length" class="panel-node-muted">
            {{ t('workflow.canvasNode.noIo') }}
          </span>
        </slot>
      </div>

      <div class="panel-node-preview">
        <slot name="preview">
          <span class="panel-node-muted">{{ t('workflow.canvasNode.previewHint') }}</span>
        </slot>
      </div>

      <div class="panel-node-outputs">
        <slot name="outputs" />
      </div>
    </section>
  </article>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { DeleteOutlined } from '@ant-design/icons-vue'
import type { WorkflowStepStatus } from '@/workflow/artifact-types'
import type { WorkflowCanvasNode } from '@/workflow/canvas-types'
import WorkflowNodeStatusBadge from './WorkflowNodeStatusBadge.vue'

const props = defineProps<{
  node: WorkflowCanvasNode
  title: string
  subtitle?: string
  status: WorkflowStepStatus
  selected?: boolean
  deletable?: boolean
  scale?: number
}>()

const { t } = useI18n()

const emit = defineEmits<{
  (event: 'select-node', nodeId: string): void
  (event: 'delete-node', nodeId: string): void
  (event: 'start-connect', nodeId: string): void
  (event: 'finish-connect', nodeId: string): void
  (event: 'move-node', payload: { nodeId: string; position: { x: number; y: number } }): void
  (event: 'configure-node', nodeId: string): void
}>()

const isDragging = ref(false)
const suppressClick = ref(false)

function handleKeydown(event: KeyboardEvent) {
  const offsetByKey: Record<string, { x: number; y: number }> = {
    ArrowUp: { x: 0, y: -16 },
    ArrowDown: { x: 0, y: 16 },
    ArrowLeft: { x: -16, y: 0 },
    ArrowRight: { x: 16, y: 0 },
  }
  const offset = offsetByKey[event.key]
  if (!offset) return
  event.preventDefault()
  emit('move-node', {
    nodeId: props.node.id,
    position: { x: props.node.position.x + offset.x, y: props.node.position.y + offset.y },
  })
}

function handleClick() {
  if (suppressClick.value) {
    suppressClick.value = false
    return
  }
  emit('select-node', props.node.id)
}

function handlePointerDown(event: PointerEvent) {
  if (event.button !== 0) {
    return
  }

  const target = event.target
  if (target instanceof HTMLElement && target.closest('button, input, textarea, select, a')) {
    return
  }

  const startX = event.clientX
  const startY = event.clientY
  const startPosition = { ...props.node.position }
  let hasDragged = false
  suppressClick.value = false

  const handlePointerMove = (moveEvent: PointerEvent) => {
    const deltaX = (moveEvent.clientX - startX) / (props.scale || 1)
    const deltaY = (moveEvent.clientY - startY) / (props.scale || 1)
    if (Math.abs(deltaX) > 2 || Math.abs(deltaY) > 2) {
      hasDragged = true
      isDragging.value = true
      suppressClick.value = true
      moveEvent.preventDefault()
    }

    emit('move-node', {
      nodeId: props.node.id,
      position: {
        x: startPosition.x + deltaX,
        y: startPosition.y + deltaY,
      },
    })
  }

  const handlePointerUp = () => {
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', handlePointerUp)
    window.removeEventListener('pointercancel', handlePointerUp)
    isDragging.value = false
    if (hasDragged) {
      event.preventDefault()
    }
  }

  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', handlePointerUp, { once: true })
  window.addEventListener('pointercancel', handlePointerUp, { once: true })
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workflow-canvas-panel-node {
  position: absolute;
  width: 420px;
  height: 340px;
  display: flex;
  flex-direction: column;
  border: 1px solid @accent-color-border;
  border-radius: @border-radius-md;
  background: @bg-elevated;
  box-shadow: @shadow-md;
  color: @text-color-light-primary;
  text-align: left;
  cursor: grab;
  user-select: none;
  touch-action: none;
  transition:
    transform @transition-fast,
    border-color @transition-fast,
    box-shadow @transition-fast;
}

.workflow-canvas-panel-node:hover,
.workflow-canvas-panel-node:focus-visible {
  transform: translateY(-2px);
  border-color: rgba(59, 130, 246, 0.35);
  box-shadow: @shadow-lg;
  outline: none;
}

.workflow-canvas-panel-node:active {
  cursor: grabbing;
}

.workflow-canvas-panel-node.is-selected {
  border-color: @accent-color;
  box-shadow: 0 0 0 3px @accent-color-light, @shadow-lg;
}

.panel-node-header {
  min-height: 76px;
  display: flex;
  justify-content: space-between;
  gap: @spacing-md;
  padding: @spacing-md;
  border-bottom: 1px solid @border-color-light;
}

.panel-node-title-group {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.panel-node-kind {
  color: @text-color-light-tertiary;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

.panel-node-title-group h3 {
  max-width: 100%;
  margin: 0;
  color: @text-color-light-primary;
  font-size: @font-size-md;
  font-weight: 800;
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-node-title-group p {
  margin: 0;
  color: @text-color-light-secondary;
  font-size: @font-size-xs;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.panel-node-actions {
  flex: 0 0 auto;
  display: flex;
  align-items: flex-start;
  gap: @spacing-xs;
}

.panel-node-run-button,
.panel-node-delete-button {
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid @border-color-hover;
  border-radius: @border-radius-sm;
  background: @bg-surface;
  color: @text-color-light-primary;
  font-size: @font-size-xs;
  font-weight: 800;
  cursor: pointer;
}

.panel-node-run-button {
  padding: 0 @spacing-sm;
  border-color: rgba(59, 130, 246, 0.28);
  color: @primary-color;
}

.panel-node-delete-button {
  width: 28px;
  color: @error-color;
}

.panel-node-run-button:hover,
.panel-node-run-button:focus-visible {
  background: @primary-color-light;
  outline: none;
}

.panel-node-delete-button:hover,
.panel-node-delete-button:focus-visible {
  background: @error-color;
  color: #fff;
  outline: none;
}

.panel-node-body {
  min-height: 0;
  flex: 1;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: @spacing-sm;
  padding: @spacing-sm @spacing-md @spacing-md;
}

.panel-node-summary,
.panel-node-outputs {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: @spacing-xs;
  flex-wrap: wrap;
}

.panel-node-preview {
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed @border-color-hover;
  border-radius: @border-radius-sm;
  background: @bg-light-secondary;
  overflow: hidden;
}

.panel-node-chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 @spacing-xs;
  border: 1px solid @border-color-light;
  border-radius: @border-radius-sm;
  background: @bg-surface;
  color: @text-color-light-secondary;
  font-size: @font-size-xs;
  font-weight: 700;
}

.panel-node-muted {
  color: @text-color-light-tertiary;
  font-size: @font-size-xs;
}

.node-port {
  position: absolute;
  top: 50%;
  width: 14px;
  height: 14px;
  padding: 0;
  border: 2px solid @accent-color;
  border-radius: 50%;
  background: @bg-surface;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.12);
  cursor: crosshair;
  transform: translateY(-50%);
  z-index: 2;
}

.node-port:hover,
.node-port:focus-visible {
  background: @accent-color;
  outline: none;
}

.node-port-input {
  left: -8px;
}

.node-port-output {
  right: -8px;
}
</style>
