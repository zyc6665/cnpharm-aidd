<template>
  <header class="app-page-header" :class="`app-page-header--${align}`">
    <div class="app-page-header__copy">
      <p v-if="eyebrow" class="app-page-header__eyebrow">{{ eyebrow }}</p>
      <h1 class="app-page-header__title">{{ title }}</h1>
      <p v-if="subtitle" class="app-page-header__subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="app-page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
  withDefaults(defineProps<{
    title: string
    subtitle?: string
    eyebrow?: string
    align?: 'start' | 'center'
  }>(), {
    align: 'start'
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .app-page-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: @spacing-xl;
    margin-bottom: @spacing-xl;
  }

  .app-page-header__copy {
    min-width: 0;
    max-width: 760px;
  }

  .app-page-header--center {
    align-items: center;
    justify-content: center;
    text-align: center;

    .app-page-header__copy {
      max-width: 840px;
      margin: 0 auto;
    }

    .app-page-header__subtitle {
      max-width: 760px;
      margin-right: auto;
      margin-left: auto;
    }
  }

  .app-page-header__eyebrow {
    margin: 0 0 @spacing-xs;
    color: @accent-color;
    font-size: @font-size-xs;
    font-weight: @font-weight-bold;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .app-page-header__title {
    margin: 0;
    color: @text-color-light-primary;
    font-size: @font-size-xxxl;
    font-weight: @font-weight-bold;
    line-height: @line-height-tight;
  }

  .app-page-header__subtitle {
    margin: @spacing-sm 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-lg;
    line-height: @line-height-base;
  }

  .app-page-header__actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: @spacing-sm;
    flex-shrink: 0;
  }

  @media (max-width: @screen-md) {
    .app-page-header {
      align-items: flex-start;
      flex-direction: column;
      gap: @spacing-md;
    }

    .app-page-header__title {
      font-size: @font-size-xxl;
    }

    .app-page-header__subtitle {
      font-size: @font-size-md;
    }

    .app-page-header__actions {
      justify-content: flex-start;
      width: 100%;
    }
  }
</style>
