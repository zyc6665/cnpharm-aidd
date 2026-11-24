<template>
  <a-drawer
    :open="open"
    :title="t('downloads.title')"
    placement="right"
    :width="380"
    @close="emit('update:open', false)"
  >
    <template #extra>
      <a-button
        v-if="hasFinished"
        type="link"
        size="small"
        data-testid="download-tray-clear"
        @click="clearFinished"
      >
        {{ t('downloads.clearFinished') }}
      </a-button>
    </template>

    <p class="download-tray__hint">{{ t('downloads.hint') }}</p>

    <a-empty
      v-if="records.length === 0"
      class="download-tray__empty"
      :description="t('downloads.empty')"
      data-testid="download-tray-empty"
    />

    <ul v-else class="download-tray__list" data-testid="download-tray-list">
      <li
        v-for="record in records"
        :key="record.id"
        class="download-tray__item"
        :class="`is-${record.status}`"
        :data-testid="`download-tray-item-${record.id}`"
      >
        <div class="download-tray__main">
          <div class="download-tray__name" :title="record.filename">
            {{ record.filename }}
          </div>
          <div class="download-tray__meta">
            <a-tag :color="statusColor(record.status)" class="download-tray__status">
              {{ t(`downloads.status.${record.status}`) }}
            </a-tag>
            <span class="download-tray__time">{{ formatTime(record.startedAt) }}</span>
          </div>
          <p v-if="record.error" class="download-tray__error">{{ record.error }}</p>
        </div>
        <div class="download-tray__actions">
          <a-button
            v-if="record.status === 'error' && record.retry"
            type="link"
            size="small"
            data-testid="download-tray-retry"
            @click="handleRetry(record)"
          >
            {{ t('common.retry') }}
          </a-button>
          <a-button
            v-if="record.status !== 'pending'"
            type="text"
            size="small"
            :aria-label="t('common.delete')"
            @click="remove(record.id)"
          >
            ×
          </a-button>
        </div>
      </li>
    </ul>
  </a-drawer>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import { useDownloadHistory, type DownloadRecord, type DownloadStatus } from '@/utils/download-history'

  defineProps<{ open: boolean }>()
  const emit = defineEmits<{ 'update:open': [value: boolean] }>()

  const { t } = useI18n()
  const { records, remove, clearFinished } = useDownloadHistory()

  const hasFinished = computed(() => records.value.some(record => record.status !== 'pending'))

  function statusColor(status: DownloadStatus): string {
    if (status === 'pending') return 'processing'
    if (status === 'done') return 'success'
    return 'error'
  }

  function formatTime(timestamp: number): string {
    const date = new Date(timestamp)
    const hh = String(date.getHours()).padStart(2, '0')
    const mm = String(date.getMinutes()).padStart(2, '0')
    const ss = String(date.getSeconds()).padStart(2, '0')
    return `${hh}:${mm}:${ss}`
  }

  async function handleRetry(record: DownloadRecord): Promise<void> {
    if (!record.retry) return
    remove(record.id)
    try {
      await record.retry()
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : String(cause))
    }
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .download-tray__hint {
    margin: 0 0 @spacing-md;
    color: @text-tertiary;
    font-size: @font-size-xs;
    line-height: 1.5;
  }

  .download-tray__empty {
    margin-top: @spacing-xl;
  }

  .download-tray__list {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .download-tray__item {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: @spacing-sm;
    padding: @spacing-sm @spacing-md;
    border: 1px solid @border-color-split;
    border-radius: @border-radius-md;
    background: @bg-surface;

    &.is-error {
      border-color: fade(@error-color, 40%);
    }
  }

  .download-tray__main {
    flex: 1;
    min-width: 0;
  }

  .download-tray__name {
    overflow: hidden;
    color: @text-primary;
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .download-tray__meta {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
    margin-top: 4px;
  }

  .download-tray__status {
    margin-inline-end: 0;
  }

  .download-tray__time {
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .download-tray__error {
    margin: 4px 0 0;
    color: @error-color;
    font-size: @font-size-xs;
    word-break: break-word;
  }

  .download-tray__actions {
    display: flex;
    align-items: center;
    flex-shrink: 0;
  }
</style>
