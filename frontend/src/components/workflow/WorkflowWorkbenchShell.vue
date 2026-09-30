<template>
  <section class="workflow-workbench" data-testid="workflow-workbench">
    <WorkflowWorkbenchHeader
      :workflow-name="workflowName"
      :ready-count="readyCount"
      :running-count="runningCount"
      :completed-count="completedCount"
      :failed-count="failedCount"
    >
      <template #actions>
        <slot name="actions" />
      </template>
    </WorkflowWorkbenchHeader>

    <div class="workflow-workbench__body">
      <ResizableWorkbenchSidebar
        side="left"
        :width="leftWidth"
        :collapsed="leftCollapsed"
        :min-width="leftMinWidth"
        :max-width="leftMaxWidth"
        @update:width="$emit('update:leftWidth', $event)"
        @update:collapsed="$emit('update:leftCollapsed', $event)"
      >
        <slot name="left" />
      </ResizableWorkbenchSidebar>

      <main class="workflow-workbench__canvas">
        <slot name="canvas" />
      </main>

      <ResizableWorkbenchSidebar
        side="right"
        :width="rightWidth"
        :collapsed="rightCollapsed"
        :min-width="rightMinWidth"
        :max-width="rightMaxWidth"
        @update:width="$emit('update:rightWidth', $event)"
        @update:collapsed="$emit('update:rightCollapsed', $event)"
      >
        <slot name="right" />
      </ResizableWorkbenchSidebar>
    </div>
  </section>
</template>

<script setup lang="ts">
import ResizableWorkbenchSidebar from './ResizableWorkbenchSidebar.vue'
import WorkflowWorkbenchHeader from './WorkflowWorkbenchHeader.vue'

withDefaults(defineProps<{
  workflowName: string
  readyCount: number
  runningCount: number
  completedCount: number
  failedCount: number
  leftWidth: number
  rightWidth: number
  leftCollapsed: boolean
  rightCollapsed: boolean
  leftMinWidth?: number
  leftMaxWidth?: number
  rightMinWidth?: number
  rightMaxWidth?: number
}>(), {
  leftMinWidth: 280,
  leftMaxWidth: 480,
  rightMinWidth: 320,
  rightMaxWidth: 560,
})

defineEmits<{
  'update:leftWidth': [width: number]
  'update:rightWidth': [width: number]
  'update:leftCollapsed': [collapsed: boolean]
  'update:rightCollapsed': [collapsed: boolean]
}>()
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workflow-workbench {
  height: calc(100vh - @header-height);
  min-height: 720px;
  display: flex;
  flex-direction: column;
  border: 1px solid @border-color-light;
  background: @bg-light;
  overflow: hidden;
}

.workflow-workbench__body {
  min-height: 0;
  flex: 1;
  display: flex;
}

.workflow-workbench__canvas {
  min-width: 0;
  min-height: 0;
  flex: 1;
  display: flex;
  background: @bg-light;
  overflow: hidden;
}

@media (max-width: @screen-md) {
  .workflow-workbench {
    height: auto;
    min-height: calc(100vh - @header-height);
  }

  .workflow-workbench__body {
    min-height: 0;
    display: grid;
    grid-template-rows: auto minmax(560px, 1fr) auto;
    overflow: auto;
  }

  .workflow-workbench__canvas {
    min-height: 560px;
    order: 2;
  }

  .workflow-workbench__body :deep(.resizable-workbench-sidebar) {
    width: 100% !important;
    height: auto;
    min-height: 0;
    max-height: 360px;
  }

  .workflow-workbench__body :deep(.resizable-workbench-sidebar.is-left) {
    order: 1;
  }

  .workflow-workbench__body :deep(.resizable-workbench-sidebar.is-right) {
    order: 3;
  }

  .workflow-workbench__body :deep(.sidebar-content) {
    height: auto;
    max-height: 316px;
  }
}
</style>
