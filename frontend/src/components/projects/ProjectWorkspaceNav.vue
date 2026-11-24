<template>
  <nav class="project-workspace-nav" aria-label="项目工作台导航">
    <router-link
      v-for="item in navItems"
      :key="item.key"
      :to="item.to"
      class="project-workspace-nav-item"
      :class="{
        'is-active': isActive(item),
        'is-settings': item.key === 'settings'
      }"
      :title="item.key === 'settings' ? item.label : undefined"
      :aria-label="item.key === 'settings' ? item.label : undefined"
    >
      <SettingOutlined v-if="item.key === 'settings'" class="nav-settings-icon" />
      <span :class="{ 'nav-settings-label': item.key === 'settings' }">{{ item.label }}</span>
    </router-link>
  </nav>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useRoute } from 'vue-router'
  import { SettingOutlined } from '@ant-design/icons-vue'
  import {
    buildProjectWorkspaceNavItems,
    isProjectWorkspaceNavItemActive,
    type ProjectWorkspaceNavItem
  } from '@/domain/projects'

  const props = defineProps<{ projectId: string }>()
  const route = useRoute()

  const currentPath = computed(() => route.path ?? '')
  const queryProjectId = computed(() => {
    const value = route.query?.project_id
    return typeof value === 'string' ? value : undefined
  })
  const navItems = computed(() => buildProjectWorkspaceNavItems(props.projectId))

  function isActive(item: ProjectWorkspaceNavItem) {
    return isProjectWorkspaceNavItemActive(item, {
      currentPath: currentPath.value,
      currentProjectId: props.projectId,
      queryProjectId: queryProjectId.value
    })
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .project-workspace-nav {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
    margin-bottom: @spacing-lg;
    padding-bottom: @spacing-sm;
    overflow-x: auto;
    border-bottom: 1px solid @border-color;
  }

  .project-workspace-nav-item {
    flex: 0 0 auto;
    padding: 6px 10px;
    color: @text-tertiary;
    border-radius: @border-radius-base;
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
    line-height: @line-height-base;
  }

  .project-workspace-nav-item:hover,
  .project-workspace-nav-item.is-active {
    color: @accent-color;
    background: @accent-color-light;
  }

  .project-workspace-nav-item.is-settings {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }

  .nav-settings-icon {
    font-size: @font-size-md;
  }

  .nav-settings-label {
    font-size: @font-size-xs;
  }

  @media (max-width: @screen-sm) {
    .project-workspace-nav {
      margin-right: -@spacing-lg;
      margin-left: -@spacing-lg;
      padding-right: @spacing-lg;
      padding-left: @spacing-lg;
    }
  }
</style>
