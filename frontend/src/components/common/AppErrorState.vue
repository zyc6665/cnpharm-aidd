<template>
  <main class="app-error-state">
    <section class="app-error-state__panel">
      <p class="app-error-state__eyebrow">{{ PLATFORM_SHORT_NAME }}</p>
      <h1 class="app-error-state__code">{{ code }}</h1>
      <h2 class="app-error-state__title">{{ title }}</h2>
      <p class="app-error-state__description">{{ description }}</p>
      <router-link :to="to">
        <a-button type="primary" size="large">
          {{ actionText }}
        </a-button>
      </router-link>
    </section>
  </main>
</template>

<script setup lang="ts">
  import { PLATFORM_SHORT_NAME } from '@/config/brand'

  withDefaults(
    defineProps<{
      code: string
      title: string
      description: string
      actionText: string
      /**
       * 操作按钮的跳转目标。
       *
       * 默认 `/`（403/404 的「返回首页」）；页面内错态可传项目/靶点等上游路径，
       * 让按钮真正回到用户上一级，而不是把用户甩到首页。
       */
      to?: string
    }>(),
    { to: '/' }
  )
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .app-error-state {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: @spacing-lg;
    background: @bg-body;
    color: @text-primary;
  }

  .app-error-state__panel {
    width: min(100%, 560px);
    padding: @spacing-xxl @spacing-xl;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-elevated;
    box-shadow: @shadow-lg;
  }

  .app-error-state__eyebrow {
    margin: 0 0 @spacing-md;
    color: @text-tertiary;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    font-weight: @font-weight-semibold;
    text-transform: uppercase;
  }

  .app-error-state__code {
    margin: 0;
    color: @accent-color;
    font-size: 112px;
    font-weight: @font-weight-bold;
    line-height: 0.9;
  }

  .app-error-state__title {
    margin: @spacing-lg 0 @spacing-sm;
    color: @text-primary;
    font-size: @font-size-xxl;
    font-weight: @font-weight-semibold;
  }

  .app-error-state__description {
    margin: 0 auto @spacing-xl;
    max-width: 420px;
    color: @text-secondary;
    font-size: @font-size-lg;
    line-height: @line-height-base;
  }

  :deep(.ant-btn-primary) {
    background: @accent-color;
    border-color: @accent-color;
    color: @bg-body;
    font-weight: @font-weight-semibold;

    &:hover {
      background: @accent-color-hover;
      border-color: @accent-color-hover;
      color: @bg-body;
    }
  }

  @media (max-width: @screen-sm) {
    .app-error-state__panel {
      padding: @spacing-xl @spacing-lg;
    }

    .app-error-state__code {
      font-size: 84px;
    }
  }
</style>
