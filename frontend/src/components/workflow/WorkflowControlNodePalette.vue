<template>
  <div class="workflow-control-library">
    <span class="rail-kicker">流程控制</span>
    <div class="control-node-actions">
      <button
        v-for="item in controlNodes"
        :key="item.type"
        type="button"
        class="control-node-button"
        :data-testid="`add-${item.type}-node`"
        @click="emit('add-control-node', item.type)"
      >
        <span>{{ item.label }}</span>
        <small>{{ item.description }}</small>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { WorkflowCanvasNodeType } from '@/workflow/canvas-types'

type ControlNodeType = Extract<WorkflowCanvasNodeType, 'condition' | 'map' | 'loop'>

const emit = defineEmits<{
  'add-control-node': [type: ControlNodeType]
}>()

const controlNodes: Array<{ type: ControlNodeType; label: string; description: string }> = [
  { type: 'condition', label: '条件分支', description: '按分数或字段选择路径' },
  { type: 'map', label: '批量处理', description: '并行处理候选集合' },
  { type: 'loop', label: '循环优化', description: '迭代生成与筛选' },
]
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workflow-control-library { display: grid; gap: @spacing-xs; padding: @spacing-sm; border-top: 1px solid @border-color-light; }
.rail-kicker { display: block; margin-bottom: @spacing-xs; color: @text-color-light-tertiary; font-size: @font-size-xs; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.control-node-actions { display: grid; gap: @spacing-xs; }
.control-node-button { display: grid; gap: 2px; padding: @spacing-sm; border: 1px solid @border-color-hover; border-left: 4px solid @warning-color; border-radius: @border-radius-sm; background: @bg-elevated; color: @text-color-light-primary; text-align: left; cursor: pointer; }
.control-node-button:hover,
.control-node-button:focus-visible { border-color: rgba(250, 173, 20, 0.38); background: rgba(250, 173, 20, 0.08); outline: none; }
.control-node-button span { font-size: @font-size-sm; font-weight: 800; }
.control-node-button small { color: @text-color-light-secondary; font-size: @font-size-xs; }
</style>
