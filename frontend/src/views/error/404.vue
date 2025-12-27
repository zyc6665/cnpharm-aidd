<template>
  <div class="error-page">
    <div class="error-content">
      <h1 class="error-code">404</h1>
      <p class="error-text">{{ t('error.404.description') }}</p>
      <router-link to="/">
        <a-button type="primary" size="large">
          {{ t('error.backHome') }}
        </a-button>
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  const { t } = useI18n()
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .error-page {
    min-height: 100vh;
    .gradient-bg();
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .error-content {
    text-align: center;
  }

  .error-code {
    font-size: 120px;
    font-weight: @font-weight-bold;
    color: @accent-color;
    line-height: 1;
    margin-bottom: @spacing-md;
  }

  .error-text {
    font-size: @font-size-lg;
    color: @text-color-secondary;
    margin-bottom: @spacing-xl;
  }

  :deep(.ant-btn-primary) {
    background: @accent-color;
    border-color: @accent-color;

    &:hover {
      background: @accent-color-hover;
      border-color: @accent-color-hover;
    }
  }
</style>
