<template>
  <nav class="project-workspace-nav" aria-label="项目工作台导航">
    <router-link
      v-for="item in navItems"
      :key="item.key"
      :to="item.to"
      class="project-workspace-nav-item"
      :class="{ 'is-active': isActive(item) }"
    >
      {{ item.label }}
    </router-link>
  </nav>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useRoute } from 'vue-router'

  const props = defineProps<{ projectId: string }>()
  const route = useRoute()

  const encodedProjectId = computed(() => encodeURIComponent(props.projectId))
  const currentPath = computed(() => route.path ?? '')
  const taskPath = computed(() => `/tasks?project_id=${encodedProjectId.value}`)
  const navItems = computed(() => [
    { key: 'overview', label: '项目总览', to: `/projects/${props.projectId}` },
    { key: 'research', label: '智能体研究', to: `/projects/${props.projectId}/research` },
    { key: 'boards', label: '科研白板', to: `/projects/${props.projectId}/boards` },
    { key: 'workflow', label: 'Workflow', to: `/projects/${props.projectId}/workflow` },
    { key: 'tasks', label: '任务中心', to: taskPath.value },
    { key: 'lineage', label: 'Artifact 谱系', to: `/projects/${props.projectId}/lineage` },
    { key: 'settings', label: '项目设置', to: `/projects/${props.projectId}/settings` }
  ])

  function isActive(item: { key: string; to: string }) {
    if (item.key === 'tasks') {
      return currentPath.value === '/tasks' && route.query?.project_id === props.projectId
    }
    return currentPath.value === item.to || currentPath.value.startsWith(`${item.to}/`)
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

  @media (max-width: @screen-sm) {
    .project-workspace-nav {
      margin-right: -@spacing-lg;
      margin-left: -@spacing-lg;
      padding-right: @spacing-lg;
      padding-left: @spacing-lg;
    }
  }
</style>
