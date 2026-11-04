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

    <!-- 分组子导航 -->
    <div class="admin-layout">
      <aside class="admin-nav" :aria-label="t('admin.title')">
        <div v-for="group in adminGroups" :key="group.key" class="admin-nav-group">
          <div class="admin-nav-title">{{ t(group.labelKey) }}</div>
          <button
            v-for="item in group.items"
            :key="item"
            class="admin-nav-item"
            :class="{ active: activeTab === item }"
            @click="navigate(item)"
          >
            <component :is="tabMeta(item).icon" />
            <span>{{ t(tabMeta(item).labelKey) }}</span>
          </button>
        </div>
      </aside>

      <!-- 内容区 -->
      <main class="admin-body">
        <router-view />
      </main>
    </div>
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
  InboxOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const activeTab = ref('dashboard')

// 扁平清单（供路由高亮/查询）；分组见 adminGroups。工作台分组已下线。
const adminTabs = [
  { key: 'dashboard', icon: DashboardOutlined, labelKey: 'admin.dashboard' },
  { key: 'users', icon: TeamOutlined, labelKey: 'admin.users' },
  { key: 'tools', icon: ToolOutlined, labelKey: 'admin.tools' },
  { key: 'tool-packages', icon: InboxOutlined, labelKey: 'admin.toolPackages' },
  { key: 'tool-categories', icon: AppstoreOutlined, labelKey: 'admin.toolCategories' },
  { key: 'tasks', icon: CloudServerOutlined, labelKey: 'admin.tasks' },
  { key: 'compute', icon: DatabaseOutlined, labelKey: 'admin.compute.title' },
  { key: 'audit', icon: FileSearchOutlined, labelKey: 'admin.audit.title' },
  { key: 'system', icon: SettingOutlined, labelKey: 'admin.system' },
]

const adminGroups = [
  { key: 'overview', labelKey: 'admin.group.overview', items: ['dashboard'] },
  { key: 'access', labelKey: 'admin.group.access', items: ['users'] },
  {
    key: 'tools',
    labelKey: 'admin.group.tools',
    items: ['tools', 'tool-packages', 'tool-categories'],
  },
  { key: 'tasks', labelKey: 'admin.group.tasks', items: ['tasks', 'compute'] },
  { key: 'system', labelKey: 'admin.group.system', items: ['audit', 'system'] },
]

function tabMeta(key: string) {
  return adminTabs.find(tab => tab.key === key) ?? adminTabs[0]!
}

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

.admin-layout {
  display: flex;
  gap: @spacing-lg;
  align-items: flex-start;
}

.admin-nav {
  flex: 0 0 208px;
  width: 208px;
  position: sticky;
  top: @spacing-lg;
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
  padding: @spacing-sm;
  background: @bg-surface;
  border: 1px solid @border-color;
  border-radius: @border-radius-lg;
}

.admin-nav-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.admin-nav-title {
  padding: 6px 10px 2px;
  color: @text-tertiary;
  font-size: @font-size-xs;
  font-weight: @font-weight-semibold;
  letter-spacing: 0.04em;
}

.admin-nav-item {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  padding: 8px 10px;
  border: none;
  border-radius: @border-radius-md;
  background: transparent;
  color: @text-secondary;
  font-size: @font-size-sm;
  font-weight: @font-weight-medium;
  font-family: @font-family;
  text-align: left;
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
  flex: 1;
  min-width: 0;
  min-height: 60vh;
}

@media (max-width: @screen-md) {
  .admin-page {
    padding: @spacing-md;
  }

  .admin-layout {
    flex-direction: column;
  }

  .admin-nav {
    position: static;
    width: 100%;
    flex: none;
    flex-direction: row;
    flex-wrap: wrap;
  }

  .admin-nav-group {
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
  }

  .admin-nav-title {
    display: none;
  }
}
</style>
