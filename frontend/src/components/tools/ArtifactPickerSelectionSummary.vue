<template>
  <div class="artifact-selection-summary">
    <div class="artifact-selection-summary-copy">
      <span class="artifact-selection-summary-label">{{ label }}</span>
      <strong class="artifact-selection-summary-title">{{ title }}</strong>
      <p class="artifact-selection-summary-meta">{{ meta }}</p>
    </div>
    <a-button
      v-if="showClear"
      type="link"
      size="small"
      class="artifact-selection-summary-action"
      @click="emit('clear')"
    >
      {{ t('tools.clearArtifactSelection') }}
    </a-button>
  </div>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'

  defineProps<{
    label: string
    title: string
    meta: string
    showClear: boolean
  }>()

  const emit = defineEmits<{
    clear: []
  }>()

  const { t } = useI18n()
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .artifact-selection-summary {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: @spacing-sm;
    padding: @spacing-md;
    border: 1px dashed #d8e1ee;
    border-radius: @border-radius-md;
    background: @accent-color-light;
  }

  .artifact-selection-summary-copy {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    min-width: 0;
  }

  .artifact-selection-summary-label {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .artifact-selection-summary-title {
    overflow: hidden;
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .artifact-selection-summary-meta {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: @line-height-base;
    overflow-wrap: anywhere;
  }

  .artifact-selection-summary-action {
    padding-inline: 0;
  }
</style>
