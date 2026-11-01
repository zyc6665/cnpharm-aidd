<template>
  <div
    class="app-shell"
    :class="{ 'sidebar-collapsed': collapsed, 'focus-mode': route.meta.focusMode, 'mobile-nav-open': mobileNavOpen }"
  >
    <!-- 移动端顶栏（仅窄屏显示）：品牌 + 抽屉开关 -->
    <header class="mobile-topbar">
      <router-link to="/workspace" class="mobile-brand" :aria-label="t('nav.home')">
        <img src="@/assets/logo.svg" :alt="PLATFORM_NAME" class="brand-logo" />
        <span class="mobile-brand-text">{{ PLATFORM_SHORT_NAME }}</span>
      </router-link>
      <button
        class="mobile-menu-btn"
        type="button"
        :aria-label="t('common.expand')"
        :aria-expanded="mobileNavOpen"
        @click="mobileNavOpen = !mobileNavOpen"
      >
        <MenuFoldOutlined v-if="mobileNavOpen" />
        <MenuUnfoldOutlined v-else />
      </button>
    </header>
    <div v-if="mobileNavOpen" class="sidebar-backdrop" @click="mobileNavOpen = false"></div>

    <!-- 侧边栏 -->
    <aside class="shell-sidebar">
      <!-- Logo 区 -->
      <div class="sidebar-brand">
        <router-link to="/workspace" class="brand-link" :aria-label="t('nav.home')">
          <img src="@/assets/logo.svg" :alt="PLATFORM_NAME" class="brand-logo" />
          <span v-if="!collapsed" class="brand-text">{{ PLATFORM_SHORT_NAME }}</span>
        </router-link>
        <button
          class="sidebar-collapse-btn"
          type="button"
          :aria-label="collapsed ? t('common.expand') : t('common.collapse')"
          @click="toggleCollapsed"
        >
          <MenuFoldOutlined v-if="!collapsed" />
          <MenuUnfoldOutlined v-else />
        </button>
      </div>

      <div class="sidebar-scroll">
      <!-- 主导航 -->
      <nav class="sidebar-nav" aria-label="主导航">
        <router-link
          v-for="item in mainNav"
          :key="item.key"
          :to="item.to"
          class="nav-item"
          :class="{ active: isActive(item.active) }"
          :aria-label="t(item.labelKey)"
          :title="collapsed ? t(item.labelKey) : undefined"
        >
          <component :is="item.icon" class="nav-icon" />
          <span v-if="!collapsed" class="nav-label">{{ t(item.labelKey) }}</span>
          <span v-if="item.badge && !collapsed" class="nav-badge">{{ item.badge }}</span>
        </router-link>
      </nav>

      <!-- 设计工具导航（直达页入口；移动端底部 Tab 不显示，避免项过多） -->
      <nav class="sidebar-nav sidebar-design-nav" :aria-label="t('nav.designSection')">
        <div v-if="!collapsed" class="sidebar-section-label">{{ t('nav.designSection') }}</div>
        <router-link
          v-for="item in designNav"
          :key="item.key"
          :to="item.to"
          class="nav-item"
          :class="{ active: isActive(item.active) }"
          :aria-label="t(item.labelKey)"
          :title="collapsed ? t(item.labelKey) : undefined"
        >
          <component :is="item.icon" class="nav-icon" />
          <span v-if="!collapsed" class="nav-label">{{ t(item.labelKey) }}</span>
        </router-link>
      </nav>

      <!-- 分隔 -->
      <div class="sidebar-divider"></div>

      <!-- 管理导航（管理员可见） -->
      <nav v-if="isAdmin" class="sidebar-nav" aria-label="管理导航">
        <router-link
          v-for="item in adminNav"
          :key="item.key"
          :to="item.to"
          class="nav-item"
          :class="{ active: isActive(item.active) }"
          :aria-label="t(item.labelKey)"
          :title="collapsed ? t(item.labelKey) : undefined"
        >
          <component :is="item.icon" class="nav-icon" />
          <span v-if="!collapsed" class="nav-label">{{ t(item.labelKey) }}</span>
        </router-link>
      </nav>
      </div>

      <!-- 底部区 -->
      <div class="sidebar-footer">
        <button
          class="nav-item nav-item-btn"
          :class="{ active: isActive(['settings']) }"
          @click="toggleTheme"
          :aria-label="t('common.theme')"
          :title="collapsed ? t('common.theme') : undefined"
        >
          <BulbOutlined class="nav-icon" />
          <span v-if="!collapsed" class="nav-label">{{ t('common.theme') }}</span>
        </button>

        <router-link
          to="/user/settings"
          class="nav-item"
          :class="{ active: isActive(['settings']) }"
          :aria-label="t('user.settings')"
          :title="collapsed ? t('user.settings') : undefined"
        >
          <SettingOutlined class="nav-icon" />
          <span v-if="!collapsed" class="nav-label">{{ t('user.settings') }}</span>
        </router-link>

        <!-- 用户区 -->
        <div v-if="isLoggedIn" class="sidebar-user">
          <ProtectedAvatar
            :src="userAvatar"
            :size="28"
            class="user-avatar"
          />
          <span v-if="!collapsed" class="user-name">{{ currentUserName }}</span>
        </div>
      </div>
    </aside>

    <!-- 内容区 -->
    <main class="shell-content">
      <router-view v-slot="{ Component, route }">
        <transition :name="transitionName" mode="out-in">
          <component :is="Component" :key="route.path" />
        </transition>
      </router-view>
    </main>

    <!-- 命令面板 -->
    <CommandPalette ref="commandPaletteRef" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, type Component } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  HomeOutlined,
  AppstoreOutlined,
  ExperimentOutlined,
  ApartmentOutlined,
  DashboardOutlined,
  SettingOutlined,
  BulbOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  DeploymentUnitOutlined,
  ClusterOutlined,
  LineChartOutlined,
  FilterOutlined,
  ThunderboltOutlined,
  TrophyOutlined,
} from '@ant-design/icons-vue'
import { useUserStore, useAppStore } from '@/stores'
import ProtectedAvatar from '@/components/common/ProtectedAvatar.vue'
import CommandPalette from '@/components/common/CommandPalette.vue'
import { PLATFORM_NAME, PLATFORM_SHORT_NAME } from '@/config/brand'

