<template>
  <header class="workflow-workbench-header">
    <div class="workflow-workbench-header__main">
      <span class="workflow-workbench-header__kicker">{{ t('workflow.workbenchHeader.kicker') }}</span>
      <h1>{{ workflowName || t('workflow.workbenchHeader.titleFallback') }}</h1>
    </div>

    <a-space class="workflow-workbench-header__metrics" size="small" wrap>
      <a-tag color="blue">{{ t('workflow.statusSummary.ready') }} {{ readyCount }}</a-tag>
      <a-tag color="processing">{{ t('workflow.statusSummary.running') }} {{ runningCount }}</a-tag>
      <a-tag color="green">{{ t('workflow.statusSummary.completed') }} {{ completedCount }}</a-tag>
      <a-tag color="red">{{ t('workflow.statusSummary.failed') }} {{ failedCount }}</a-tag>
    </a-space>

    <div class="workflow-workbench-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  workflowName: string
  readyCount: number
  runningCount: number
  completedCount: number
  failedCount: number
}>()

const { t } = useI18n()
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

.workflow-workbench-header__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: @spacing-xs;
  flex-wrap: wrap;
}

@media (max-width: @screen-md) {
  .workflow-workbench-header {
    grid-template-columns: 1fr;
    align-items: stretch;
  }
}
</style>
