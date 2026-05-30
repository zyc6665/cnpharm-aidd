<template>
  <section class="app-filter-bar">
    <slot />
  </section>
</template>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .app-filter-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: @spacing-md;
    margin-bottom: @spacing-xl;
    padding: @spacing-md;
    background: @bg-light-secondary;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-lg;
    box-shadow: @shadow-sm;
  }

  :deep(.ant-input-search),
  :deep(.ant-picker),
  :deep(.ant-select),
  :deep(.ant-btn) {
    min-width: 0;
  }

  @media (max-width: @screen-sm) {
    .app-filter-bar {
      align-items: stretch;
      flex-direction: column;
      padding: @spacing-sm;
    }

    :deep(.ant-input-search),
    :deep(.ant-picker),
    :deep(.ant-select),
    :deep(.ant-btn) {
      width: 100% !important;
      max-width: none !important;
    }
  }
</style>
