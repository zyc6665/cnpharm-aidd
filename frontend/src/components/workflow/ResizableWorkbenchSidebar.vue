<template>
  <aside
    class="resizable-workbench-sidebar"
    :class="[`is-${side}`, { 'is-collapsed': collapsed }]"
    :style="sidebarStyle"
  >
    <button
      type="button"
      class="sidebar-collapse-toggle"
      data-testid="sidebar-collapse-toggle"
      :aria-label="collapsed ? t('workflow.workbenchSidebar.expand') : t('workflow.workbenchSidebar.collapse')"
      @click="emit('update:collapsed', !collapsed)"
    >
      {{ collapsed ? expandLabel : collapseLabel }}
    </button>

    <div v-show="!collapsed" class="sidebar-content">
      <slot />
    </div>

    <button
      v-if="!collapsed"
      type="button"
      class="sidebar-resize-handle"
      data-testid="sidebar-resize-handle"
      :aria-label="t('workflow.workbenchSidebar.resize')"
      @pointerdown="handlePointerDown"
    />
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const COLLAPSED_WIDTH = 56

const props = defineProps<{
  side: 'left' | 'right'
  width: number
  collapsed: boolean
  minWidth: number
  maxWidth: number
}>()

const emit = defineEmits<{
  'update:width': [width: number]
  'update:collapsed': [collapsed: boolean]
}>()

const { t } = useI18n()

const sidebarStyle = computed(() => ({
  width: `${props.collapsed ? COLLAPSED_WIDTH : props.width}px`,
}))

const collapseLabel = computed(() => (props.side === 'left' ? '‹' : '›'))
const expandLabel = computed(() => (props.side === 'left' ? '›' : '‹'))

function clamp(value: number) {
  return Math.min(props.maxWidth, Math.max(props.minWidth, Math.round(value)))
}

function handlePointerDown(event: PointerEvent) {
  if (event.button !== 0) {
    return
  }

  const startX = event.clientX
  const startWidth = props.width
  const direction = props.side === 'left' ? 1 : -1

  const handleMove = (moveEvent: PointerEvent) => {
    emit('update:width', clamp(startWidth + (moveEvent.clientX - startX) * direction))
  }

  const handleUp = () => {
    window.removeEventListener('pointermove', handleMove)
    window.removeEventListener('pointerup', handleUp)
  }

  window.addEventListener('pointermove', handleMove)
  window.addEventListener('pointerup', handleUp, { once: true })
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.resizable-workbench-sidebar {
  position: relative;
  min-width: 56px;
  height: 100%;
  display: flex;
  flex-direction: column;
  border-color: @border-color-light;
  background: @bg-surface;
  overflow: hidden;
  transition: width @transition-fast;
}

.resizable-workbench-sidebar.is-left {
  border-right: 1px solid @border-color-light;
}

.resizable-workbench-sidebar.is-right {
  border-left: 1px solid @border-color-light;
}

.sidebar-collapse-toggle {
  position: absolute;
  top: @spacing-sm;
  right: @spacing-sm;
  z-index: 3;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid @border-color-hover;
  border-radius: @border-radius-sm;
  background: @bg-elevated;
  color: @text-color-light-secondary;
  font-size: @font-size-md;
  font-weight: 800;
  line-height: 1;
  cursor: pointer;
}

.is-right .sidebar-collapse-toggle {
  right: auto;
  left: @spacing-sm;
}

.sidebar-collapse-toggle:hover,
.sidebar-collapse-toggle:focus-visible {
  border-color: rgba(59, 130, 246, 0.35);
  color: @primary-color;
  outline: none;
}

.sidebar-content {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding-top: 44px;
  overflow: auto;
}

.sidebar-resize-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: col-resize;
}

.is-left .sidebar-resize-handle {
  right: -4px;
}

.is-right .sidebar-resize-handle {
  left: -4px;
}

.sidebar-resize-handle:hover,
.sidebar-resize-handle:focus-visible {
  background: rgba(59, 130, 246, 0.12);
  outline: none;
}
</style>
