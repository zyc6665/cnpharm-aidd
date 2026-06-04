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
  import dayjs from 'dayjs'
  import type { TaskLog } from '@/types/models'

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
    if (!props.maxItems || props.maxItems <= 0) {
      return props.logs
    }

    return props.logs.slice(0, props.maxItems)
  })

  const hiddenCount = computed(() => {
    if (!props.maxItems || props.maxItems <= 0) {
      return 0
    }

    return Math.max(props.logs.length - props.maxItems, 0)
  })

  function formatLogTime(time: string) {
    return dayjs(time).format('HH:mm:ss.SSS')
  }

  function getLogColor(level: string) {
    const colors: Record<string, string> = {
      info: 'blue',
      warning: 'orange',
      error: 'red'
    }
    return colors[level] || 'default'
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
    background: #f8fafc;
    border: 1px solid #e8edf5;
    font-size: @font-size-sm;

    &.log-warning {
      background: #fff7e6;
      border-color: #ffe7ba;
    }

    &.log-error {
      background: #fff1f0;
      border-color: #ffccc7;
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