const { t } = useI18n()
const route = useRoute()
const userStore = useUserStore()
const appStore = useAppStore()

// ── 侧边栏状态 ──
const collapsed = computed(() => appStore.isCollapsed)
const commandPaletteRef = ref<InstanceType<typeof CommandPalette> | null>(null)
// 移动端抽屉：窄屏下侧栏改为抽屉，避免底部 Tab 挤掉设计/管理/设置入口
const mobileNavOpen = ref(false)

const isAdmin = computed(() => userStore.isAdmin)
const isLoggedIn = computed(() => userStore.isLoggedIn)
const currentUserName = computed(() => userStore.user?.display_name ?? userStore.user?.username)
const userAvatar = computed(() => userStore.avatar)

// ── 导航 ──
interface NavItem {
  key: string
  to: string
  icon: Component
  labelKey: string
  active: string[]
  badge?: string | number
}

const mainNav: NavItem[] = [
  {
    key: 'workspace',
    to: '/workspace',
    icon: HomeOutlined,
    labelKey: 'nav.workspace',
    active: ['/workspace'],
  },
  {
    key: 'tools',
    to: '/tools',
    icon: AppstoreOutlined,
    labelKey: 'nav.tools',
    active: ['/tools'],
  },
  {
    key: 'tasks',
    to: '/tasks',
    icon: ExperimentOutlined,
    labelKey: 'nav.tasks',
    active: ['/tasks'],
  },
  {
    key: 'workflow',
    to: '/workflow',
    icon: ApartmentOutlined,
    labelKey: 'nav.workflow',
    active: ['/workflow'],
  },
  {
    key: 'achievements',
    to: '/achievements',
    icon: TrophyOutlined,
    labelKey: 'nav.achievements',
    active: ['/achievements'],
  },
]

// 直达设计/分析页入口。这些页面此前「有路由、零入口」（docs/18 收口项），
// 补到侧栏与命令面板，避免用户只能靠手敲 URL 进入。
const designNav: NavItem[] = [
  {
    key: 'molecules',
    to: '/design/molecules',
    icon: DeploymentUnitOutlined,
    labelKey: 'nav.molecules',
    active: ['/design/molecules'],
  },
  {
    key: 'peptides',
    to: '/design/peptides',
    icon: ClusterOutlined,
    labelKey: 'nav.peptides',
    active: ['/design/peptides'],
  },
  {
    key: 'predict',
    to: '/predict',
    icon: LineChartOutlined,
    labelKey: 'nav.predict',
    active: ['/predict'],
  },
  {
    key: 'screen',
    to: '/screen',
    icon: FilterOutlined,
    labelKey: 'nav.screen',
    active: ['/screen'],
  },
  {
    key: 'md',
    to: '/md',
    icon: ThunderboltOutlined,
    labelKey: 'nav.md',
    active: ['/md'],
  },
]

