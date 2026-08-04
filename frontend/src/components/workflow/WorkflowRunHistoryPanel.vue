<template>
  <div class="workflow-run-history-panel">
    <div class="run-history-header">
      <span>{{ t('workflow.canvasPresets.runHistory') }}</span>
      <a-button size="small" :loading="loading" @click="emit('refresh')">
        <template #icon><ReloadOutlined /></template>
        {{ t('workflow.canvasPresets.refreshRuns') }}
      </a-button>
    </div>

    <div v-if="runs.length > 0" class="run-history-list">
      <div
        v-for="run in runs"
        :key="run.id"
        class="run-history-item"
        :class="{ active: run.id === activeRunId }"
        role="button"
        tabindex="0"
        @click="emit('select', run.id)"
        @keydown.enter.prevent="emit('select', run.id)"
        @keydown.space.prevent="emit('select', run.id)"
      >
        <span class="run-history-name">{{ run.name }}</span>
        <a-tag :color="getWorkflowRunStatusTone(run.status)">
          {{ t(`workflow.runStatus.${run.status}`) }}
        </a-tag>
        <span class="run-history-time">{{ formatRunTime(run.created_at) }}</span>
        <a-button
          class="view-workflow-run-detail"
          size="small"
          type="link"
          @click.stop="emit('viewDetail', run.id)"
        >
          {{ t('workflow.canvasPresets.viewRunDetail') }}
        </a-button>
      </div>
    </div>

    <div v-if="runs.length > 0" class="run-history-footer">
      <a-button v-if="hasMore" size="small" :loading="loadingMore" @click="emit('loadMore')">
        {{ t('workflow.canvasPresets.loadMoreRuns') }}
      </a-button>
      <span v-else>{{ t('workflow.canvasPresets.allRunsLoaded') }}</span>
    </div>

    <div v-else class="run-history-empty">
      {{ t('workflow.canvasPresets.emptyRunHistory') }}
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
    viewDetail: [runId: string]
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
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-lg;
    background: @bg-surface;
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
    border: 1px solid @border-color;
    border-radius: @border-radius-base;
    background: @bg-elevated;
    text-align: left;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease;

    &.active,
    &:hover {
      border-color: rgba(59, 130, 246, 0.4);
      background: @accent-color-light;
    }
  }

  .run-history-name {
    color: @text-color-light;
    font-weight: 600;
    overflow-wrap: anywhere;
  }

  .run-history-time {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .view-workflow-run-detail {
    grid-column: 1 / -1;
    justify-self: start;
    padding-inline: 0;
  }

  .run-history-empty {
    padding: @spacing-sm;
    border-radius: @border-radius-base;
    background: @bg-elevated;
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
