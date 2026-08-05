<template>
  <div class="task-log-preview">
    <div v-if="visibleLogs.length" class="logs-list">
      <div
        v-for="log in visibleLogs"
        :key="String(log.id)"
        class="log-item"
        :class="[`log-${log.level}`]"
      >
        <span class="log-time">{{ formatLogTime(log.timestamp) }}</span>
        <a-tag :color="getLogColor(log.level)" size="small">{{ log.level.toUpperCase() }}</a-tag>
        <span class="log-message">{{ log.message }}</span>
      </div>
    </div>
    <a-empty v-else :description="emptyDescription || t('tasks.noLogs')" />

    <p v-if="hiddenCount > 0" class="log-more">
      {{ t('tasks.moreLogs', { count: hiddenCount }) }}
    </p>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import type { TaskLog } from '@/types/models'
  import {
    formatTaskLogPreviewTime,
    getHiddenTaskLogCount,
    getTaskLogPreviewColor,
    getVisibleTaskLogs,
  } from '@/domain/tasks'

  const props = withDefaults(defineProps<{
    logs: TaskLog[]
    maxItems?: number
    emptyDescription?: string
  }>(), {
    maxItems: 5,
    emptyDescription: ''
  })

  const { t } = useI18n()

  const visibleLogs = computed(() => {
    return getVisibleTaskLogs(props.logs, props.maxItems)
  })

  const hiddenCount = computed(() => {
    return getHiddenTaskLogCount(props.logs, props.maxItems)
  })

  function formatLogTime(time: string) {
    return formatTaskLogPreviewTime(time)
  }

  function getLogColor(level: string) {
    return getTaskLogPreviewColor(level)
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .task-log-preview {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .logs-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .log-item {
    display: flex;
    align-items: flex-start;
    gap: @spacing-sm;
    padding: @spacing-sm @spacing-md;
    border-radius: @border-radius-md;
    background: @bg-hover;
    border: 1px solid #e8edf5;
    font-size: @font-size-sm;

    &.log-warning {
      background: rgba(245, 158, 11, 0.12);
      border-color: rgba(245, 158, 11, 0.25);
    }

    &.log-error {
      background: rgba(239, 68, 68, 0.12);
      border-color: rgba(239, 68, 68, 0.25);
    }
  }

  .log-time {
    flex: none;
    color: @text-color-light-tertiary;
    font-family: @font-family-mono;
    white-space: nowrap;
  }

  .log-message {
    min-width: 0;
    color: @text-color-light-primary;
    line-height: @line-height-base;
    overflow-wrap: anywhere;
  }

  .log-more {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }
</style>
