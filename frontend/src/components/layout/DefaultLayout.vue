<template>
  <a-layout class="default-layout">
    <!-- 顶部导航 -->
    <a-layout-header class="header">
      <div class="header-content">
        <!-- Logo -->
        <router-link to="/" class="logo">
          <span class="logo-text">CPUModel</span>
        </router-link>

        <a-button type="text" class="mobile-menu-btn" @click="mobileDrawerOpen = true">
          <MenuOutlined />
        </a-button>

        <!-- 导航菜单 -->
        <a-menu
          v-model:selectedKeys="selectedKeys"
          mode="horizontal"
          theme="dark"
          class="nav-menu"
        >
          <a-menu-item v-for="item in visibleNavItems" :key="item.key">
            <router-link v-if="item.to" :to="item.to">
              {{ t(item.labelKey) }}
            </router-link>
            <a v-else :href="item.href" target="_blank" rel="noreferrer">
              {{ t(item.labelKey) }}
            </a>
          </a-menu-item>
        </a-menu>

        <!-- 右侧操作区 -->
        <div class="header-actions">
          <!-- 语言切换 -->
          <a-dropdown>
            <a-button type="text" class="action-btn">
              <GlobalOutlined />
            </a-button>
            <template #overlay>
              <a-menu @click="handleLocaleChange">
                <a-menu-item key="zh-CN">简体中文</a-menu-item>
                <a-menu-item key="en-US">English</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>

          <!-- 用户操作 -->
          <template v-if="isLoggedIn">
            <a-dropdown>
              <a-button type="text" class="user-btn">
                <ProtectedAvatar :size="28" :src="userStore.avatar">
                  {{ username.charAt(0).toUpperCase() }}
                </ProtectedAvatar>
                <span class="username">{{ username }}</span>
              </a-button>
              <template #overlay>
                <a-menu @click="handleUserMenuClick">
                  <a-menu-item key="profile">
                    <UserOutlined />
                    {{ t('nav.profile') }}
                  </a-menu-item>
                  <a-menu-item key="settings">
                    <SettingOutlined />
                    {{ t('nav.settings') }}
                  </a-menu-item>
                  <a-menu-item key="favorites">
                    <HeartOutlined />
                    {{ t('nav.favorites') }}
                  </a-menu-item>
                  <a-menu-divider />
                  <a-menu-item key="logout">
                    <LogoutOutlined />
                    {{ t('nav.logout') }}
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </template>
          <template v-else>
            <router-link to="/login">
              <a-button type="primary" ghost>{{ t('nav.login') }}</a-button>
            </router-link>
            <router-link to="/register" class="ml-sm">
              <a-button type="primary">{{ t('nav.register') }}</a-button>
            </router-link>
          </template>
        </div>
      </div>
    </a-layout-header>

    <a-drawer
      v-model:open="mobileDrawerOpen"
      placement="left"
      class="mobile-nav-drawer"
      :title="'CPUModel'"
      :width="280"
      @close="mobileDrawerOpen = false"
    >
      <a-menu
        :selectedKeys="selectedKeys"
        mode="inline"
        class="mobile-drawer-menu"
        @click="handleMobileNavClick"
      >
        <a-menu-item v-for="item in visibleNavItems" :key="item.key">
          {{ t(item.labelKey) }}
        </a-menu-item>
      </a-menu>
    </a-drawer>

    <!-- 主内容区 -->
    <a-layout-content class="content">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </a-layout-content>

    <!-- 页脚 -->
    <a-layout-footer class="footer">
      <div class="footer-content">
        <div class="footer-links">
          <a href="#">{{ t('footer.about') }}</a>
          <a href="#">{{ t('footer.docs') }}</a>
          <a href="#">{{ t('footer.contact') }}</a>
          <a href="#">{{ t('footer.privacy') }}</a>
          <a href="#">{{ t('footer.terms') }}</a>
        </div>
        <div class="footer-copyright">
          {{ t('footer.copyright') }}
        </div>
      </div>
    </a-layout-footer>
  </a-layout>
</template>

