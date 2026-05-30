<template>
  <AppErrorState
    code="403"
    :title="t('error.forbidden')"
    :description="t('error.403.description')"
    :action-text="t('error.backHome')"
  />
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import AppErrorState from '@/components/common/AppErrorState.vue'
  const { t } = useI18n()
</script>
