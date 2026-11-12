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
    border-left: 3px solid var(--color-warning-border, #faad14);
    border-radius: 4px;
    background: var(--color-warning-bg, #fffbe6);
    color: var(--color-text-secondary, #595959);
    font-size: 12px;
    line-height: 1.6;
  }
</style>