const adminNav: NavItem[] = [
  {
    key: 'admin',
    to: '/admin/dashboard',
    icon: DashboardOutlined,
    labelKey: 'nav.admin',
    active: ['/admin'],
  },
]

function isActive(paths: string[]): boolean {
  return paths.some((p) => route.path.startsWith(p))
}

// ── 主题切换 ──
function toggleTheme() {
  appStore.toggleTheme()
}

function toggleCollapsed() {
  appStore.toggleCollapsed()
}

// ── 路由过渡 ──
const transitionName = ref('slide-left')
const routeOrder = ['workspace', 'tools', 'tasks', 'workflow', 'admin']

watch(
  () => route.path,
  (to, from) => {
    const toIdx = routeOrder.findIndex((r) => to.includes(r))
    const fromIdx = routeOrder.findIndex((r) => from?.includes(r) ?? false)
    transitionName.value = toIdx >= fromIdx ? 'slide-left' : 'slide-right'
    mobileNavOpen.value = false
  },
)

// ── 键盘快捷键 ──
function onKeydown(e: KeyboardEvent) {
  const mod = e.metaKey || e.ctrlKey
  if (mod && e.key === 'k') {
    e.preventDefault()
    commandPaletteRef.value?.open()
  }
}

// 全局注册
import { onMounted, onUnmounted } from 'vue'
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.app-shell {
  display: flex;
  min-height: 100vh;
  background: @bg-body;
}

// ── 移动端顶栏（默认隐藏，窄屏见媒体查询）──
.mobile-topbar {
  display: none;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 @spacing-md;
  border-bottom: 1px solid @border-color;
  background: @bg-surface;
}

.mobile-brand {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  min-width: 0;
  text-decoration: none;
}

.mobile-brand-text {
  overflow: hidden;
  color: @text-primary;
  font-size: @font-size-sm;
  font-weight: @font-weight-semibold;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mobile-menu-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: @border-radius-md;
  background: transparent;
  color: @text-secondary;
  font-size: 18px;
  cursor: pointer;
  transition: all @transition-fast;

  &:hover {
    background: @bg-hover;
    color: @text-primary;
  }
}

.sidebar-backdrop {
  display: none;
}

// ── 侧边栏 ──
.shell-sidebar {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: @z-index-sidebar;
  width: @sidebar-width;
  display: flex;
  flex-direction: column;
  background: @bg-surface;
  border-right: 1px solid @border-color;
  transition: width @transition-base;
  overflow: hidden;
  user-select: none;
}

.sidebar-collapsed .shell-sidebar {
  width: @sidebar-collapsed-width;

  &:hover {
    width: @sidebar-width;
    box-shadow: @shadow-xl;
  }
}

// ── 品牌区 ──
.sidebar-brand {
  padding: @spacing-md @spacing-md;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: @spacing-sm;
}

.brand-link {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  text-decoration: none;
  min-width: 0;
}

.brand-logo {
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  border-radius: @border-radius-sm;
}

.brand-text {
  /* 中文品牌名比原来的英文短名长得多，240px 侧栏里要留出折叠按钮的位置，
     所以字号收一档并允许省略——折叠态本来只显示 logo，不影响识别。 */
  min-width: 0;
  overflow: hidden;
  font-size: @font-size-sm;
  font-weight: @font-weight-bold;
  color: @text-primary;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: -0.01em;
}

.sidebar-collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: @border-radius-md;
  background: transparent;
  color: @text-tertiary;
  cursor: pointer;
  transition: all @transition-fast;

  &:hover {
    background: @bg-hover;
    color: @text-primary;
  }
}

.sidebar-scroll {
  min-height: 0;
  overflow-y: auto;
}

// ── 导航 ──
.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: @spacing-xs;
}

