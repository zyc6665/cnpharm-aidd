<template>
  <div class="workflow-run-history-panel">
    <div class="run-history-header">
      <span>{{ t('workflow.templates.runHistory') }}</span>
      <a-button size="small" :loading="loading" @click="emit('refresh')">
        <template #icon><ReloadOutlined /></template>
        {{ t('workflow.templates.refreshRuns') }}
      </a-button>
    </div>

    <div v-if="runs.length > 0" class="run-history-list">
      <button
        v-for="run in runs"
        :key="run.id"
        class="run-history-item"
        :class="{ active: run.id === activeRunId }"
        type="button"
        @click="emit('select', run.id)"
      >
        <span class="run-history-name">{{ run.name }}</span>
        <a-tag :color="getWorkflowRunStatusTone(run.status)">
          {{ t(`workflow.runStatus.${run.status}`) }}
        </a-tag>
        <span class="run-history-time">{{ formatRunTime(run.created_at) }}</span>
      </button>
    </div>

    <div v-if="runs.length > 0" class="run-history-footer">
      <a-button v-if="hasMore" size="small" :loading="loadingMore" @click="emit('loadMore')">
        {{ t('workflow.templates.loadMoreRuns') }}
      </a-button>
      <span v-else>{{ t('workflow.templates.allRunsLoaded') }}</span>
    </div>

    <div v-else class="run-history-empty">
      {{ t('workflow.templates.emptyRunHistory') }}
    </div>
  </div>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import { ReloadOutlined } from '@ant-design/icons-vue'
  import type { WorkflowRun } from '@/types/models'
  import { getWorkflowRunStatusTone } from '@/workflow/workflow-runs'

  defineProps<{
    runs: WorkflowRun[]
    activeRunId?: string | null
    loading?: boolean
    hasMore?: boolean
    loadingMore?: boolean
  }>()

  const emit = defineEmits<{
    select: [runId: string]
    refresh: []
    loadMore: []
  }>()

  const { t } = useI18n()

  function formatRunTime(value: string): string {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) {
      return value
    }
    return date.toLocaleString()
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-run-history-panel {
    margin: 0 @spacing-md @spacing-lg;
    padding: @spacing-md;
    border: 1px solid rgba(205, 217, 235, 0.9);
    border-radius: @border-radius-lg;
    background: rgba(255, 255, 255, 0.88);
    box-shadow: 0 14px 28px rgb(15 23 42 / 5%);
  }

  .run-history-header {
    display: flex;
    justify-content: space-between;
    gap: @spacing-sm;
    align-items: center;
    margin-bottom: @spacing-sm;
    color: @text-color-light;
    font-weight: 700;
  }

  .run-history-list {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: @spacing-sm;
  }

  .run-history-item {
    min-width: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 4px @spacing-sm;
    align-items: center;
    padding: @spacing-sm;
    border: 1px solid rgba(226, 232, 240, 0.95);
    border-radius: @border-radius-base;
    background: rgba(248, 250, 252, 0.95);
    text-align: left;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease;

    &.active,
    &:hover {
      border-color: rgba(24, 144, 255, 0.55);
      background: rgba(230, 244, 255, 0.78);
    }
  }

  .run-history-name {
    color: @text-color-light;
    font-weight: 600;
    overflow-wrap: anywhere;
  }

  .run-history-time {
    grid-column: 1 / -1;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .run-history-empty {
    padding: @spacing-sm;
    border-radius: @border-radius-base;
    background: rgba(248, 250, 252, 0.95);
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .run-history-footer {
    display: flex;
    justify-content: center;
    margin-top: @spacing-sm;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }
</style>
