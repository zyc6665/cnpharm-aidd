<template>
  <p class="result-disclaimer" data-testid="result-disclaimer">
    {{ t('common.disclaimer.resultNotice') }}
  </p>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'

  const { t } = useI18n()
</script>

<style scoped>
  .result-disclaimer {
    margin: 16px 0 0;
    padding: 10px 12px;
    border: 1px solid rgba(245, 158, 11, 0.35);
    border-left: 3px solid #f59e0b;
    border-radius: 4px;
    background: rgba(245, 158, 11, 0.12);
    color: var(--theme-text-secondary, #94a3b8);
    font-size: 12px;
    line-height: 1.6;
  }
</style>
