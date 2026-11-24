<template>
  <div class="project-view-switcher" role="tablist" data-testid="project-view-switcher">
    <router-link
      v-for="item in items"
      :key="item.key"
      :to="item.to"
      role="tab"
      class="project-view-switcher__item"
      :class="{ 'is-active': item.key === active }"
      :aria-selected="item.key === active"
      :data-testid="`project-view-tab-${item.key}`"
    >
      {{ item.label }}
    </router-link>
  </div>
</template>

<script setup lang="ts">
  export interface ProjectViewTabItem {
    key: string
    label: string
    to: string
  }

  defineProps<{
    items: readonly ProjectViewTabItem[]
    active: string
  }>()
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .project-view-switcher {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    padding: 3px;
    margin-bottom: @spacing-md;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-elevated;
  }

  .project-view-switcher__item {
    padding: 4px 12px;
    border-radius: @border-radius-sm;
    color: @text-secondary;
    font-size: @font-size-xs;
    font-weight: @font-weight-medium;
    text-decoration: none;
    transition: all @transition-fast;

    &:hover {
      color: @text-primary;
    }

    &.is-active {
      background: @bg-surface;
      color: @accent-color;
      box-shadow: @shadow-sm;
    }
  }
</style>