<script setup lang="ts">
  import { ref, computed, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import {
    MenuOutlined,
    GlobalOutlined,
    UserOutlined,
    SettingOutlined,
    HeartOutlined,
    LogoutOutlined
  } from '@ant-design/icons-vue'
  import { useUserStore, useAppStore } from '@/stores'
  import { setLocale, type Locale } from '@/locales'
  import ProtectedAvatar from '@/components/common/ProtectedAvatar.vue'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const userStore = useUserStore()
  const appStore = useAppStore()

  const selectedKeys = ref<string[]>([])
  const mobileDrawerOpen = ref(false)
  const cpupdbUrl = 'https://www.cpupdb.com'

  const isLoggedIn = computed(() => userStore.isLoggedIn)
  const isAdmin = computed(() => userStore.isAdmin)
  const username = computed(() => userStore.username)

  const navItems = [
    { key: 'home', labelKey: 'nav.home', to: '/' },
    { key: 'tools', labelKey: 'nav.tools', to: '/tools' },
    { key: 'cpupdb', labelKey: 'nav.cpupdb', href: cpupdbUrl },
    { key: 'tasks', labelKey: 'nav.tasks', to: '/tasks', requiresAuth: true },
    { key: 'admin', labelKey: 'nav.admin', to: '/admin', requiresAdmin: true }
  ]

  const visibleNavItems = computed(() => {
    return navItems.filter(item => {
      if (item.requiresAdmin) {
        return isAdmin.value
      }
      if (item.requiresAuth) {
        return isLoggedIn.value
      }
      return true
    })
  })

  // 监听路由变化更新选中菜单
  watch(
    () => route.path,
    path => {
      if (path === '/') {
        selectedKeys.value = ['home']
      } else if (path.startsWith('/tools')) {
        selectedKeys.value = ['tools']
      } else if (path.startsWith('/tasks')) {
        selectedKeys.value = ['tasks']
      } else if (path.startsWith('/admin')) {
        selectedKeys.value = ['admin']
      } else {
        selectedKeys.value = []
      }
    },
    { immediate: true }
  )

  // 切换语言
  const handleLocaleChange = ({ key }: { key: string }) => {
    setLocale(key as Locale)
    appStore.setLocale(key as Locale)
  }

  const handleMobileNavClick = ({ key }: { key: string }) => {
    const item = visibleNavItems.value.find(navItem => navItem.key === key)
    mobileDrawerOpen.value = false

    if (!item) {
      return
    }

    if (item.to) {
      router.push(item.to)
      return
    }

    if (item.href) {
      window.open(item.href, '_blank', 'noopener,noreferrer')
    }
  }

  // 用户菜单点击
  const handleUserMenuClick = async ({ key }: { key: string }) => {
    mobileDrawerOpen.value = false
    switch (key) {
      case 'profile':
        router.push('/user')
        break
      case 'settings':
        router.push('/user/settings')
        break
      case 'favorites':
        router.push('/user/favorites')
        break
      case 'logout':
        await userStore.logout()
        message.success(t('auth.logoutSuccess'))
        router.push('/')
        break
    }
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .default-layout {
    min-height: 100vh;
  }

  .header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: @z-index-fixed;
    height: @header-height;
    padding: 0;
    background: rgba(15, 12, 41, 0.95);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid @border-color-dark;
  }

  .header-content {
    display: flex;
    align-items: center;
    height: 100%;
    max-width: @container-xxl;
    margin: 0 auto;
    padding: 0 @spacing-lg;
  }

  .logo {
    display: flex;
    align-items: center;
    margin-right: @spacing-xl;

    .logo-text {
      font-size: @font-size-xl;
      font-weight: @font-weight-bold;
      color: @accent-color;
      letter-spacing: 1px;
    }
  }

  .mobile-menu-btn {
    display: none;
    color: @text-color-secondary;
    margin-right: @spacing-sm;

    &:hover {
      color: @accent-color;
    }
  }

  .nav-menu {
    flex: 1;
    background: transparent;
    border-bottom: none;

    :deep(.ant-menu-item) {
      color: @text-color-secondary;

      &:hover,
      &.ant-menu-item-selected {
        color: @accent-color;
      }

      a {
        color: inherit;
      }
    }
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: @spacing-sm;

    .action-btn {
      color: @text-color-secondary;

      &:hover {
        color: @accent-color;
      }
    }

    .user-btn {
      display: flex;
      align-items: center;
      gap: @spacing-sm;
      color: @text-color-secondary;

      .username {
        max-width: 100px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      &:hover {
        color: @accent-color;
      }
    }

    .ml-sm {
      margin-left: @spacing-sm;
    }
  }

  .content {
    margin-top: @header-height;
    min-height: calc(100vh - @header-height - @footer-height);
  }

  .footer {
    background: @bg-dark;
    padding: @spacing-lg;
    border-top: 1px solid @border-color-dark;
  }

  .footer-content {
    max-width: @container-xxl;
    margin: 0 auto;
    text-align: center;
  }

  .footer-links {
    margin-bottom: @spacing-md;

    a {
      color: @text-color-tertiary;
      margin: 0 @spacing-md;
      transition: color @transition-fast;

      &:hover {
        color: @accent-color;
      }
    }
  }

  .footer-copyright {
    color: @text-color-disabled;
    font-size: @font-size-sm;
  }

  .mobile-nav-drawer {
    :deep(.ant-drawer-header) {
      border-bottom: 1px solid @border-color-light;
    }

    :deep(.ant-drawer-title) {
      color: @bg-dark;
      font-weight: @font-weight-bold;
    }
  }

  .mobile-drawer-menu {
    border-inline-end: none;
  }

  @media (max-width: @screen-md) {
    .header-content {
      padding: 0 @spacing-md;
    }

    .logo {
      margin-right: auto;
    }

    .mobile-menu-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      order: -1;
    }

    .nav-menu {
      display: none;
    }

    .header-actions {
      gap: @spacing-xs;

      .username {
        display: none;
      }

      .ml-sm {
        margin-left: 0;
      }
    }

    .footer-links {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: @spacing-sm @spacing-md;

      a {
        margin: 0;
      }
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
