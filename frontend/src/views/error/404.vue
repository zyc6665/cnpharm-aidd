<template>
  <AppErrorState
    code="404"
    :title="t('error.notFound')"
    :description="t('error.404.description')"
    :action-text="t('error.backHome')"
  />
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import AppErrorState from '@/components/common/AppErrorState.vue'
  const { t } = useI18n()
</script>
