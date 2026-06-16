<template>
  <span class="workflow-node-status-badge" :class="`is-${status}`">
    <span class="status-dot" />
    <span class="status-label">{{ statusLabel }}</span>
  </span>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import type { WorkflowStepStatus } from '@/workflow/artifact-types'

  const props = defineProps<{
    status: WorkflowStepStatus
  }>()

  const statusLabel = computed(() => {
    const labels: Record<WorkflowStepStatus, string> = {
      idle: 'Idle',
      ready: 'Ready',
      running: 'Running',
      completed: 'Done',
      failed: 'Failed',
      invalidated: 'Stale',
      needs_tool_selection: 'Tool'
    }

    return labels[props.status]
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-node-status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-width: 72px;
    height: 24px;
    padding: 0 @spacing-sm;
    border-radius: 999px;
    border: 1px solid @border-color-light;
    background: rgba(255, 255, 255, 0.92);
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    font-weight: 700;
    line-height: 1;
  }

  .status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: @text-color-light-tertiary;
  }

  .is-ready .status-dot {
    background: @info-color;
  }

  .is-running .status-dot {
    background: @warning-color;
    box-shadow: 0 0 0 4px @warning-color-light;
  }

  .is-completed .status-dot {
    background: @success-color;
  }

  .is-failed .status-dot {
    background: @error-color;
  }

  .is-invalidated .status-dot,
  .is-needs_tool_selection .status-dot {
    background: @warning-color;
  }
</style>
