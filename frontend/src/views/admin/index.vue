<template>
  <div class="admin-page">
    <!-- 顶部工具栏 -->
    <header class="admin-topbar">
      <div class="admin-breadcrumb">
        <router-link to="/workspace" class="admin-back">
          <ArrowLeftOutlined />
          <span>{{ t('admin.backToSite') }}</span>
        </router-link>
        <span class="admin-sep">/</span>
        <span class="admin-current">{{ t('admin.title') }}</span>
      </div>
    </header>

    <!-- 子页导航 tabs -->
    <nav class="admin-tabs">
      <button
        v-for="tab in adminTabs"
        :key="tab.key"
        class="admin-tab"
        :class="{ active: activeTab === tab.key }"
        @click="navigate(tab.key)"
      >
        <component :is="tab.icon" />
        <span>{{ t(tab.labelKey) }}</span>
      </button>
    </nav>

    <!-- 内容区 -->
    <main class="admin-body">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowLeftOutlined,
  DashboardOutlined,
  TeamOutlined,
  ToolOutlined,
  AppstoreOutlined,
  ClusterOutlined,
  CloudServerOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const activeTab = ref('dashboard')

const adminTabs = [
  { key: 'dashboard', icon: DashboardOutlined, labelKey: 'admin.dashboard' },
  { key: 'users', icon: TeamOutlined, labelKey: 'admin.users' },
  { key: 'tools', icon: ToolOutlined, labelKey: 'admin.tools' },
  { key: 'tool-categories', icon: AppstoreOutlined, labelKey: 'admin.toolCategories' },
  { key: 'workbench-groups', icon: ClusterOutlined, labelKey: 'admin.workbenchGroups' },
  { key: 'tasks', icon: CloudServerOutlined, labelKey: 'admin.tasks' },
  { key: 'system', icon: SettingOutlined, labelKey: 'admin.system' },
]

watch(
  () => route.path,
  (path) => {
    const segment = path.split('/').pop()
    if (segment && adminTabs.some((t) => t.key === segment)) {
      activeTab.value = segment
    }
  },
  { immediate: true },
)

function navigate(key: string) {
  router.push(`/admin/${key}`)
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-page {
  max-width: @container-xxl;
  margin: 0 auto;
  padding: @spacing-lg;
}

.admin-topbar {
  margin-bottom: @spacing-lg;
}

.admin-back {
  display: inline-flex;
  align-items: center;
  gap: @spacing-xs;
  color: @text-secondary;
  font-size: @font-size-sm;
  text-decoration: none;
  transition: color @transition-fast;

  &:hover {
    color: @text-primary;
  }
}

.admin-sep {
  margin: 0 @spacing-sm;
  color: @text-tertiary;
}

.admin-current {
  color: @text-primary;
  font-weight: @font-weight-medium;
  font-size: @font-size-sm;
}

.admin-tabs {
  display: flex;
  gap: 2px;
  padding: 4px;
  margin-bottom: @spacing-lg;
  background: @bg-surface;
  border: 1px solid @border-color;
  border-radius: @border-radius-lg;
  overflow-x: auto;
}

.admin-tab {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  padding: 8px 14px;
  border: none;
  border-radius: @border-radius-md;
  background: transparent;
  color: @text-secondary;
  font-size: @font-size-sm;
  font-weight: @font-weight-medium;
  font-family: @font-family;
  cursor: pointer;
  white-space: nowrap;
  transition: all @transition-fast;

  &:hover {
    color: @text-primary;
    background: @bg-hover;
  }

  &.active {
    color: @text-primary;
    background: @bg-elevated;
    box-shadow: @shadow-sm;
  }
}

.admin-body {
  min-height: 60vh;
}

@media (max-width: @screen-md) {
  .admin-page {
    padding: @spacing-md;
  }

  .admin-tabs {
    gap: 0;
    padding: 2px;
  }

  .admin-tab {
    padding: 8px 10px;
    font-size: @font-size-xs;
  }
}
</style>
