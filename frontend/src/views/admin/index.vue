<template>
  <div class="admin-layout">
    <a-layout>
      <!-- 侧边栏 -->
      <a-layout-sider
        v-model:collapsed="collapsed"
        :trigger="null"
        collapsible
        :width="220"
        class="admin-sider"
      >
        <div class="logo">
          <img src="@/assets/logo.svg" alt="Logo" />
          <span v-if="!collapsed">{{ t('admin.title') }}</span>
        </div>

        <a-menu
          v-model:selectedKeys="selectedKeys"
          v-model:openKeys="openKeys"
          mode="inline"
          theme="dark"
        >
          <a-menu-item key="dashboard" @click="navigate('dashboard')">
            <DashboardOutlined />
            <span>{{ t('admin.dashboard') }}</span>
          </a-menu-item>
          <a-menu-item key="users" @click="navigate('users')">
            <UserOutlined />
            <span>{{ t('admin.users') }}</span>
          </a-menu-item>
          <a-menu-item key="tools" @click="navigate('tools')">
            <ToolOutlined />
            <span>{{ t('admin.tools') }}</span>
          </a-menu-item>
          <a-menu-item key="tasks" @click="navigate('tasks')">
            <CloudServerOutlined />
            <span>{{ t('admin.tasks') }}</span>
          </a-menu-item>
          <a-menu-item key="system" @click="navigate('system')">
            <SettingOutlined />
            <span>{{ t('admin.system') }}</span>
          </a-menu-item>
        </a-menu>
      </a-layout-sider>

      <a-layout>
        <!-- 头部 -->
        <a-layout-header class="admin-header">
          <div class="header-left">
            <MenuUnfoldOutlined
              v-if="collapsed"
              class="trigger"
              @click="collapsed = false"
            />
            <MenuFoldOutlined
              v-else
              class="trigger"
              @click="collapsed = true"
            />
            <a-breadcrumb>
              <a-breadcrumb-item>
                <router-link to="/">{{ t('common.home') }}</router-link>
              </a-breadcrumb-item>
              <a-breadcrumb-item>{{ t('admin.title') }}</a-breadcrumb-item>
              <a-breadcrumb-item>{{ currentPageTitle }}</a-breadcrumb-item>
            </a-breadcrumb>
          </div>

          <div class="header-right">
            <a-dropdown>
              <a-space class="user-dropdown">
                <a-avatar :size="32" :src="userStore.user?.avatar">
                  <template #icon><UserOutlined /></template>
                </a-avatar>
                <span>{{ userStore.user?.username }}</span>
              </a-space>
              <template #overlay>
                <a-menu>
                  <a-menu-item @click="goToProfile">
                    <UserOutlined />
                    {{ t('user.profile') }}
                  </a-menu-item>
                  <a-menu-divider />
                  <a-menu-item @click="goToHome">
                    <HomeOutlined />
                    {{ t('admin.backToSite') }}
                  </a-menu-item>
                  <a-menu-item danger @click="handleLogout">
                    <LogoutOutlined />
                    {{ t('nav.logout') }}
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </div>
        </a-layout-header>

        <!-- 内容区 -->
        <a-layout-content class="admin-content">
          <router-view />
        </a-layout-content>
      </a-layout>
    </a-layout>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  DashboardOutlined,
  UserOutlined,
  ToolOutlined,
  CloudServerOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  HomeOutlined,
  LogoutOutlined
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { useUserStore } from '@/stores'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const userStore = useUserStore()

const collapsed = ref(false)
const selectedKeys = ref<string[]>(['dashboard'])
const openKeys = ref<string[]>([])

const pageTitles: Record<string, string> = {
  dashboard: 'admin.dashboard',
  users: 'admin.users',
  tools: 'admin.tools',
  tasks: 'admin.tasks',
  system: 'admin.system'
}

const currentPageTitle = computed(() => {
  const key = selectedKeys.value[0] as keyof typeof pageTitles
  return t(pageTitles[key] || 'admin.dashboard')
})

// 根据路由更新选中状态
watch(
  () => route.path,
  (path) => {
    const segments = path.split('/')
    const lastSegment = segments[segments.length - 1] as keyof typeof pageTitles
    if (lastSegment && pageTitles[lastSegment]) {
      selectedKeys.value = [lastSegment]
    }
  },
  { immediate: true }
)

const navigate = (key: string) => {
  router.push(`/admin/${key}`)
}

const goToProfile = () => {
  router.push('/user')
}

const goToHome = () => {
  router.push('/')
}

const handleLogout = () => {
  Modal.confirm({
    title: t('user.logoutConfirm'),
    content: t('user.logoutConfirmContent'),
    onOk: async () => {
      await userStore.logout()
      message.success(t('auth.logoutSuccess'))
      router.push('/')
    }
  })
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-layout {
  min-height: 100vh;

  :deep(.ant-layout) {
    min-height: 100vh;
  }
}

.admin-sider {
  .logo {
    height: 64px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: @spacing-sm;
    padding: 0 @spacing-md;
    background: rgba(255, 255, 255, 0.1);

    img {
      height: 32px;
      width: auto;
    }

    span {
      color: #fff;
      font-size: @font-size-lg;
      font-weight: @font-weight-semibold;
      white-space: nowrap;
    }
  }
}

.admin-header {
  background: #fff;
  padding: 0 @spacing-lg;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);

  .header-left {
    display: flex;
    align-items: center;
    gap: @spacing-md;

    .trigger {
      font-size: 18px;
      cursor: pointer;
      transition: color @transition-duration;

      &:hover {
        color: @primary-color;
      }
    }
  }

  .header-right {
    .user-dropdown {
      cursor: pointer;
      padding: @spacing-xs @spacing-sm;
      border-radius: @border-radius-base;
      transition: background @transition-duration;

      &:hover {
        background: @bg-color-light;
      }
    }
  }
}

.admin-content {
  margin: @spacing-lg;
  padding: @spacing-lg;
  background: #fff;
  border-radius: @border-radius-lg;
  min-height: calc(100vh - 64px - 48px);
}
</style>
