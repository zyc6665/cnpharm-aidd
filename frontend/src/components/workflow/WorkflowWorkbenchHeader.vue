<template>
  <header class="workflow-workbench-header">
    <div class="workflow-workbench-header__main">
      <span class="workflow-workbench-header__kicker">工作流工作台</span>
      <h1>{{ workflowName || '未命名工作流' }}</h1>
    </div>

    <a-space class="workflow-workbench-header__metrics" size="small" wrap>
      <a-tag color="blue">可运行 {{ readyCount }}</a-tag>
      <a-tag color="processing">运行中 {{ runningCount }}</a-tag>
      <a-tag color="green">完成 {{ completedCount }}</a-tag>
      <a-tag color="red">失败 {{ failedCount }}</a-tag>
    </a-space>

    <div class="workflow-workbench-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  workflowName: string
  readyCount: number
  runningCount: number
  completedCount: number
  failedCount: number
}>()
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workflow-workbench-header {
  min-height: 56px;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto auto;
  align-items: center;
  gap: @spacing-md;
  padding: @spacing-sm @spacing-md;
  border-bottom: 1px solid @border-color-light;
  background: @bg-surface;
}

.workflow-workbench-header__main {
  min-width: 0;
}

.workflow-workbench-header__kicker {
  display: block;
  color: @text-color-light-tertiary;
  font-size: @font-size-xs;
  font-weight: 800;
  letter-spacing: 0;
}

.workflow-workbench-header h1 {
  margin: 0;
  color: @text-color-light-primary;
  font-size: @font-size-lg;
  font-weight: 800;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-workbench-header__metrics,
.workflow-workbench-header__actions {
  min-width: 0;
}

@media (max-width: @screen-md) {
  .workflow-workbench-header {
    grid-template-columns: 1fr;
    align-items: stretch;
  }
}
</style>