.sidebar-section-label {
  padding: @spacing-xs @spacing-sm 2px;
  margin-top: @spacing-md;
  color: @text-tertiary;
  font-size: @font-size-xs;
  font-weight: @font-weight-semibold;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  height: 36px;
  padding: 0 @spacing-sm;
  border-radius: @border-radius-md;
  color: @text-secondary;
  text-decoration: none;
  font-size: @font-size-sm;
  font-weight: @font-weight-medium;
  transition: all @transition-fast;
  white-space: nowrap;
  cursor: pointer;
  border: none;
  background: none;
  width: 100%;
  font-family: @font-family;

  &:hover {
    color: @text-primary;
    background: @bg-hover;
  }

  &.active {
    color: @text-primary;
    background: @accent-color-light;

    // 当前项左侧 3px 强调条
    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 50%;
      width: 3px;
      height: 18px;
      transform: translateY(-50%);
      border-radius: 0 2px 2px 0;
      background: @accent-color;
    }
  }
}

.nav-item-btn {
  appearance: none;
}

.nav-icon {
  font-size: 18px;
  flex-shrink: 0;
  width: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.nav-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.nav-badge {
  font-size: 11px;
  font-weight: @font-weight-semibold;
  color: @accent-color;
  background: @accent-color-light;
  padding: 1px 6px;
  border-radius: 999px;
}

// ── 分隔线 ──
.sidebar-divider {
  height: 1px;
  margin: @spacing-sm @spacing-md;
  background: @border-color;
}

// ── 底部区 ──
.sidebar-footer {
  margin-top: auto;
  padding: @spacing-xs;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-top: 1px solid @border-color;
  padding-top: @spacing-sm;
}

.sidebar-user {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  padding: @spacing-sm;
  margin-top: @spacing-xs;
}

.user-avatar {
  flex-shrink: 0;
  border-radius: @border-radius-round;
}

.user-name {
  font-size: @font-size-sm;
  font-weight: @font-weight-medium;
  color: @text-primary;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

// ── 内容区 ──
.shell-content {
  flex: 1;
  margin-left: @sidebar-width;
  min-width: 0;
  min-height: 100vh;
  transition: margin-left @transition-base;
}

.sidebar-collapsed .shell-content {
  margin-left: @sidebar-collapsed-width;
}

.focus-mode {
  .shell-sidebar { display: none; }
  .shell-content { margin-left: 0; }
}

// ── 路由过渡动画 ──
.slide-left-enter-active,
.slide-left-leave-active,
.slide-right-enter-active,
.slide-right-leave-active {
  transition: all 0.2s @transition-base;
}

.slide-left-enter-from {
  opacity: 0;
  transform: translateX(16px);
}

.slide-left-leave-to {
  opacity: 0;
  transform: translateX(-16px);
}

.slide-right-enter-from {
  opacity: 0;
  transform: translateX(-16px);
}

.slide-right-leave-to {
  opacity: 0;
  transform: translateX(16px);
}

// ── 响应式：移动端抽屉式侧栏 ──
// 不再用底部 Tab（会把设计 / 管理 / 设置入口挤掉），改为顶部汉堡 + 侧栏抽屉，
// 复用同一套导航节点，入口零丢失。
@media (max-width: @screen-md) {
  .app-shell {
    flex-direction: column;
  }

  .mobile-topbar {
    display: flex;
    position: sticky;
    top: 0;
    flex-shrink: 0;
    z-index: @z-index-sticky;
  }

  .shell-sidebar {
    // 抽屉：默认移出视口，展开时滑入
    top: 0;
    bottom: 0;
    width: @sidebar-width !important;
    height: 100vh;
    height: 100dvh;
    border-right: 1px solid @border-color;
    transform: translateX(-100%);
    transition: transform @transition-base;
    z-index: @z-index-sidebar;
  }

  .mobile-nav-open .shell-sidebar {
    transform: translateX(0);
    box-shadow: @shadow-xl;
  }

  .sidebar-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 1025; // 介于顶栏(1020)与抽屉(1030)之间
    background: rgba(0, 0, 0, 0.45);
  }

  // 抽屉内保持竖排，折叠按钮对移动端无意义，隐藏
  .sidebar-collapse-btn {
    display: none;
  }

  .sidebar-scroll {
    overflow-y: auto;
  }

  .sidebar-nav {
    flex-direction: column;
    justify-content: flex-start;
    width: 100%;
    padding: @spacing-xs;
  }

  .nav-item {
    flex-direction: row;
    gap: @spacing-sm;
    height: 36px;
    padding: 0 @spacing-sm;
    font-size: @font-size-sm;
  }

  .nav-icon {
    font-size: 18px;
    width: 20px;
  }

  .nav-label {
    font-size: @font-size-sm;
  }

  .nav-badge {
    display: inline-flex;
  }

  .shell-content {
    margin-left: 0 !important;
    padding-bottom: 0;
  }
}
</style>
