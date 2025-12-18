<template>
  <a-layout class="admin-layout">
    <!-- 侧边栏 -->
    <a-layout-sider
      v-model:collapsed="collapsed"
      :trigger="null"
      collapsible
      :width="240"
      :collapsed-width="80"
      class="sider"
    >
      <!-- Logo -->
      <div class="sider-logo">
        <router-link to="/">
          <span v-if="!collapsed" class="logo-text">CPUModel</span>
          <span v-else class="logo-short">CP</span>
        </router-link>
      </div>

      <!-- 菜单 -->
      <a-menu
        v-model:selectedKeys="selectedKeys"
        v-model:openKeys="openKeys"
        mode="inline"
        theme="dark"
      >
        <a-menu-item key="dashboard">
          <router-link to="/admin/dashboard">
            <DashboardOutlined />
            <span>{{ t('admin.dashboard') }}</span>
          </router-link>
        </a-menu-item>
        <a-menu-item key="users">
          <router-link to="/admin/users">
            <UserOutlined />
            <span>{{ t('admin.users') }}</span>
          </router-link>
        </a-menu-item>
        <a-menu-item key="tools">
          <router-link to="/admin/tools">
            <ToolOutlined />
            <span>{{ t('admin.tools') }}</span>
          </router-link>
        </a-menu-item>
        <a-menu-item key="tasks">
          <router-link to="/admin/tasks">
            <OrderedListOutlined />
            <span>{{ t('admin.tasks') }}</span>
          </router-link>
        </a-menu-item>
        <a-menu-item key="system">
          <router-link to="/admin/system">
            <SettingOutlined />
            <span>{{ t('admin.system') }}</span>
          </router-link>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <a-layout>
      <!-- 顶部栏 -->
      <a-layout-header class="admin-header">
        <div class="header-left">
          <a-button type="text" @click="toggleCollapsed">
            <MenuUnfoldOutlined v-if="collapsed" />
            <MenuFoldOutlined v-else />
          </a-button>
          <a-breadcrumb class="breadcrumb">
            <a-breadcrumb-item>
              <router-link to="/admin">{{ t('admin.title') }}</router-link>
            </a-breadcrumb-item>
            <a-breadcrumb-item v-if="currentMenu">
              {{ currentMenu }}
            </a-breadcrumb-item>
          </a-breadcrumb>
        </div>

        <div class="header-right">
          <!-- 返回前台 -->
          <router-link to="/">
            <a-button type="text">
              <HomeOutlined />
              {{ t('nav.home') }}
            </a-button>
          </router-link>

          <!-- 用户信息 -->
          <a-dropdown>
            <a-button type="text" class="user-btn">
              <a-avatar :size="28">
                {{ username.charAt(0).toUpperCase() }}
              </a-avatar>
              <span class="username">{{ username }}</span>
            </a-button>
            <template #overlay>
              <a-menu @click="handleUserMenuClick">
                <a-menu-item key="profile">
                  <UserOutlined />
                  {{ t('nav.profile') }}
                </a-menu-item>
                <a-menu-divider />
                <a-menu-item key="logout">
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
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
  import { ref, computed, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import {
    DashboardOutlined,
    UserOutlined,
    ToolOutlined,
    OrderedListOutlined,
    SettingOutlined,
    MenuFoldOutlined,
    MenuUnfoldOutlined,
    HomeOutlined,
    LogoutOutlined
  } from '@ant-design/icons-vue'
  import { useUserStore, useAppStore } from '@/stores'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const userStore = useUserStore()
  const appStore = useAppStore()

  const collapsed = ref(appStore.collapsed)
  const selectedKeys = ref<string[]>(['dashboard'])
  const openKeys = ref<string[]>([])

  const username = computed(() => userStore.username)

  const currentMenu = computed(() => {
    const menuMap: Record<string, string> = {
      dashboard: t('admin.dashboard'),
      users: t('admin.users'),
      tools: t('admin.tools'),
      tasks: t('admin.tasks'),
      system: t('admin.system')
    }
    const key = selectedKeys.value[0]
    return key ? menuMap[key] || '' : ''
  })

  // 监听路由变化
  watch(
    () => route.path,
    path => {
      if (path.includes('/admin/dashboard')) {
        selectedKeys.value = ['dashboard']
      } else if (path.includes('/admin/users')) {
        selectedKeys.value = ['users']
      } else if (path.includes('/admin/tools')) {
        selectedKeys.value = ['tools']
      } else if (path.includes('/admin/tasks')) {
        selectedKeys.value = ['tasks']
      } else if (path.includes('/admin/system')) {
        selectedKeys.value = ['system']
      }
    },
    { immediate: true }
  )

  const toggleCollapsed = () => {
    collapsed.value = !collapsed.value
    appStore.setCollapsed(collapsed.value)
  }

  const handleUserMenuClick = async ({ key }: { key: string }) => {
    if (key === 'profile') {
      router.push('/user')
    } else if (key === 'logout') {
      await userStore.logout()
      message.success(t('auth.logoutSuccess'))
      router.push('/')
    }
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .admin-layout {
    min-height: 100vh;
  }

  .sider {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    overflow: auto;
    background: @bg-dark;
  }

  .sider-logo {
    height: @header-height;
    display: flex;
    align-items: center;
    justify-content: center;
    border-bottom: 1px solid @border-color-dark;

    a {
      color: @accent-color;
      font-size: @font-size-xl;
      font-weight: @font-weight-bold;
    }

    .logo-short {
      font-size: @font-size-xxl;
    }
  }

  .admin-header {
    position: fixed;
    top: 0;
    right: 0;
    left: @sider-width;
    z-index: @z-index-fixed;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: @header-height;
    padding: 0 @spacing-lg;
    background: #fff;
    box-shadow: @shadow-sm;
    transition: left @transition-base;

    .ant-layout-sider-collapsed + .ant-layout & {
      left: @sider-collapsed-width;
    }
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: @spacing-md;

    .breadcrumb {
      margin-left: @spacing-md;
    }
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: @spacing-sm;

    .user-btn {
      display: flex;
      align-items: center;
      gap: @spacing-sm;

      .username {
        max-width: 100px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }
  }

  .admin-content {
    margin-top: @header-height;
    margin-left: @sider-width;
    padding: @spacing-lg;
    min-height: calc(100vh - @header-height);
    background: @bg-light;
    transition: margin-left @transition-base;

    .ant-layout-sider-collapsed + .ant-layout & {
      margin-left: @sider-collapsed-width;
    }
  }

  // 页面切换动画
  .fade-enter-active,
  .fade-leave-active {
    transition: opacity 0.2s ease;
  }

  .fade-enter-from,
  .fade-leave-to {
    opacity: 0;
  }
</style>
